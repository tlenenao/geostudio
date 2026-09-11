# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine configs : get_app_config, save_app_config,
create_item, create_form_app (SP-43 Étape 8 — extrait de
app/mcp/tools.py). create_item et create_form_app réutilisent
app.configs.service.create_config_service, partagée avec POST /configs
(app/configs/routes.py). save_app_config reste un tool autonome, mais
exécute désormais (REV-174) exactement la même séquence de gardes de
capacité + validateurs par kind que PUT /configs/by-item/{id}
(app/configs/routes.py::update_config_by_item), importés depuis les mêmes
modules source — jamais dupliqués localement : les 2 gardes de capacité
(_require_etl_enabled_for_pipeline, _require_export_enabled_for_report)
depuis app.configs.service (seule source de vérité depuis la revue finale
SP-43), les 7 validateurs par kind depuis leurs modules
app.configs.<kind>_validation respectifs, comme routes.py."""

from typing import Literal

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs import repository as configs_repo
from app.configs.alert_validation import validate_alert_payload as _validate_alert_payload
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
from app.configs.extension_permissions import (
    ExtensionPermissionError,
    validate_extension_permissions,
)
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
from app.configs.report_validation import validate_report_payload as _validate_report_payload
from app.configs.repository import ConfigRead
from app.configs.routes import _require_kind_matches_existing
from app.configs.schemas import BuilderConfig
from app.configs.service import (
    _require_etl_enabled_for_pipeline,
    _require_export_enabled_for_report,
    create_config_service,
)
from app.configs.terrain3d_validation import (
    validate_terrain3d_payload as _validate_terrain3d_payload,
)
from app.configs.tileset3d_validation import (
    validate_tileset3d_payload as _validate_tileset3d_payload,
)
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.items.schemas import ItemRead
from app.mcp import form_app
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    require_access,
    require_collection_read,
    resolve_actor,
    without_thumbnail_url,
)
from app.mcp.tools.write_tools import write_tool
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.users.models import User


def _require_config_privilege(session, config: BuilderConfig, *, user: User) -> None:
    """SP-42/F-securite-autorisation-01 : mirrors app.configs.routes'
    kind->privilege guard, raises ValueError instead of HTTPException (no
    HTTP status channel in an MCP tool body)."""
    try:
        require_privilege(session, user, privilege_for_kind(config.kind))
    except HTTPException as exc:
        raise http_exception_to_value_error(exc) from exc


def _validate_extension_scope(session, config: BuilderConfig, *, tenant_id: str) -> None:
    try:
        validate_extension_permissions(session, config, tenant_id=tenant_id)
    except ExtensionPermissionError as err:
        raise ValueError(str(err)) from err


def _require_kind_unchanged(existing_kind: str, submitted_kind: str) -> None:
    """SP-42, revue des lots de correctifs 2/3bis (point 3) : mirrors
    app.configs.routes._require_kind_matches_existing for save_app_config,
    the only MCP tool that updates an already-existing config."""
    try:
        _require_kind_matches_existing(existing_kind, submitted_kind)
    except HTTPException as exc:
        raise http_exception_to_value_error(exc) from exc


def _require_capabilities_for_save(config: BuilderConfig) -> None:
    """REV-174 : mirrors the 2 instance-capability guards that
    update_config_by_item runs before writing (_require_etl_enabled_for_pipeline,
    _require_export_enabled_for_report — both imported from app.configs.service,
    their sole source of truth since the SP-43 final review), which
    save_app_config used to skip entirely."""
    try:
        _require_etl_enabled_for_pipeline(config)
        _require_export_enabled_for_report(config)
    except HTTPException as exc:
        raise http_exception_to_value_error(exc) from exc


def _validate_payload_by_kind(session, config: BuilderConfig, *, user: User) -> None:
    """REV-174 : mirrors the 7 per-kind payload validators that
    update_config_by_item runs before writing, in the same order, imported
    from the same modules as app.configs.routes — save_app_config used to
    skip all 7, letting an MCP agent write a dataset pointing at an unreadable
    collection, a pipeline/report bypassing its capability guard's sibling
    structural checks, etc."""
    try:
        _validate_dataset_payload(session, config, user=user)
        _validate_bookmark_payload(session, config, user=user)
        _validate_pipeline_payload(session, config, user=user)
        _validate_alert_payload(session, config, user=user)
        _validate_report_payload(session, config, user=user)
        _validate_tileset3d_payload(session, config, user=user)
        _validate_terrain3d_payload(session, config, user=user)
    except HTTPException as exc:
        raise http_exception_to_value_error(exc) from exc


def _require_create_item_kind_matches_config(kind: str, config_kind: str) -> None:
    """SP-43, revue de la Tâche 9 (1 Important, trouvé en revue) : `kind`
    (paramètre du tool `create_item`, restreint par son type à
    Literal["app", "dashboard"]) et `config.kind` (le Literal bien plus
    large de BuilderConfig — 11 valeurs, dont "pipeline"/"report"/...)
    n'étaient reliés par AUCUNE vérification après l'extraction vers
    create_config_service : celle-ci calcule `resource_type` et choisit ses
    gardes/validateurs depuis `config.kind` seul, jamais depuis `kind`. Sans
    ce garde, un appelant MCP pouvait satisfaire la contrainte de type du
    tool avec kind="app" tout en soumettant
    config={"kind": "pipeline", "pipeline": {...}} : l'item créé aurait
    resource_type="pipeline" (pas "app"), et la ligne d'audit écrite par ce
    tool (payload={"kind": kind}) aurait décrit un kind différent de celui
    réellement créé — un défaut d'intégrité d'audit dans une zone sensible
    à la sécurité, introduit PENDANT ce découpage (contrairement à l'écart
    pré-existant de save_app_config documenté plus haut, celui-ci est
    nouveau et devait être corrigé, pas seulement documenté). Vérifié
    qu'aucun usage légitime ne fait diverger les deux : ce tool ne crée que
    des apps/dashboards (docstring de create_item), et les tests existants
    (tests/test_mcp_tools_create.py) soumettent toujours kind==config.kind.
    """
    if config_kind != kind:
        raise ValueError(f"create_item: config.kind ('{config_kind}') must match kind ('{kind}')")


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def get_app_config(ctx: Context, itemId: str) -> ConfigRead:
        """Get the app/dashboard config for an item — mirrors GET /configs/by-item/{id}."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=itemId, action="read")
            result = configs_repo.get_config_by_item(session, itemId)
            if result is None:
                raise ValueError("config not found")
            return result

    @server.tool()
    @write_tool
    async def save_app_config(ctx: Context, itemId: str, config: BuilderConfig) -> ConfigRead:
        """Save (and version) the app/dashboard config for an item — mirrors
        PUT /configs/by-item/{id}."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=itemId, action="write")
            existing = configs_repo.get_config_by_item(session, itemId)
            if existing is None:
                raise ValueError("config not found")
            _require_kind_unchanged(existing.kind, config.kind)
            _require_config_privilege(session, config, user=user)
            _require_capabilities_for_save(config)
            _validate_extension_scope(session, config, tenant_id=user.tenant_id)
            _validate_payload_by_kind(session, config, user=user)
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
    @write_tool
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
            user = resolve_actor(session, access_token)
            _require_create_item_kind_matches_config(kind, config.kind)
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
                payload={"title": title, "kind": kind},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None  # just created it, in the same transaction
            return without_thumbnail_url(result)

    @server.tool()
    @write_tool
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
            user = resolve_actor(session, access_token)
            col = require_collection_read(session, user=user, collection_id=collectionId)
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
            resolved_title = title or f"Application {col.title}"
            try:
                created = create_config_service(session, config, title=resolved_title, user=user)
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
                payload={"title": created.item.title, "collectionId": collectionId},
            )
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="config.create",
                object_type="config",
                object_id=created.config.id,
                payload={"collectionId": collectionId, "includeForm": include_form},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None
            return without_thumbnail_url(result)
