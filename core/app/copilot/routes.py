# SPDX-License-Identifier: Apache-2.0
import asyncio
import json

import anyio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependency import get_current_user
from app.copilot.llm_provider import LLMTurn, get_llm_provider
from app.copilot.mcp_loopback import McpLoopbackError, McpLoopbackSession
from app.copilot.mcp_token import McpTokenError, mcp_token_subject
from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES
from app.users.models import User

router = APIRouter()

MAX_TOOL_ITERATIONS = 6
TURN_TIMEOUT_SECONDS = 30.0


class CopilotMessage(BaseModel):
    role: str
    content: str


class CopilotTurnRequest(BaseModel):
    itemId: str
    message: str
    history: list[CopilotMessage] = []
    mcpToken: str
    currentConfig: dict
    clientTools: list[dict] = []


class ClientOp(BaseModel):
    op: str
    args: dict


class CopilotTurnResponse(BaseModel):
    reply: str
    clientOps: list[ClientOp]


def _system_message(item_id: str, current_config: dict) -> dict:
    return {
        "role": "system",
        "content": (
            "Tu es le copilote intégré au builder GeoStudio. Tu édites la "
            "configuration affichée par petites actions ciblées (widgets, "
            "sources de données), jamais en générant un tableau de bord "
            "entier d'un coup. Utilise les outils fournis ; ne réponds en "
            "texte libre que pour expliquer ou poser une question.\n\n"
            f"Item en cours d'édition : {item_id}\n"
            f"Configuration actuelle (JSON) : {json.dumps(current_config, ensure_ascii=False)}"
        ),
    }


async def _run_turn(*, request: CopilotTurnRequest, mcp_session: McpLoopbackSession) -> CopilotTurnResponse:
    try:
        server_tools_raw = await mcp_session.list_tools()
    except McpLoopbackError as exc:
        raise HTTPException(status_code=502, detail=f"MCP loopback failed: {exc}") from exc
    server_tools = [t for t in server_tools_raw if t["name"] in ALLOWED_MCP_TOOL_NAMES]
    all_tools = server_tools + request.clientTools

    messages: list[dict] = [_system_message(request.itemId, request.currentConfig)]
    for m in request.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": request.message})

    provider = get_llm_provider()

    for _ in range(MAX_TOOL_ITERATIONS):
        # provider.chat est synchrone (httpx.post bloquant) : appelé
        # directement ici, il gèlerait la boucle d'événements — donc tout le
        # process, tous tenants confondus — pour la latence du LLM, et
        # neutraliserait le asyncio.wait_for qui garde ce tour (wait_for ne
        # peut pas interrompre un appel synchrone qui tient déjà le thread).
        turn: LLMTurn = await anyio.to_thread.run_sync(provider.chat, messages, all_tools)
        if not turn.tool_calls:
            return CopilotTurnResponse(reply=turn.text, clientOps=[])

        client_ops: list[ClientOp] = []
        messages.append({
            "role": "assistant", "content": turn.text,
            "tool_calls": [
                # arguments doit être une **chaîne** JSON : le schéma de
                # message OpenAI rejette un objet à la réinjection du tour
                # suivant.
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in turn.tool_calls
            ],
        })

        for tc in turn.tool_calls:
            if tc.name not in ALLOWED_MCP_TOOL_NAMES:
                # Ni dans l'allowlist MCP : soit un outil client déclaré par
                # le shell, soit un nom halluciné — dans les deux cas jamais
                # exécuté côté serveur. Une opération client ne produit
                # jamais de résultat réinjecté au LLM dans le même tour.
                client_ops.append(ClientOp(op=tc.name, args=tc.arguments))
                continue
            try:
                result = await mcp_session.call_tool(tc.name, tc.arguments)
            except McpLoopbackError as exc:
                raise HTTPException(status_code=502, detail=f"MCP loopback failed: {exc}") from exc
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": result.text or ("(erreur outil)" if result.is_error else ""),
            })

        if client_ops:
            return CopilotTurnResponse(reply=turn.text, clientOps=client_ops)

    return CopilotTurnResponse(
        reply="Désolé, je n'ai pas réussi à conclure cette demande — reformule ou simplifie.",
        clientOps=[],
    )


@router.post("/copilot/turn")
async def copilot_turn(
    body: CopilotTurnRequest,
    user: User = Depends(get_current_user),
) -> CopilotTurnResponse:
    # Le jeton MCP du corps agira à la place de l'appelant : il doit
    # d'abord être prouvé lui appartenir, sinon la route vérifie une
    # identité (header Authorization) et exécute sous une autre.
    try:
        token_subject = mcp_token_subject(body.mcpToken)
    except McpTokenError as exc:
        raise HTTPException(status_code=401, detail="Jeton MCP invalide.") from exc
    if token_subject != user.oidc_sub:
        raise HTTPException(
            status_code=403,
            detail="Le jeton MCP ne correspond pas à l'utilisateur authentifié.",
        )

    mcp_session = McpLoopbackSession(body.mcpToken)
    try:
        return await asyncio.wait_for(
            _run_turn(request=body, mcp_session=mcp_session),
            timeout=TURN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Le copilote a mis trop de temps à répondre.") from exc
    finally:
        await mcp_session.aclose()
