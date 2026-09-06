# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine catalogue : list_items, search_catalog, get_item,
query_features (SP-43 Étape 8 — extrait de app/mcp/tools.py). get_item
appelle désormais app.items.service.get_item_service, partagée avec
GET /items/{id} (première couche de service partagée entre route REST et
tool MCP de ce dépôt, avec app.items.service.get_sharing_service/
set_sharing_service et app.configs.service.create_config_service)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

from app.collections import repository as collections_repo
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.db import request_scoped_session
from app.features.repository import FilterError, select_features
from app.features.rls import rls_scope
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.items.service import get_item_service
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    require_collection_read,
    resolve_actor,
    without_thumbnail_url,
    without_thumbnail_urls,
)
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege


class CollectionSearchResult(BaseModel):
    id: str
    title: str
    description: str


def _parse_bbox_tuple(raw: str) -> tuple[float, float, float, float]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise ValueError("bbox must be minx,miny,maxx,maxy") from None


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def list_items(
        ctx: Context,
        q: str | None = None,
        type: str | None = None,
        scope: str = "all",
        page: int = 1,
        pageSize: int = 12,
    ) -> ItemPage:
        """List catalog items — mirrors GET /items. scope: all|mine|shared|public."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            return without_thumbnail_urls(
                items_repo.list_items(
                    session,
                    tenant_id=user.tenant_id,
                    current_user_id=user.id,
                    q=q,
                    resource_type=type,
                    scope=scope,
                    page=page,
                    page_size=pageSize,
                )
            )

    @server.tool()
    async def search_catalog(
        ctx: Context,
        q: str | None = None,
        type: str | None = None,
        scope: str = "all",
        page: int = 1,
        pageSize: int = 12,
    ) -> ItemPage:
        """Search the catalog (hybrid trigram + vector ranking on q) — items
        only, not collections. Same permissions/parameters as list_items;
        registered as its own tool for agent discoverability of the search
        capability (SP-7 MCP v1)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            return without_thumbnail_urls(
                items_repo.list_items(
                    session,
                    tenant_id=user.tenant_id,
                    current_user_id=user.id,
                    q=q,
                    resource_type=type,
                    scope=scope,
                    page=page,
                    page_size=pageSize,
                )
            )

    @server.tool()
    async def search_collections(
        ctx: Context, q: str | None = None, page: int = 1, pageSize: int = 12
    ) -> list[CollectionSearchResult]:
        """Search collections (hybrid trigram + vector ranking on q, same
        mechanism as search_catalog for items) — collections were never
        searchable from an agent before this tool (GAP-40/47)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            can_see_all = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
            cols = collections_repo.list_visible_collections(
                session,
                tenant_id=user.tenant_id,
                user_id=user.id,
                can_see_all=can_see_all,
                q=q,
            )
            start = (page - 1) * pageSize
            page_cols = cols[start : start + pageSize]
            return [
                CollectionSearchResult(id=c.id, title=c.title, description=c.description)
                for c in page_cols
            ]

    @server.tool()
    async def query_features(
        ctx: Context,
        collectionId: str,
        bbox: str | None = None,
        geomIntersects: dict | None = None,
        filters: dict[str, str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Read features from a collection — mirrors GET
        /collections/{id}/items (bbox, attribute filters, pagination), same
        permissions/RLS. No natural-language-to-filter translation: filters
        are structured field=value pairs, like any OGC client (SP-7 MCP v1).
        geomIntersects: a GeoJSON geometry object (already parsed, unlike the
        REST route's query-string form) — relayed to select_features exactly
        like bbox/filters (GAP-47)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            col = require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound as exc:
                raise ValueError("collection backing table not found") from exc
            except UnsupportedTable as exc:
                raise ValueError(exc.reason) from exc
            parsed_bbox = _parse_bbox_tuple(bbox) if bbox else None
            try:
                with rls_scope(session, col.tenant_id):
                    page = select_features(
                        session,
                        info,
                        limit=min(limit, 1000),
                        offset=offset,
                        bbox=parsed_bbox,
                        geom_intersects=geomIntersects,
                        filters=filters or None,
                    )
            except FilterError as exc:
                raise ValueError(f"unknown filter field: {exc.field}") from exc
            return {
                "type": "FeatureCollection",
                "features": page.features,
                "numberMatched": page.number_matched,
                "numberReturned": page.number_returned,
            }

    @server.tool()
    async def get_item(ctx: Context, itemId: str) -> ItemRead:
        """Get one catalog item by id — mirrors GET /items/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                result = get_item_service(session, item_id=itemId, user=user)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            return without_thumbnail_url(result)
