# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine partage : get_sharing, set_sharing (SP-43 Étape 8 —
extrait de app/mcp/tools.py). Réutilisent app.items.service.
get_sharing_service/set_sharing_service, partagées avec
GET/PUT /items/{id}/sharing (app/items/routes.py)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.items.service import get_sharing_service, set_sharing_service
from app.mcp.tools.identity import http_exception_to_value_error, resolve_actor
from app.sharing.schemas import Sharing


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def get_sharing(ctx: Context, itemId: str) -> Sharing:
        """Get an item's sharing settings — mirrors GET /items/{id}/sharing."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                return get_sharing_service(session, item_id=itemId, user=user)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc

    @server.tool()
    async def set_sharing(ctx: Context, itemId: str, sharing: Sharing) -> None:
        """Set an item's sharing settings — mirrors PUT /items/{id}/sharing."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                set_sharing_service(
                    session, item_id=itemId, user=user, sharing=sharing, actor_kind="agent"
                )
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
