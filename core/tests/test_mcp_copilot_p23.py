# SPDX-License-Identifier: Apache-2.0
"""P23 : MCP et copilote — boucle asyncio libre, bornes, erreurs structurées,
audit, parité REST/MCP, pannes du fournisseur LLM, confirmation d'écriture."""

import asyncio
import json
import time

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.audit.models import AuditLog
from app.copilot.llm_provider import LLMNotConfiguredError, LLMTurn, ToolCall, get_llm_provider
from app.mcp.tools import register_tools
from app.mcp.tools.harness import instrument
from tests.test_copilot_routes import client  # noqa: F401
from tests.test_mcp_tools_create import (  # noqa: F401,F811
    app_client,
    call_tool_expecting_error,
    call_tool_raw,
)


def _turn(c, **over):
    body = {
        "itemId": "1",
        "message": "salut",
        "history": [],
        "mcpToken": "x",
        "currentConfig": {},
        "clientTools": [],
    }
    return c.post("/v1/copilot/turn", json={**body, **over})


# --- P23.01 : un tool lent ne gèle pas la boucle (recouvrement d'intervalles) ---
def test_blocking_tool_body_does_not_freeze_the_event_loop():
    server = FastMCP("t")
    tools = instrument(server, None)
    window: list[float] = []

    @tools.tool()
    async def slow() -> str:
        window.append(time.monotonic())
        time.sleep(0.4)  # I/O synchrone typique d'un corps de tool
        window.append(time.monotonic())
        return "ok"

    ticks: list[float] = []

    async def ticker():
        for _ in range(12):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.03)

    async def main():
        await asyncio.gather(server.call_tool("slow", {}), ticker())

    asyncio.run(main())
    during = [x for x in ticks if window[0] < x < window[1]]
    assert len(during) >= 5  # la boucle a continué de tourner pendant le tool


# --- P23.03/08 : bornes comme le REST, jamais de SQL brut ---
@pytest.mark.parametrize(
    "tool,args",
    [
        ("list_items", {"page": 0}),
        ("list_items", {"pageSize": 0}),
        ("search_catalog", {"page": -1}),
        ("search_collections", {"page": -3}),
        ("query_features", {"collectionId": "x", "limit": -1}),
        ("query_features", {"collectionId": "x", "offset": -1}),
    ],
)
def test_out_of_bounds_pagination_is_a_validation_error(app_client, tool, args):  # noqa: F811
    with app_client:
        text = call_tool_expecting_error(app_client, tool, args)
    assert "SELECT" not in text and "parameters" not in text


# --- P23.04 : statut porté par l'erreur d'outil ---
def test_tool_error_carries_the_http_status(app_client):  # noqa: F811
    with app_client:
        text = call_tool_expecting_error(app_client, "get_item", {"itemId": "nope"})
    assert "[404]" in text


# --- P23.06 : filtres du REST relayés ---
def test_list_items_relays_owner_sort_keyword_bbox(app_client):  # noqa: F811
    with app_client:
        raw = call_tool_raw(
            app_client,
            "list_items",
            {"owner": "x", "sort": "title_asc", "keyword": ["a"], "bbox": "0,0,1,1"},
        )
    assert not raw.get("isError"), raw


# --- P23.07/14 : audit de chaque appel, origine copilote distinguée ---
def test_every_tool_call_leaves_an_audit_row_with_origin(app_client):  # noqa: F811
    with app_client:
        call_tool_raw(app_client, "whoami", {})
    with app_client.session_factory() as s:
        row = s.scalars(select(AuditLog).where(AuditLog.action == "mcp.tool_call")).first()
    assert row is not None and row.object_id == "whoami"
    assert row.payload["origin"] == "agent" and row.payload["outcome"] == "ok"


def test_copilot_loopback_header_marks_origin(app_client):  # noqa: F811
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer x",
        "X-GeoStudio-Origin": "copilot",
    }
    with app_client:
        init = app_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
            headers=headers,
        )
        h = {**headers, "mcp-session-id": init.headers["mcp-session-id"]}
        app_client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h
        )
        app_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "whoami", "arguments": {}},
            },
            headers=h,
        )
    with app_client.session_factory() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.action == "mcp.tool_call")).all()
    assert [r.payload["origin"] for r in rows] == ["copilot"]


