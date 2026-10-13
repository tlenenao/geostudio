# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""Outils MCP de routage (ARC-34) : jumeaux de /v1/routing/*."""

import httpx
import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.routing import client as rc
from app.routing.client import Valhalla
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)
from tests.test_routing import BRIVE, TULLE, fake_valhalla


@pytest.fixture()
def fake(monkeypatch):
    seen: list = []
    transport = httpx.MockTransport(fake_valhalla(seen))
    monkeypatch.setattr(
        "app.mcp.tools.routing.get_routing",
        lambda: Valhalla("http://valhalla:8002", lambda: httpx.Client(transport=transport)),
    )
    monkeypatch.setattr("app.mcp.tools.routing.rate_window", rc._Window())
    return seen


def test_route_isochrone_service_area_matrix(app_client, fake):
    with app_client:
        route = call_tool(app_client, "route", {"points": [TULLE, BRIVE]})
        iso = call_tool(app_client, "isochrone", {"origin": TULLE, "minutes": [10]})
        area = call_tool(app_client, "service_area", {"origins": [TULLE, BRIVE], "minutes": [5]})
        matrix = call_tool(app_client, "travel_matrix", {"sources": [TULLE], "targets": [BRIVE]})
    assert route["distance_km"] == 25.4
    assert iso["features"][0]["properties"]["contour_minutes"] == 10
    assert len(area["features"]) == 2
    assert matrix["matrix"][0][0]["duration_s"] == 90


def test_bounds_are_enforced(app_client, fake):
    with app_client:
        error = call_tool_expecting_error(app_client, "route", {"points": [TULLE]})
    assert "[422]" in error and fake == []


def test_service_absent_is_503(app_client, monkeypatch):
    monkeypatch.setenv("CORE_ROUTING_URL", "")
    with app_client:
        error = call_tool_expecting_error(app_client, "route", {"points": [TULLE, BRIVE]})
    assert "[503]" in error


def test_call_is_audited_and_rate_limited(app_client, fake, monkeypatch):
    monkeypatch.setattr("app.mcp.tools.routing.rate_window", rc._Window(budget=2))
    with app_client:
        call_tool(app_client, "route", {"points": [TULLE, BRIVE]})
        call_tool(app_client, "route", {"points": [TULLE, BRIVE]})
        error = call_tool_expecting_error(app_client, "route", {"points": [TULLE, BRIVE]})
    assert "[429]" in error and len(fake) == 2
    with app_client.session_factory() as session:
        rows = [r for r in session.scalars(select(AuditLog)) if r.action == "mcp.tool_call"]
    assert [r.object_id for r in rows] == ["route"] * 3
