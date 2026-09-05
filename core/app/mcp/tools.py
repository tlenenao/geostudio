# SPDX-License-Identifier: Apache-2.0
import json
from typing import Literal

import httpx
from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.alerts import repository as alerts_repo
from app.analytics.aggregate import (
    AggregateMeasure,
    AggregateRequestBody,
    UnknownAggregateField,
    _measure_label,
    run_collection_aggregate,
)
from app.attachments import repository as attachments_repo
from app.audit.writer import write_audit
from app.auth.dependency import admin_subs, analyst_subs, is_etl_enabled, is_read_only_mode
from app.collections import repository as collections_repo
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs import repository as configs_repo
from app.configs.bookmark_validation import validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload
from app.configs.extension_permissions import (
    ExtensionPermissionError,
    validate_extension_permissions,
)
from app.configs.pipeline_validation import validate_pipeline_payload
from app.configs.repository import ConfigRead
from app.configs.routes import _require_kind_matches_existing
from app.configs.schemas import (
    BookmarkCrossFilterEntry,
    BookmarkPayload,
    BookmarkTimeRange,
    BuilderConfig,
    DatasetColumnMeta,
    DatasetPayload,
    PipelineEdge,
    PipelineNode,
    PipelinePayload,
)
from app.db import request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FilterError, select_features
from app.features.rls import rls_scope
from app.harvest import live_query
from app.harvest import repository as harvest_repo
from app.harvest import routes as harvest_routes
from app.harvest.egress import EgressBlockedError
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead
from app.mcp import form_app
from app.pipelines import repository as pipelines_repo
from app.pipelines import service as pipelines_service
from app.pipelines.jobs import run_pipeline_task
from app.reports import repository as reports_repo
from app.roles.guards import has_privilege, require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege
from app.sharing import repository as sharing_repo
from app.sharing.authorization import ItemAccessFacts, can
from app.sharing.schemas import Sharing
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

READ_ONLY_TOOLS = {
    "save_app_config",
    "create_item",
    "create_form_app",
    "set_sharing",
    "create_dataset",
    "create_bookmark",
    "create_pipeline",
    "run_pipeline",
}


def _without_thumbnail_url(item: ItemRead) -> ItemRead:
    """SP-42, correctif 2 (F-coeur-federation-08) : ItemRead.thumbnailUrl
    pointe vers GET /items/{id}/thumbnail, gardée par l'audience OIDC du
    shell (CORE_OIDC_AUDIENCE). Un jeton MCP porte l'audience distincte
    CORE_MCP_AUDIENCE (app/mcp/auth.py) et reçoit systématiquement 401 sur
    cette route — servir cette URL à un agent MCP promettrait un accès qui
    échoue toujours. Plutôt que d'élargir une garde d'authentification (les
    deux options qu'aurait demandé un mécanisme d'échange), on cesse de la
    produire côté MCP ; le champ reste `str | None` côté schéma REST, donc
    ce None ne casse aucun contrat de tool."""
    return item.model_copy(update={"thumbnailUrl": None})


