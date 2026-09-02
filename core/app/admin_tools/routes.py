# SPDX-License-Identifier: Apache-2.0
"""Routes du gate /admin/* — montées uniquement quand
CORE_ADMIN_TOOLS_ENABLED est actif (app.main, même patron que
app.tileset3d/app.export). Trois endpoints : lancement (Bearer, appelé par
le shell), bootstrap de session (jeton de lancement à durée de vie courte
(60s) -> cookie, atteint par navigation directe du navigateur depuis l'URL
renvoyée par le lancement), et vérification (appelée par le forwardAuth de
Traefik, jamais par le shell — cf. plan d'implémentation, Tâche 4)."""

import os
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.admin_tools.tokens import (
    AdminToolsTokenError,
    decode_launch_token,
    decode_session_token,
    mint_launch_token,
    mint_session_token,
)
from app.auth.dependency import get_current_user
from app.users.models import User

router = APIRouter()

ToolName = Literal["martin", "titiler", "grafana"]
_SESSION_COOKIE = "gs_admin_session"
_SESSION_MAX_AGE_SECONDS = 1800


class LaunchAdminToolResponse(BaseModel):
    url: str


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


@router.post("/admin-tools/launch/{tool}")
def launch_admin_tool(
    tool: ToolName, user: User = Depends(get_current_user)
) -> LaunchAdminToolResponse:
    _require_admin(user)
    base = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    token = mint_launch_token(sub=user.id, tool=tool)
    return LaunchAdminToolResponse(url=f"{base}/admin-tools/session/{tool}?_at={token}")


@router.get("/admin-tools/session/{tool}")
def bootstrap_admin_tool_session(tool: ToolName, _at: str) -> Response:
    try:
        claims = decode_launch_token(_at)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid launch token") from exc
    if claims.tool != tool:
        raise HTTPException(status_code=401, detail="invalid launch token")
    session_token = mint_session_token(sub=claims.sub)
    response = RedirectResponse(url=f"/admin/{tool}/", status_code=302)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=session_token,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/admin",
    )
    return response


@router.get("/admin-tools/verify")
def verify_admin_tool_session(gs_admin_session: str | None = Cookie(default=None)) -> Response:
    if gs_admin_session is None:
        raise HTTPException(status_code=403, detail="no admin session")
    try:
        decode_session_token(gs_admin_session)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=403, detail="invalid admin session") from exc
    return Response(status_code=200)
