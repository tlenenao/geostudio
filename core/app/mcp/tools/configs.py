# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine configs : get_app_config, save_app_config,
create_item, create_form_app (SP-43 Étape 8 — extrait de
app/mcp/tools.py). create_item et create_form_app réutilisent
app.configs.service.create_config_service, partagée avec POST /configs
(app/configs/routes.py). save_app_config reste un tool autonome —
**écart pré-existant, non corrigé par SP-43** : contrairement à
PUT /configs/by-item/{id} (app/configs/routes.py::update_config_by_item),
save_app_config n'exécute PAS les 7 validateurs par kind
(dataset/bookmark/pipeline/alert/report/tileset3d/terrain3d) ni les 2
gardes de capacité (ETL/export) — seulement le garde de privilège et la
portée d'extension. Documenté ici plutôt que "corrigé" au passage (règle
explicite du plan SP-43, spec §6) ; candidat de backlog séparé."""

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
from app.configs.extension_permissions import (
    ExtensionPermissionError,
    validate_extension_permissions,
)
from app.configs.repository import ConfigRead
from app.configs.routes import _require_kind_matches_existing
from app.configs.schemas import BuilderConfig
from app.configs.service import create_config_service
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
            user = resolve_actor(session, access_token)
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