def _without_thumbnail_urls(page: ItemPage) -> ItemPage:
    return page.model_copy(update={"items": [_without_thumbnail_url(i) for i in page.items]})


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
        bootstrap_analyst=access_token.subject in analyst_subs(),
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
    col = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id
    )
    if col is None:
        raise ValueError("collection not found")
    can_manage_collections = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    readable = can_manage_collections or can(
        session,
        user_id=user.id,
        action="read",
        item=collections_repo.get_access_facts(col),
        kind="collection",
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


def _validate_bookmark(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors _validate_dataset above — same rationale (ValueError instead
    of HTTPException, no HTTP status channel in an MCP tool body)."""
    try:
        validate_bookmark_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc


def _validate_pipeline(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors _validate_dataset/_validate_bookmark above — same rationale
    (ValueError instead of HTTPException, no HTTP status channel in an MCP
    tool body). validate_pipeline_payload (app.configs.pipeline_validation)
    raises HTTPException for graph/topology/per-node errors, same as its
    dataset/bookmark counterparts."""
    try:
        validate_pipeline_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc


def _require_config_privilege(session, config: BuilderConfig, *, user: User) -> None:
    """SP-42/F-securite-autorisation-01 fixed POST/PUT /configs and
    PUT /configs/by-item/{id} (commit eafb02cc) by adding a kind->privilege
    guard in app.configs.routes — but every MCP tool below that calls
    configs_repo.create_config/update_config directly (create_item,
    create_form_app, create_dataset, create_bookmark, create_pipeline,
    save_app_config) stayed wide open, since none of them go through those
    REST handlers. SP-43 Étape 1: consumes app.roles.kind_registry.
    privilege_for_kind directly (the single source of truth for the
    kind->privilege mapping, rather than a second table that could silently
    drift from it) but raises ValueError instead of HTTPException, same
    rationale as _require_access above."""
    try:
        require_privilege(session, user, privilege_for_kind(config.kind))
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc


def _require_kind_unchanged(existing_kind: str, submitted_kind: str) -> None:
    """SP-42, revue des lots de correctifs 2/3bis (point 3) : mirrors
    app.configs.routes._require_kind_matches_existing for save_app_config,
    the only MCP tool that updates an already-existing config (the other
    call sites in this module all create — there is no existing kind to
    compare yet) — raises ValueError instead of HTTPException, same
    rationale as _require_config_privilege above."""
    try:
        _require_kind_matches_existing(existing_kind, submitted_kind)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc


def _resolve_dataset_payload(session, *, user: User, dataset_item_id: str) -> DatasetPayload:
    """Read-access check on the dataset item itself, plus its kind/payload —
    shared first step for run_analytics_query and explain_dataset (Task 3)."""
    _require_access(session, user=user, item_id=dataset_item_id, action="read")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if config is None or config.kind != "dataset" or config.config.dataset is None:
        raise ValueError("dataset not found")
    return config.config.dataset


def _resolve_arcgis_external_url(session, *, user: User, dataset_item_id: str) -> str:
    """Mirrors app/harvest/routes.py's _resolve_arcgis_dataset — same
    dataset-read-then-arcgis-layer-read double check as
    /datasets/{id}/arcgis/aggregate — but raises ValueError instead of
    HTTPException, same rationale as _require_access above. Re-checks
    dataset-item read access independently of _resolve_dataset_payload's
    own check (harmless, cheap, and keeps this a faithful, self-contained
    mirror of the REST route's helper rather than a partial reimplementation)."""
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=dataset_item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise ValueError("dataset not found")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if (
        config is None
        or config.kind != "dataset"
        or config.config.dataset is None
        or config.config.dataset.source != "arcgis"
    ):
        raise ValueError("dataset not found")
    arcgis_item_id = config.config.dataset.arcgisItemId
    assert arcgis_item_id is not None
    record = harvest_repo.get_feature_layer_record(
        session, tenant_id=user.tenant_id, item_id=arcgis_item_id
    )
    if record is None or record.external_url is None:
        raise ValueError("arcgis layer not found")
    layer_facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=arcgis_item_id
    )
    if layer_facts is None or not can(session, user_id=user.id, action="read", item=layer_facts):
        raise ValueError("arcgis layer not found")
    return record.external_url


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

    @server.tool(structured_output=False)
    async def list_attachments(
        ctx: Context, collectionId: str, fid: str, fieldKey: str | None = None
    ) -> str:
        """List the metadata of files attached to one entity of a collection
        (chantier 4.12) — read-only, never returns file bytes. No fileUrl:
        the REST proxy-read it would point to
        (GET /collections/{id}/items/{fid}/attachments/{aid}/file) is
        gated by the shell's OIDC audience (CORE_OIDC_AUDIENCE), which an
        MCP-audienced token (CORE_MCP_AUDIENCE) never satisfies — same
        reason ItemRead.thumbnailUrl is omitted for MCP callers (SP-42,
        F-coeur-federation-08). Deliberately absent from the copilot's
        ALLOWED_MCP_TOOL_NAMES (app/copilot/tools_allowlist.py).

        Returns a JSON-encoded array (rather than a typed list[dict]) because
        FastMCP's unstructured-content conversion fragments a returned Python
        list into one content block per element instead of one block holding
        the whole array — verified empirically against mcp==1.29.1, not
        assumed. structured_output=False avoids a second, incompatible
        failure mode: the structured-output path would otherwise try to
        validate this pre-serialized string against a list[dict] schema."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_collection_read(session, user=user, collection_id=collectionId)
            rows = attachments_repo.list_attachments(
                session,
                tenant_id=user.tenant_id,
                collection_id=collectionId,
                fid=fid,
                field_key=fieldKey,
            )
            return json.dumps(
                [
                    {
                        "id": a.id,
                        "fieldKey": a.field_key,
                        "filename": a.filename,
                        "contentType": a.content_type,
                        "byteSize": a.byte_size,
                    }
                    for a in rows
                ]
            )

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
            return _without_thumbnail_urls(
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
            user = _resolve_actor(session, access_token)
            return _without_thumbnail_urls(
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
            user = _resolve_actor(session, access_token)
            _require_access(session, user=user, item_id=itemId, action="read")
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=itemId, current_user_id=user.id
            )
            if result is None:
                raise ValueError("item not found")
            return _without_thumbnail_url(result)

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
            _require_kind_unchanged(existing.kind, config.kind)
            _require_config_privilege(session, config, user=user)
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            result = configs_repo.update_config(
                session, existing.id, config, tenant_id=user.tenant_id
            )
            if result is None:
                raise ValueError("config not found")
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.update",
                object_type="config",
                object_id=existing.id,
                payload={},
            )
            return result

    @server.tool()
    async def create_item(
        ctx: Context,
        kind: Literal["app", "dashboard"],
        title: str,
        config: BuilderConfig,
    ) -> ItemRead:
        """Create a new app or dashboard — mirrors POST /configs, including
        its privilege guard (apps.manage, app.roles.kind_registry::
        privilege_for_kind). The item's owner is always the
        authenticated caller; there is no owner parameter to accept from
        the agent."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            _require_config_privilege(session, config, user=user)
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            item = items_repo.create_item(
                session,
                tenant_id=user.tenant_id,
                owner_id=user.id,
                resource_type=kind,
                title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.create",
                object_type="item",
                object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=config_result.id,
                payload={"title": title, "kind": kind},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=item.id, current_user_id=user.id
            )
            assert result is not None  # just created it, in the same transaction
            return _without_thumbnail_url(result)

    @server.tool()
    async def create_form_app(
        ctx: Context,
        collectionId: str,
        title: str | None = None,
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
            except TableNotFound as exc:
                raise ValueError("collection backing table not found") from exc
            except UnsupportedTable as exc:
                raise ValueError(exc.reason) from exc
            schema = table_info_to_schema(info)
            include_form = form_app.can_write_collection(session, user=user, col=col)
            config = form_app.build_config(
                collection_id=collectionId,
                schema=schema,
                include_form=include_form,
            )
            _require_config_privilege(session, config, user=user)
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            item = items_repo.create_item(
                session,
                tenant_id=user.tenant_id,
                owner_id=user.id,
                resource_type="app",
                title=title or f"Application {col.title}",
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.create",
                object_type="item",
                object_id=item.id,
                payload={"title": item.title, "collectionId": collectionId},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=config_result.id,
                payload={"collectionId": collectionId, "includeForm": include_form},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=item.id, current_user_id=user.id
            )
            assert result is not None
            return _without_thumbnail_url(result)

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
                source=source,
                collectionId=collectionId,
                arcgisItemId=arcgisItemId,
                columns=columns or {},
                timeField=timeField,
                reactsToExtent=reactsToExtent,
            )
            config = BuilderConfig(version=1, kind="dataset", dataset=payload)
            _require_config_privilege(session, config, user=user)
            _validate_dataset(session, config, user=user)
            item = items_repo.create_item(
                session,
                tenant_id=user.tenant_id,
                owner_id=user.id,
                resource_type="dataset",
                title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.create",
                object_type="item",
                object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=config_result.id,
                payload={"title": title, "kind": "dataset"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=item.id, current_user_id=user.id
            )
            assert result is not None
            return _without_thumbnail_url(result)

    @server.tool()
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
            user = _resolve_actor(session, access_token)
            payload = BookmarkPayload(
                appId=appId,
                pageId=pageId,
                timeRange=timeRange,
                extent=extent,
                crossFilter=crossFilter or {},
            )
            config = BuilderConfig(version=1, kind="bookmark", bookmark=payload)
            _require_config_privilege(session, config, user=user)
            _validate_bookmark(session, config, user=user)
            item = items_repo.create_item(
                session,
                tenant_id=user.tenant_id,
                owner_id=user.id,
                resource_type="bookmark",
                title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.create",
                object_type="item",
                object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=config_result.id,
                payload={"title": title, "kind": "bookmark"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=item.id, current_user_id=user.id
            )
            assert result is not None  # just created it, in the same transaction
            return _without_thumbnail_url(result)

    @server.tool()
    async def run_analytics_query(
        ctx: Context, datasetId: str, query: AggregateRequestBody
    ) -> dict:
        """Run a structured aggregate query against a dataset (source
        collection or arcgis) — mirrors POST /collections/{id}/aggregate and
        POST /datasets/{id}/arcgis/aggregate, same query contract
        (groupBy/split/measures/filters/bbox/bucket/bins), same permissions.
        Never fabricates SQL (A19). SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = _require_collection_read(
                    session, user=user, collection_id=payload.collectionId
                )
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound as exc:
                    raise ValueError("collection backing table not found") from exc
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason) from exc
                conn = features_routes.get_duckdb_connection_factory()()
                try:
                    try:
                        category_key, rows = run_collection_aggregate(
                            conn,
                            base_uri=features_routes.get_analytics_base_uri(),
                            tenant_id=col.tenant_id,
                            collection_id=col.id,
                            table_info=info,
                            request=query,
                        )
                    except UnknownAggregateField as exc:
                        raise ValueError(f"{exc.field}: {exc.message}") from exc
                finally:
                    conn.close()
                return {"categoryKey": category_key, "rows": rows}

            assert payload.arcgisItemId is not None
            if query.bucket is not None or query.split is not None or query.bins is not None:
                raise ValueError("bucket/split/bins are not supported for arcgis-sourced datasets")
            external_url = _resolve_arcgis_external_url(
                session, user=user, dataset_item_id=datasetId
            )
            group_by = (
                query.groupBy
                if isinstance(query.groupBy, list)
                else ([query.groupBy] if query.groupBy else [])
            )
            measures_in = query.measures or [
                AggregateMeasure(field=query.field, agg=query.agg, label="value")
            ]
            measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
            try:
                params = live_query.translate_aggregate_query(
                    group_by=group_by,
                    measures=measures,
                    filters=query.filters,
                    bbox=query.bbox,
                )
            except live_query.ArcgisQueryError as exc:
                raise ValueError(f"{exc.field}: {exc.message}") from exc
            client = harvest_routes.get_arcgis_http_client()
            try:
                raw = live_query.fetch_query(client, external_url, params)
            except EgressBlockedError as exc:
                raise ValueError("arcgis service unavailable") from exc
            except httpx.HTTPError as exc:
                raise ValueError("arcgis service unavailable") from exc
            finally:
                client.close()
            category_key, rows = live_query.aggregate_response(
                raw, group_by=group_by, measures=measures
            )
            return {"categoryKey": category_key, "rows": rows}

    @server.tool()
    async def explain_dataset(ctx: Context, datasetId: str) -> dict:
        """Describe a dataset's queryable fields before calling
        run_analytics_query — author metadata (columns/timeField/
        reactsToExtent) plus introspected field name+type, so an agent
        doesn't have to guess a groupBy/measure field name. No stats, no
        sampling. SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=datasetId)
            assert item is not None
            base = {
                "title": item.title,
                "source": payload.source,
                "timeField": payload.timeField,
                "reactsToExtent": payload.reactsToExtent,
                "columns": {k: v.model_dump() for k, v in payload.columns.items()},
            }

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = _require_collection_read(
                    session, user=user, collection_id=payload.collectionId
                )
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound as exc:
                    raise ValueError("collection backing table not found") from exc
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason) from exc
                schema = table_info_to_schema(info)
                fields = [{"name": f["name"], "type": f["type"]} for f in schema["fields"]]
                return {**base, "fields": fields}

            external_url = _resolve_arcgis_external_url(
                session, user=user, dataset_item_id=datasetId
            )
            client = harvest_routes.get_arcgis_http_client()
            try:
                response = client.get(f"{external_url}?f=json")
                response.raise_for_status()
            except EgressBlockedError as exc:
                raise ValueError("arcgis service unavailable") from exc
            except httpx.HTTPError as exc:
                raise ValueError("arcgis service unavailable") from exc
            finally:
                client.close()
            data = response.json()
            raw_fields = data.get("fields") if isinstance(data, dict) else None
            fields = [
                {"name": f.get("name"), "type": f.get("type")}
                for f in (raw_fields or [])
                if isinstance(f, dict)
            ]
            return {**base, "fields": fields}

    if is_etl_enabled():

        @server.tool()
        async def create_pipeline(
            ctx: Context,
            title: str,
            nodes: list[PipelineNode],
            edges: list[PipelineEdge],
        ) -> ItemRead:
            """Create a Pipeline (reader/transform/writer graph) — mirrors
            POST /configs with kind="pipeline". Only registered when
            CORE_ETL_ENABLED is on. SP-15a."""
            if is_read_only_mode():
                raise ValueError("Mode démo : lecture seule, écritures désactivées.")
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                payload = PipelinePayload(nodes=nodes, edges=edges)
                config = BuilderConfig(version=1, kind="pipeline", pipeline=payload)
                _require_config_privilege(session, config, user=user)
                _validate_pipeline(session, config, user=user)
                item = items_repo.create_item(
                    session,
                    tenant_id=user.tenant_id,
                    owner_id=user.id,
                    resource_type="pipeline",
                    title=title,
                )
                config_result = configs_repo.create_config(
                    session, config, item_id=item.id, tenant_id=user.tenant_id
                )
                write_audit(
                    session,
                    tenant_id=user.tenant_id,
                    actor_id=user.id,
                    actor_kind="agent",
                    action="item.create",
                    object_type="item",
                    object_id=item.id,
                    payload={"title": title},
                )
                write_audit(
                    session,
                    tenant_id=user.tenant_id,
                    actor_id=user.id,
                    actor_kind="agent",
                    action="config.create",
                    object_type="config",
                    object_id=config_result.id,
                    payload={"title": title, "kind": "pipeline"},
                )
                result = items_repo.get_item(
                    session, tenant_id=user.tenant_id, item_id=item.id, current_user_id=user.id
                )
                assert result is not None
                return _without_thumbnail_url(result)

        @server.tool()
        async def run_pipeline(ctx: Context, pipelineId: str) -> dict:
            """Defer a run of a Pipeline — mirrors POST /pipelines/{id}/run.
            Only registered when CORE_ETL_ENABLED is on. SP-15a."""
            if is_read_only_mode():
                raise ValueError("Mode démo : lecture seule, écritures désactivées.")
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                config = configs_repo.get_config_by_item(session, pipelineId)
                if config is None or config.config.kind != "pipeline":
                    raise ValueError("pipeline not found")
                facts = items_repo.get_access_facts(
                    session, tenant_id=user.tenant_id, item_id=pipelineId
                )
                if facts is None or not can(session, user_id=user.id, action="write", item=facts):
                    raise ValueError("pipeline not found")
                try:
                    pipelines_service.require_data_manage_if_pipeline_writes_dataset(
                        session, user, config
                    )
                except HTTPException as exc:
                    raise ValueError(exc.detail) from exc
                run = pipelines_repo.create_run(
                    session,
                    tenant_id=user.tenant_id,
                    pipeline_item_id=pipelineId,
                )
                write_audit(
                    session,
                    tenant_id=user.tenant_id,
                    actor_id=user.id,
                    actor_kind="agent",
                    action="pipeline.run",
                    object_type="pipeline_run",
                    object_id=run.id,
                    payload={"pipelineItemId": pipelineId},
                )
                session.commit()
                run_pipeline_task.defer(run_id=run.id, tenant_id=user.tenant_id)
                return {"runId": run.id}

        @server.tool()
        async def explain_pipeline(ctx: Context, pipelineId: str) -> dict:
            """Describe a Pipeline's graph (nodes/ops/edges) without running
            it — mirrors explain_dataset's shape. Only registered when
            CORE_ETL_ENABLED is on. SP-15a."""
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                config = configs_repo.get_config_by_item(session, pipelineId)
                if config is None or config.config.kind != "pipeline":
                    raise ValueError("pipeline not found")
                facts = items_repo.get_access_facts(
                    session, tenant_id=user.tenant_id, item_id=pipelineId
                )
                if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                    raise ValueError("pipeline not found")
                item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=pipelineId)
                if item is None:
                    raise ValueError("pipeline not found")
                payload = config.config.pipeline
                assert payload is not None
                return {
                    "title": item.title,
                    "nodes": [
                        {"id": n.id, "kind": n.kind, "op": n.op, "title": n.title}
                        for n in payload.nodes
                    ],
                    "edges": [{"from": e.from_, "to": e.to} for e in payload.edges],
                    "refreshPolicy": payload.refreshPolicy.model_dump()
                    if payload.refreshPolicy
                    else None,
                }

    @server.tool()
    async def explain_alert_rule(ctx: Context, alertRuleId: str) -> dict:
        """Describe an AlertRule (dataset, condition, schedule, current
        state) without evaluating it — mirrors explain_pipeline's shape.
        Registered unconditionally (no capability flag). SP-16b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, alertRuleId)
            if config is None or config.config.kind != "alert":
                raise ValueError("alert rule not found")
            facts = items_repo.get_access_facts(
                session, tenant_id=user.tenant_id, item_id=alertRuleId
            )
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("alert rule not found")
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=alertRuleId)
            if item is None:
                raise ValueError("alert rule not found")
            payload = config.config.alert
            assert payload is not None
            latest = alerts_repo.get_latest_evaluation(
                session,
                tenant_id=user.tenant_id,
                alert_rule_item_id=alertRuleId,
            )
            return {
                "title": item.title,
                "datasetItemId": payload.datasetItemId,
                "condition": payload.condition.expr,
                "refreshPolicy": payload.refreshPolicy.model_dump(),
                "channels": [c.kind for c in payload.channels],
                "currentState": latest.state if latest else "pending",
            }

    @server.tool()
    async def explain_report_schedule(ctx: Context, reportScheduleId: str) -> dict:
        """Describe a ReportSchedule (target bookmark, cron, channels, last
        run) without triggering it — mirrors explain_alert_rule's shape.
        Registered unconditionally (no capability flag). SP-17b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, reportScheduleId)
            if config is None or config.config.kind != "report":
                raise ValueError("report schedule not found")
            facts = items_repo.get_access_facts(
                session, tenant_id=user.tenant_id, item_id=reportScheduleId
            )
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("report schedule not found")
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=reportScheduleId)
            if item is None:
                raise ValueError("report schedule not found")
            payload = config.config.report
            assert payload is not None
            latest = reports_repo.get_latest_run(
                session,
                tenant_id=user.tenant_id,
                report_item_id=reportScheduleId,
            )
            return {
                "title": item.title,
                "bookmarkItemId": payload.bookmarkItemId,
                "refreshPolicy": payload.refreshPolicy.model_dump(),
                "channels": [c.kind for c in payload.channels],
                "lastRunAt": latest.created_at.isoformat() if latest else None,
            }

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
                session,
                tenant_id=user.tenant_id,
                item_id=itemId,
                shares=[(g.groupId, g.role) for g in sharing.groups],
            )
            if not ok:
                raise ValueError("group not found")
            items_repo.set_is_public(
                session, tenant_id=user.tenant_id, item_id=itemId, is_public=sharing.public
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="item.share",
                object_type="item",
                object_id=itemId,
                payload={
                    "public": sharing.public,
                    "groups": [g.model_dump() for g in sharing.groups],
                },
            )

    @server.resource("schema://app-config")
    def app_config_schema() -> dict:
        """JSON Schema for AppConfig/DashboardConfig — validate before
        calling create_item or save_app_config."""
        return BuilderConfig.model_json_schema()
