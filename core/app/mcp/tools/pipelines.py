# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine pipelines : create_pipeline, run_pipeline,
explain_pipeline (SP-43 Étape 8 — extrait de app/mcp/tools.py). Montés
uniquement quand CORE_ETL_ENABLED est actif — même garde que les routes
REST /pipelines/* (app/pipelines/routes.py, monté par app.main), vérifiée
à l'enregistrement des tools (pas par requête). create_pipeline réutilise
app.configs.service.create_config_service ; run_pipeline réutilise
app.pipelines.service.run_pipeline_service, partagée avec
POST /pipelines/{id}/run — actor_kind="agent" ici vs "user" côté route,
écart de design volontaire vérifié par tests/test_mcp_rest_parity.py.
explain_pipeline réutilise require_pipeline_access/require_pipeline_config
de la même couche de service (ordre des vérifications légèrement
renormalisé : accès avant kind, comme la route REST, plutôt que kind avant
accès comme avant ce refactor — aucune différence de comportement
observable, les deux ordres produisent "pipeline not found" pour toute
combinaison item inexistant/illisible/mauvais kind)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_etl_enabled, is_read_only_mode
from app.configs.schemas import BuilderConfig, PipelineEdge, PipelineNode, PipelinePayload
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
from app.pipelines.jobs import run_pipeline_task
from app.pipelines.service import require_pipeline_access, require_pipeline_config
from app.pipelines.service import run_pipeline_service as _run_pipeline_service


def register(server: FastMCP, session_factory) -> None:
    if not is_etl_enabled():
        return

    @server.tool()
    @write_tool
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
            user = resolve_actor(session, access_token)
            payload = PipelinePayload(nodes=nodes, edges=edges)
            config = BuilderConfig(version=1, kind="pipeline", pipeline=payload)
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
                payload={"title": title, "kind": "pipeline"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None
            return without_thumbnail_url(result)

    @server.tool()
    @write_tool
    async def run_pipeline(ctx: Context, pipelineId: str) -> dict:
        """Defer a run of a Pipeline — mirrors POST /pipelines/{id}/run.
        Only registered when CORE_ETL_ENABLED is on. SP-15a."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)

            def defer_task(run_id: str, tenant_id: str) -> None:
                run_pipeline_task.defer(run_id=run_id, tenant_id=tenant_id)

            try:
                run_id = _run_pipeline_service(
                    session,
                    user=user,
                    item_id=pipelineId,
                    defer_task=defer_task,
                    actor_kind="agent",
                )
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            return {"runId": run_id}

    @server.tool()
    async def explain_pipeline(ctx: Context, pipelineId: str) -> dict:
        """Describe a Pipeline's graph (nodes/ops/edges) without running
        it — mirrors explain_dataset's shape. Only registered when
        CORE_ETL_ENABLED is on. SP-15a."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                require_pipeline_access(session, user=user, item_id=pipelineId, action="read")
                config = require_pipeline_config(session, pipelineId)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
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
