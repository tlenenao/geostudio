# SPDX-License-Identifier: Apache-2.0
"""PoC d'audit c01 (MCP) — démontre un comportement actuel, ne corrige rien.

    cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . \
        ../docs/revue/audit-2026-09-29/c01/poc/test_c01_mcp_poc.py -q -p no:cacheprovider
"""

import os

os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
os.environ.setdefault("CORE_ENV", "development")

from mcp.server.fastmcp import FastMCP  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.audit.models import AuditLog  # noqa: E402
from app.mcp.tools import READ_ONLY_TOOLS, register_tools  # noqa: E402
from tests.test_mcp_read_only_mode import (  # noqa: E402,F401
    READ_ONLY_MESSAGE,
    app_client,
    call_tool_raw,
)


def test_run_alert_rule_has_no_read_only_guard(app_client, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        _run_alert_rule_scenario(app_client)


def _run_alert_rule_scenario(app_client):  # noqa: F811
    # create_alert_rule porte le garde : message « lecture seule » renvoyé
    created = call_tool_raw(
        app_client,
        "create_alert_rule",
        {
            "title": "x",
            "datasetItemId": "nope",
            "query": {},
            "condition": {},
            "refreshPolicy": {},
            "channels": [],
        },
    )
    assert created.get("isError") and READ_ONLY_MESSAGE in created["content"][0]["text"]
    # run_alert_rule, outil qui ÉCRIT (alert_evaluations + defer d'un job qui
    # envoie webhook/email), n'a pas ce garde : il va jusqu'à la résolution
    # de l'item et répond « not found » au lieu de refuser en mode démo.
    ran = call_tool_raw(app_client, "run_alert_rule", {"alertRuleId": "nope"})
    assert ran.get("isError")
    text = ran["content"][0]["text"]
    assert READ_ONLY_MESSAGE not in text
    assert "alert rule not found" in text


def test_alert_write_tools_absent_from_write_inventory(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    register_tools(FastMCP("c01-inventory"), session_factory=None)
    assert "create_alert_rule" not in READ_ONLY_TOOLS
    assert "run_alert_rule" not in READ_ONLY_TOOLS


def test_mcp_read_tools_leave_no_audit_trail(app_client):  # noqa: F811
    with app_client:
        _audit_scenario(app_client)


def _audit_scenario(app_client):  # noqa: F811
    Session = app_client.session_factory
    with Session() as s:
        before = s.scalar(select(func.count()).select_from(AuditLog))
    for name, args in (("list_items", {}), ("whoami", {}), ("search_collections", {"q": "x"})):
        result = call_tool_raw(app_client, name, args)
        assert not result.get("isError"), (name, result)
    with Session() as s:
        after = s.scalar(select(func.count()).select_from(AuditLog))
    assert after == before  # aucune ligne audit_log pour 3 appels d'outil MCP
