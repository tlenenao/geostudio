# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine alerts : explain_alert_rule (SP-43 Étape 8 — extrait
de app/mcp/tools.py). Aucune route REST équivalente (introspection MCP
pure) — pas de couche de service à créer."""

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.mcp.tools.identity import resolve_actor
from app.sharing.authorization import can


def register(server: FastMCP, session_factory) -> None:
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
