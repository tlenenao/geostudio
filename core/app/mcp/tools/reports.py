# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine reports : explain_report_schedule (SP-43 Étape 8 —
extrait de app/mcp/tools.py). Aucune route REST équivalente (introspection
MCP pure) — pas de couche de service à créer."""

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.configs import repository as configs_repo
from app.db import request_scoped_session
from app.items import repository as items_repo
from app.mcp.tools.identity import resolve_actor
from app.reports import repository as reports_repo
from app.sharing.authorization import can


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def explain_report_schedule(ctx: Context, reportScheduleId: str) -> dict:
        """Describe a ReportSchedule (target bookmark, cron, channels, last
        run) without triggering it — mirrors explain_alert_rule's shape.
        Registered unconditionally (no capability flag). SP-17b."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
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
