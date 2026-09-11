# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine bookmark : create_bookmark (SP-43 Étape 8 — extrait
de app/mcp/tools.py). Réutilise app.configs.service.create_config_service
avec kind="bookmark", partagée avec POST /configs
(app/configs/routes.py)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs.schemas import (
    BookmarkCrossFilterEntry,
    BookmarkPayload,
    BookmarkTimeRange,
    BuilderConfig,
)
from app.configs.service import create_config_service
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.items.schemas import ItemRead
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    resolve_actor,
    without_thumbnail_url,
)
from app.mcp.tools.write_tools import write_tool


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    @write_tool
    async def create_bookmark(
        ctx: Context,
        title: str,
        appId: str,
        pageId: str,
        timeRange: BookmarkTimeRange | None = None,
        extent: tuple[float, float, float, float] | None = None,
        crossFilter: dict[str, BookmarkCrossFilterEntry] | None = None,
    ) -> ItemRead:
        """Save a named analytics view (time range/extent/cross-filter) on an
        app page — mirrors POST /configs with kind="bookmark". SP-14m."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = BookmarkPayload(
                appId=appId,
                pageId=pageId,
                timeRange=timeRange,
                extent=extent,
                crossFilter=crossFilter or {},
            )
            config = BuilderConfig(version=1, kind="bookmark", bookmark=payload)
            try:
                created = create_config_service(session, config, title=title, user=user)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.create",
                object_type="item",
                object_id=created.item.id,
                payload={"title": title},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=created.config.id,
                payload={"title": title, "kind": "bookmark"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None  # just created it, in the same transaction
            return without_thumbnail_url(result)
