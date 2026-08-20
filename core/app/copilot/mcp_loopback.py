# SPDX-License-Identifier: Apache-2.0
"""Client de rappel vers le serveur /mcp existant, pour la boucle
d'outils du copilote (SP-20) — un vrai appel réseau (HTTP), pas une
logique d'outil dupliquée. Réutilise le même protocole JSON-RPC-sur-HTTP
déjà exercé par core/tests/test_mcp_routes.py (initialize ->
notifications/initialized -> tools/list ou tools/call, réponse en SSE) :
un httpx.AsyncClient brut suffit, pas besoin du SDK client `mcp` (deuxième
dépendance client pour un seul appelant)."""

import json
import os
import uuid

import httpx

from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES

__all__ = [
    "ALLOWED_MCP_TOOL_NAMES",
    "McpLoopbackError",
    "McpLoopbackSession",
    "ToolCallResult",
]


class McpLoopbackError(Exception):
    """Échec au niveau du protocole (poignée de main, HTTP, réponse
    malformée) — distinct d'un outil qui s'exécute et lève une erreur
    métier, renvoyée comme ToolCallResult(is_error=True) pour que le LLM
    la voie et puisse réagir, plutôt que de faire planter tout le tour."""


class ToolCallResult:
    def __init__(self, text: str, is_error: bool):
        self.text = text
        self.is_error = is_error


def loopback_base_url() -> str:
    """Cible du rappel HTTP vers `/mcp`, à l'intérieur du process `core`.

    `CORE_BASE_URL` porte l'identité **publique** du cœur (métadonnées
    OAuth du serveur MCP depuis SP-2a, `geostudio-connection.json` de
    SP-18b) : en production l'overlay compose la fixe à
    `https://<hôte public>/api`. La prendre comme cible de rappel oblige le
    conteneur à joindre son propre nom d'hôte public en TLS depuis le
    réseau Docker — hairpin NAT, et de toute façon rejeté par la garde
    anti-DNS-rebinding de FastMCP (`allowed_hosts`, cf. SP-20 Task 4). En
    dev ça marchait par accident, les deux valeurs coïncidant.

    D'où `CORE_INTERNAL_BASE_URL` (wiring compose : `http://localhost:8200`,
    le process lui-même). Repli sur `CORE_BASE_URL` quand elle n'est pas
    définie, pour ne pas casser un dev déjà configuré.
    """
    internal = os.environ.get("CORE_INTERNAL_BASE_URL")
    if internal:
        return internal
    return os.environ["CORE_BASE_URL"]


class McpLoopbackSession:
    """Une session par requête POST /copilot/turn — la poignée de main
    n'a lieu qu'une fois, paresseusement, au premier appel."""

    def __init__(self, mcp_token: str, *, http_client: httpx.AsyncClient | None = None):
        self._mcp_token = mcp_token
        self._client = http_client or httpx.AsyncClient(
            base_url=loopback_base_url(),
            timeout=15.0,
        )
        self._owns_client = http_client is None
        self._session_id: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._mcp_token}",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    async def _ensure_initialized(self) -> None:
        if self._session_id:
            return
        response = await self._client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "geostudio-copilot", "version": "0"},
                },
            },
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP initialize failed: {response.status_code}")
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise McpLoopbackError("MCP initialize did not return a session id")
        self._session_id = session_id
        notify = await self._client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers(),
        )
        if notify.status_code != 202:
            raise McpLoopbackError(f"MCP notifications/initialized failed: {notify.status_code}")

    def _parse_sse(self, response: httpx.Response) -> dict:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line.removeprefix("data: "))
        raise McpLoopbackError("no SSE data line in MCP response")

    async def list_tools(self) -> list[dict]:
        await self._ensure_initialized()
        response = await self._client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}},
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP tools/list failed: {response.status_code}")
        payload = self._parse_sse(response)
        if "error" in payload:
            raise McpLoopbackError(f"MCP tools/list error: {payload['error']}")
        return payload["result"]["tools"]

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        await self._ensure_initialized()
        response = await self._client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            headers=self._headers(),
        )
        if response.status_code == 401:
            raise McpLoopbackError("MCP token rejected (expired or wrong audience)")
        if response.status_code != 200:
            raise McpLoopbackError(f"MCP tools/call failed: {response.status_code}")
        payload = self._parse_sse(response)
        if "error" in payload:
            # Erreur JSON-RPC de protocole (requête malformée) — distincte
            # d'un outil qui lève ou d'un nom d'outil inconnu, tous deux
            # remontés par ce SDK MCP comme isError=true dans un "result"
            # 200 normal (cf. isError ci-dessous), jamais comme "error" ici
            # (vérifié empiriquement, SP-20 tâche 4).
            raise McpLoopbackError(f"MCP tools/call error: {payload['error']}")
        result = payload["result"]
        content = result.get("content") or []
        text = content[0]["text"] if content else ""
        return ToolCallResult(text=text, is_error=bool(result.get("isError", False)))
