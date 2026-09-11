# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine dataset : create_dataset (SP-43 Étape 8 — extrait de
app/mcp/tools.py). Réutilise app.configs.service.create_config_service avec
kind="dataset", partagée avec POST /configs (app/configs/routes.py)."""

from typing import Literal

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs.schemas import BuilderConfig, DatasetColumnMeta, DatasetPayload
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
    async def create_dataset(
        ctx: Context,
        title: str,
        source: Literal["collection", "arcgis"],
        collectionId: str | None = None,
        arcgisItemId: str | None = None,
        columns: dict[str, DatasetColumnMeta] | None = None,
        timeField: str | None = None,
        reactsToExtent: bool = False,
    ) -> ItemRead:
        """Create a shared dataset (source collection or arcgis) — mirrors
        POST /configs with kind="dataset" (the path
        itemClient.ts::createDatasetItem uses). SP-14l."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = DatasetPayload(
                source=source,
                collectionId=collectionId,
                arcgisItemId=arcgisItemId,
                columns=columns or {},
                timeField=timeField,
                reactsToExtent=reactsToExtent,
            )
            config = BuilderConfig(version=1, kind="dataset", dataset=payload)
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
                payload={"title": title, "kind": "dataset"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None
            return without_thumbnail_url(result)
