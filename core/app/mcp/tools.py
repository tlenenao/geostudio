# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import admin_subs, is_read_only_mode
from app.collections import repository as collections_repo
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs import repository as configs_repo
from app.configs.dataset_validation import validate_dataset_payload
from app.configs.extension_permissions import ExtensionPermissionError, validate_extension_permissions
from app.configs.repository import ConfigRead
from app.configs.schemas import BuilderConfig, DatasetColumnMeta, DatasetPayload
from app.db import request_scoped_session
from app.features.repository import FilterError, select_features
from app.features.rls import rls_scope
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.mcp import form_app
from app.sharing import repository as sharing_repo
from app.sharing.authorization import ItemAccessFacts, can
from app.sharing.schemas import Sharing
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

READ_ONLY_TOOLS = {"save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset"}


def _resolve_actor(session, access_token) -> User:
    claims = access_token.claims
    tenant = get_or_create_default_tenant(session)
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub=access_token.subject,
        username=claims.get("preferred_username", access_token.subject),
        email=claims.get("email"),
        first_name=claims.get("given_name", ""),
        last_name=claims.get("family_name", ""),
        bootstrap_admin=access_token.subject in admin_subs(),
    )


def _require_access(session, *, user: User, item_id: str, action: str) -> ItemAccessFacts:
    """Mirrors app/configs/routes.py's _require_access — same 404-then-403
    logic — but raises ValueError (a normal tool-body exception the SDK
    turns into an is_error result) instead of HTTPException, since a
    TokenVerifier-authenticated MCP tool has no HTTP status channel."""
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise ValueError("item not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise ValueError("not allowed to modify this item")
    return facts


def _require_collection_read(session, *, user: User, collection_id: str):
    """Mirrors app/collections/routes.py's get_readable_collection — ValueError
    instead of HTTPException, same rationale as _require_access above."""
    col = collections_repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    if col is None:
        raise ValueError("collection not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(col), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        raise ValueError("collection not found")
    return col


def _validate_extension_scope(session, config: BuilderConfig, *, tenant_id: str) -> None:
    """Mirrors app/configs/routes.py's _validate_extension_scope — same
    ExtensionPermissionError source of truth, but re-raised as ValueError
    (a normal tool-body exception the SDK turns into an is_error result)
    instead of HTTPException, same rationale as _require_access above."""
    try:
        validate_extension_permissions(session, config, tenant_id=tenant_id)
    except ExtensionPermissionError as err:
        raise ValueError(str(err)) from err


def _validate_dataset(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors app/configs/routes.py's call to validate_dataset_payload — same
    per-source (collection/arcgis) readability check the REST route runs on
    POST /configs and PUT /configs/{by-item} — but raises ValueError instead
    of HTTPException, same rationale as _require_access above. Without this
    call, create_dataset could create a dataset pointing at a collection or
    arcgis layer invisible to the caller."""
    try:
        validate_dataset_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc


def _parse_bbox_tuple(raw: str) -> tuple[float, float, float, float]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise ValueError("bbox must be minx,miny,maxx,maxy") from None


def register_tools(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def whoami(ctx: Context) -> dict:
        """Return the identity of the currently authenticated MCP caller —
        proves the OAuth handshake resolves to the same User the shell's
        REST API would resolve for the same Keycloak subject."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            return {"username": user.username, "tenantId": user.tenant_id}

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
            user = _resolve_actor(session, access_token)
            return items_repo.list_items(
                session, tenant_id=user.tenant_id, current_user_id=user.id,
                q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
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
            user = _resolve_actor(session, access_token)
            return items_repo.list_items(
                session, tenant_id=user.tenant_id, current_user_id=user.id,
                q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
            )

    @server.tool()
    async def query_features(
        ctx: Context,
        collectionId: str,
        bbox: str | None = None,
        filters: dict[str, str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Read features from a collection — mirrors GET
        /collections/{id}/items (bbox, attribute filters, pagination), same
        permissions/RLS. No natural-language-to-filter translation: filters
        are structured field=value pairs, like any OGC client (SP-7 MCP v1)."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            col = _require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound:
                raise ValueError("collection backing table not found")
            except UnsupportedTable as exc:
                raise ValueError(exc.reason)
            parsed_bbox = _parse_bbox_tuple(bbox) if bbox else None
            try:
                with rls_scope(session, col.tenant_id):
                    page = select_features(
                        session, info, limit=min(limit, 1000), offset=offset,
                        bbox=parsed_bbox, filters=filters or None,
                    )
            except FilterError as exc:
                raise ValueError(f"unknown filter field: {exc.field}")
            return {
                "type": "FeatureCollection", "features": page.features,
                "numberMatched": page.number_matched, "numberReturned": page.number_returned,
            }

    @server.tool()
    async def get_item(ctx: Context, itemId: str) -> ItemRead:
        """Get one catalog item by id — mirrors GET /items/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="read")
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=itemId)
            if result is None:
                raise ValueError("item not found")
            return result

    @server.tool()
    async def get_app_config(ctx: Context, itemId: str) -> ConfigRead:
        """Get the app/dashboard config for an item — mirrors GET /configs/by-item/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="read")
            result = configs_repo.get_config_by_item(session, itemId)
            if result is None:
                raise ValueError("config not found")
            return result

    @server.tool()
    async def save_app_config(ctx: Context, itemId: str, config: BuilderConfig) -> ConfigRead:
        """Save (and version) the app/dashboard config for an item — mirrors
        PUT /configs/by-item/{id}."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="write")
            existing = configs_repo.get_config_by_item(session, itemId)
            if existing is None:
                raise ValueError("config not found")
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            result = configs_repo.update_config(session, existing.id, config, tenant_id=user.tenant_id)
            if result is None:
                raise ValueError("config not found")
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.update", object_type="config", object_id=existing.id, payload={},
            )
            return result

    @server.tool()
    async def create_item(
        ctx: Context, kind: Literal["app", "dashboard"], title: str, config: BuilderConfig,
    ) -> ItemRead:
        """Create a new app or dashboard — mirrors POST /configs. The item's
        owner is always the authenticated caller; there is no owner
        parameter to accept from the agent."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type=kind, title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": kind},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None  # just created it, in the same transaction
            return result

    @server.tool()
    async def create_form_app(
        ctx: Context, collectionId: str, title: str | None = None,
    ) -> ItemRead:
        """Compose a Carte+Table(+Formulaire if the caller can write) app on
        an existing collection, from its introspected schema — same shape as
        the builder's "Application de saisie" gallery template (SP-4c),
        generated instead of hand-picked. Formulaire is included only if the
        caller has write access to the collection (mirrors the canWrite
        predicate SP-4c exposes on collections). SP-7 MCP v1."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            col = _require_collection_read(session, user=user, collection_id=collectionId)
            try:
                info = introspect_table(session, col.table_name)
            except TableNotFound:
                raise ValueError("collection backing table not found")
            except UnsupportedTable as exc:
                raise ValueError(exc.reason)
            schema = table_info_to_schema(info)
            include_form = form_app.can_write_collection(session, user=user, col=col)
            config = form_app.build_config(
                collection_id=collectionId, schema=schema, include_form=include_form,
            )
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="app", title=title or f"Application {col.title}",
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": item.title, "collectionId": collectionId},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"collectionId": collectionId, "includeForm": include_form},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None
            return result

    @server.tool()
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
            user = _resolve_actor(session, access_token)
            payload = DatasetPayload(
                source=source, collectionId=collectionId, arcgisItemId=arcgisItemId,
                columns=columns or {}, timeField=timeField, reactsToExtent=reactsToExtent,
            )
            config = BuilderConfig(version=1, kind="dataset", dataset=payload)
            _validate_dataset(session, config, user=user)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="dataset", title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": "dataset"},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None
            return result

    @server.tool()
    async def get_sharing(ctx: Context, itemId: str) -> Sharing:
        """Get an item's sharing settings — mirrors GET /items/{id}/sharing."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            facts = _require_access(session, user=user, item_id=itemId, action="read")
            shares = sharing_repo.list_shares(session, item_id=itemId)
            return Sharing(
                public=facts.is_public,
                groups=[{"groupId": s.group_id, "role": s.role} for s in shares],
            )

    @server.tool()
    async def set_sharing(ctx: Context, itemId: str, sharing: Sharing) -> None:
        """Set an item's sharing settings — mirrors PUT /items/{id}/sharing."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="share")
            ok = sharing_repo.replace_shares(
                session, tenant_id=user.tenant_id, item_id=itemId,
                shares=[(g.groupId, g.role) for g in sharing.groups],
            )
            if not ok:
                raise ValueError("group not found")
            items_repo.set_is_public(session, tenant_id=user.tenant_id, item_id=itemId, is_public=sharing.public)
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.share", object_type="item", object_id=itemId,
                payload={"public": sharing.public, "groups": [g.model_dump() for g in sharing.groups]},
            )

    @server.resource("schema://app-config")
    def app_config_schema() -> dict:
        """JSON Schema for AppConfig/DashboardConfig — validate before
        calling create_item or save_app_config."""
        return BuilderConfig.model_json_schema()