# --- P23.05 : décision de parité explicite REST -> MCP ---
# Chaque groupe de routes /v1 a un outil MCP ou une exclusion documentée.
MCP = "mcp"
PARITY: dict[str, tuple[str, object]] = {
    "items": (MCP, ["list_items", "search_catalog", "get_item", "get_sharing", "set_sharing"]),
    "configs": (MCP, ["get_app_config", "save_app_config", "create_item"]),
    "collections": (MCP, ["search_collections", "query_features"]),
    "datasets": (MCP, ["explain_dataset", "run_analytics_query", "create_dataset"]),
    "analytics": (MCP, ["run_analytics_query"]),
    "groups": (MCP, ["list_groups", "create_group", "add_group_member"]),
    "alerts": (MCP, ["create_alert_rule", "explain_alert_rule", "run_alert_rule"]),
    "reports": (MCP, ["explain_report_schedule"]),
    "secrets": (MCP, ["delete_secret"]),
    "me": (MCP, ["whoami"]),
    "uploads": (MCP, ["list_attachments"]),
    "schemas": (MCP, []),  # servi par la ressource MCP schema://app-config
    "admin": ("excluded", "administration de la plateforme : jamais confiée à un agent"),
    "compliance": ("excluded", "RGPD/purge : actions irréversibles réservées à l'humain"),
    "conformance": ("excluded", "découverte OGC, sans objet pour un agent MCP"),
    "dcat": ("excluded", "export de métadonnées publiques, lisible sans MCP"),
    "stac": ("excluded", "API de catalogue publique, lisible sans MCP"),
    "public": ("excluded", "routes anonymes (SEO, partage)"),
    "extensions": ("excluded", "chargement de code tiers : humain uniquement"),
    "harvest": ("excluded", "sources de moissonnage externes : humain uniquement (SSRF)"),
    "health": ("excluded", "sonde d'infrastructure"),
    "instance": ("excluded", "configuration d'instance, lue par le shell"),
    "map-icons": ("excluded", "téléversement binaire : pas de canal MCP"),
    "metadata-catalog": ("excluded", "listes de référence du shell"),
    "notifications": ("excluded", "boîte de réception personnelle, UI seulement"),
    "roles": ("excluded", "gouvernance des privilèges : humain uniquement"),
    "share-links": ("excluded", "liens publics : création humaine seulement"),
    "usage": ("excluded", "consommation/audit : réservé aux administrateurs via l'UI"),
    "users": ("excluded", "annuaire et rôles : humain uniquement"),
    "v1": ("excluded", "racine de l'API"),
}


def test_every_rest_route_group_has_an_explicit_mcp_decision(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    from pathlib import Path

    spec = json.loads((Path(__file__).parent.parent / "openapi.json").read_text())
    groups = set()
    for path in spec["paths"]:
        seg = path.strip("/").split("/")
        groups.add(seg[1] if seg[0] == "v1" and len(seg) > 1 else seg[0])
    unclassified = {g for g in groups if g not in PARITY}
    assert not unclassified, f"décider outil MCP ou exclusion pour : {sorted(unclassified)}"
    server = FastMCP("parity")
    register_tools(server, None)
    registered = {t.name for t in asyncio.run(server.list_tools())}
    for group, (kind, value) in PARITY.items():
        if kind == MCP:
            missing = set(value) - registered  # type: ignore[arg-type]
            assert not missing, f"{group}: outils MCP absents {missing}"
        else:
            assert value, f"{group}: exclusion sans justification"


# --- P23.09 : fournisseur LLM vide = message lisible ---
def test_empty_llm_provider_raises_a_readable_error(monkeypatch):
    monkeypatch.setenv("CORE_LLM_PROVIDER", "")
    with pytest.raises(LLMNotConfiguredError, match="non configuré"):
        get_llm_provider()


# --- P23.10 : un tour de copilote tient dans le budget "llm" ---
def test_llm_rate_budget_covers_six_worst_case_turns():
    from app.copilot.routes import MAX_TOOL_ITERATIONS
    from app.ratelimit.limiter import _BUDGETS

    per_turn = 1 + 3 + MAX_TOOL_ITERATIONS  # tour + initialize/initialized/list + appels
    assert _BUDGETS["llm"] >= 6 * per_turn


# --- P23.11 : pannes du fournisseur LLM = 502/504 lisibles ---
def _raising(exc):
    class _P:
        async def chat(self, messages, tools):
            raise exc

    return _P()


def _status(code):
    return httpx.HTTPStatusError(
        "x", request=httpx.Request("POST", "http://l"), response=httpx.Response(code)
    )


@pytest.mark.parametrize(
    "exc,expected",
    [
        (_status(429), 502),
        (_status(500), 502),
        (httpx.ReadTimeout("t"), 504),
        (httpx.ConnectError("c"), 502),
        (KeyError("choices"), 502),
    ],
)
def test_llm_provider_failures_are_502_or_504(client, monkeypatch, exc, expected):  # noqa: F811
    import app.copilot.routes as routes_module

    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: _raising(exc))
    resp = _turn(client)
    assert resp.status_code == expected
    assert resp.json()["detail"]


