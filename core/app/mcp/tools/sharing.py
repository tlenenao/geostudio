# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine partage : get_sharing, set_sharing (SP-43 Étape 8 —
extrait de app/mcp/tools.py). Réutilisent app.items.service.
get_sharing_service/set_sharing_service, partagées avec
GET/PUT /items/{id}/sharing (app/items/routes.py)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.items.service import get_sharing_service, set_sharing_service
from app.mcp.tools.identity import http_exception_to_value_error, resolve_actor
from app.sharing import repository as sharing_repo
from app.sharing.schemas import Sharing


class GroupRead(BaseModel):
    id: str
    name: str


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def list_groups(ctx: Context) -> list[GroupRead]:
        """List sharing groups for the caller's tenant — mirrors GET /groups."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            return [
                GroupRead(id=g.id, name=g.name)
                for g in sharing_repo.list_groups(session, tenant_id=user.tenant_id)
            ]

    @server.tool()
    async def create_group(ctx: Context, name: str) -> GroupRead:
        """Create a sharing group — mirrors POST /groups."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            group = sharing_repo.create_group(
                session, tenant_id=user.tenant_id, name=name, created_by=user.id
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="group.create",
                object_type="group",
                object_id=group.id,
                payload={"name": name},
            )
            return GroupRead(id=group.id, name=group.name)

    @server.tool()
    async def add_group_member(ctx: Context, groupId: str, userId: str) -> None:
        """Add a member to a sharing group — mirrors POST /groups/{id}/members.
        Only the group's creator may add a member (repository-enforced) —
        raises rather than silently no-op-ing on a foreign group."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            ok = sharing_repo.add_member(
                session,
                tenant_id=user.tenant_id,
                group_id=groupId,
                user_id=userId,
                caller_id=user.id,
            )
            if not ok:
                raise ValueError("group or user not found, or you are not the group's creator")
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="group.add_member",
                object_type="group",
                object_id=groupId,
                payload={"userId": userId},
            )

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
