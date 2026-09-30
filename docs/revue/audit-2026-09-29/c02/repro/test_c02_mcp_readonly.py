# SPDX-License-Identifier: Apache-2.0
"""Repro c02 : run_alert_rule (MCP) n'a pas de garde is_read_only_mode(), alors que
POST /v1/alerts/{id}/evaluate est bloqué par le middleware read_only_guard."""

from tests.test_mcp_tools_alert import _seed_alert_rule, app_client  # noqa: F401
from tests.test_mcp_tools_create import call_tool


def test_c02_run_alert_rule_writes_in_read_only_mode(app_client, monkeypatch):  # noqa: F811
    client, Session, tenant_id, user_id = app_client
    alert_item_id, _ = _seed_alert_rule(Session, tenant_id=tenant_id, owner_id=user_id)
    from app.alerts import jobs as alerts_jobs

    deferred = []
    monkeypatch.setattr(alerts_jobs.evaluate_alert_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with client:
        rest = client.post(
            f"/v1/alerts/{alert_item_id}/evaluate", headers={"Authorization": "Bearer mock:x"}
        )
        result = call_tool(client, "run_alert_rule", {"alertRuleId": alert_item_id})
    print("REST evaluate in read-only mode ->", rest.status_code)
    print("MCP run_alert_rule in read-only mode ->", result, "deferred:", len(deferred))
    assert rest.status_code == 403
    assert result["created"] is True and len(deferred) == 1