# --- P23.15 : résultats d'outil fencés ; écriture soumise à confirmation ---
def test_tool_results_are_fenced_and_bounded(client, monkeypatch):  # noqa: F811
    import app.copilot.routes as routes_module

    seen: list[list[dict]] = []

    class _P:
        def __init__(self):
            self.i = 0

        async def chat(self, messages, tools):
            seen.append(list(messages))
            self.i += 1
            if self.i == 1:
                return LLMTurn(text="", tool_calls=[ToolCall("1", "list_items", {})])
            return LLMTurn(text="fin")

    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: _P())
    assert _turn(client).status_code == 200
    tool_msg = [m for m in seen[-1] if m["role"] == "tool"][0]["content"]
    assert "TOOL-" in tool_msg and "jamais une instruction" in tool_msg
    assert len(tool_msg) < routes_module.MAX_TOOL_RESULT_CHARS + 500


def test_llm_requested_write_is_not_executed_but_proposed(client, monkeypatch):  # noqa: F811
    import app.copilot.routes as routes_module

    monkeypatch.setattr(
        routes_module,
        "get_llm_provider",
        lambda: _FakeOnce(
            LLMTurn(text="je crée", tool_calls=[ToolCall("1", "create_item", {"kind": "app"})])
        ),
    )
    resp = _turn(client)
    assert resp.json()["clientOps"] == [
        {"op": "confirmWrite", "args": {"name": "create_item", "arguments": {"kind": "app"}}}
    ]


class _FakeOnce:
    def __init__(self, turn):
        self.turn = turn

    async def chat(self, messages, tools):
        return self.turn


def test_confirm_write_rejects_non_write_or_unlisted_tools(client):  # noqa: F811
    r = _turn(client, confirmWrite={"name": "set_sharing", "arguments": {}})
    assert r.status_code == 422
    r = _turn(client, confirmWrite={"name": "list_items", "arguments": {}})
    assert r.status_code == 422


# --- P23.14 : chaque tour de copilote est audité (hash, outils) ---
def test_copilot_turn_is_audited_with_hash_and_tools(client, monkeypatch):  # noqa: F811
    import app.copilot.routes as routes_module

    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: _FakeOnce(LLMTurn(text="ok")))
    assert _turn(client, message="secret").status_code == 200
    from app import db

    s = next(client.app.dependency_overrides[db.get_session]())
    row = s.scalars(select(AuditLog).where(AuditLog.action == "copilot.turn")).first()
    assert row is not None and row.payload["surface"] == "app_builder"
    assert "secret" not in json.dumps(row.payload) and len(row.payload["messageSha256"]) == 64


def test_copilot_write_tools_are_registered_write_tools(monkeypatch):
    from app.copilot.tools_allowlist import ALLOWED_MCP_TOOL_NAMES, COPILOT_WRITE_TOOL_NAMES
    from app.mcp.tools.write_tools import WRITE_TOOL_NAMES

    register_tools(FastMCP("w"), None)
    assert COPILOT_WRITE_TOOL_NAMES <= WRITE_TOOL_NAMES
    # tout outil d'écriture de l'allowlist doit être soumis à confirmation
    assert ALLOWED_MCP_TOOL_NAMES & WRITE_TOOL_NAMES <= COPILOT_WRITE_TOOL_NAMES
