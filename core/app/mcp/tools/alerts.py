# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine alerts : explain_alert_rule (SP-43 Étape 8 — extrait
de app/mcp/tools.py), create_alert_rule/run_alert_rule (SP-53, GAP-48).

create_alert_rule mirrors POST /configs kind="alert" (app/alerts/routes.py
docstring: "Create/update/delete of the rule itself are handled entirely by
the generic /configs routes") — décalque quasi exact de
mcp/tools/pipelines.py::create_pipeline, kind="alert" au lieu de
"pipeline". run_alert_rule n'a aucun équivalent exact de
POST /pipelines/{id}/run : une alerte s'exécute normalement par balayage
périodique (sweep_alert_rules_task, app/alerts/jobs.py) jamais par une
route REST "exécuter maintenant" — ce tool reproduit, pour une seule
règle, exactement la séquence que le balayage fait pour toutes les
règles dues (create_evaluation -> commit -> defer), sans repasser par le
balayage cross-tenant. Les deux tools sont montés inconditionnellement
(pas de garde CORE_ETL_ENABLED, comme les routes REST /alerts/*)."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.alerts import jobs as alerts_jobs
from app.alerts import repository as alerts_repo
from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.configs import repository as configs_repo
from app.configs.schemas import AlertRulePayload, BuilderConfig
from app.configs.service import create_config_service
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.items.schemas import ItemRead
from app.mcp.tools.identity import (
    http_exception_to_value_error,
    resolve_actor,
    without_thumbnail_url,
)
from app.sharing.authorization import can


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def create_alert_rule(
        ctx: Context,
        title: str,
        datasetItemId: str,
        query: dict,
        condition: dict,
        refreshPolicy: dict,
        channels: list[dict],
        messageTemplate: str = "Alert {ruleName}: value={value} ({state})",
    ) -> ItemRead:
        """Create an AlertRule — mirrors POST /configs with kind="alert".
        Registered unconditionally (alerts are not gated by
        CORE_ETL_ENABLED, unlike pipelines). SP-53."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = AlertRulePayload(
                datasetItemId=datasetItemId,
                query=query,
                condition=condition,
                refreshPolicy=refreshPolicy,
                channels=channels,
                messageTemplate=messageTemplate,
            )
            config = BuilderConfig(version=1, kind="alert", alert=payload)
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
                payload={"title": title, "kind": "alert"},
            )
            result = items_repo.get_item(
                session, tenant_id=user.tenant_id, item_id=created.item.id, current_user_id=user.id
            )
            assert result is not None
            return without_thumbnail_url(result)

    @server.tool()
    async def run_alert_rule(ctx: Context, alertRuleId: str) -> dict:
        """Defer an immediate evaluation of an AlertRule — mirrors, for a
        single rule, what sweep_alert_rules_task does for all due rules.
        No REST route equivalent exists (evaluation is periodic-only via
        REST); this is the MCP-only manual trigger. SP-53."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, alertRuleId)
            if config is None or config.config.kind != "alert":
                raise ValueError("alert rule not found")
            facts = items_repo.get_access_facts(
                session, tenant_id=user.tenant_id, item_id=alertRuleId
            )
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("alert rule not found")
            evaluation = alerts_repo.create_evaluation(
                session, tenant_id=user.tenant_id, alert_rule_item_id=alertRuleId
            )
            # Commit avant de déférer — même raison que sweep_alert_rules_task.
            session.commit()
            alerts_jobs.evaluate_alert_task.defer(
                evaluation_id=evaluation.id, tenant_id=user.tenant_id
            )
            return {"evaluationId": evaluation.id}

    @server.tool()
    async def explain_alert_rule(ctx: Context, alertRuleId: str) -> dict:
        """Describe an AlertRule (dataset, condition, schedule, current
        state) without evaluating it — mirrors explain_pipeline's shape.
        Registered unconditionally (no capability flag). SP-16b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
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
