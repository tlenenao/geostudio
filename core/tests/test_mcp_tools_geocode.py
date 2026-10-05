# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""Outil MCP geocode (REV-102) : mêmes bornes que GET /v1/geocode."""

import httpx
import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import GeocodeResult
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)


class _Stub:
    def __init__(self, results=None, exc=None):
        self.results, self.exc, self.calls = results or [], exc, []

    def search(self, q, limit):
        self.calls.append((q, limit))
        if self.exc:
            raise self.exc
        return self.results


def _use(monkeypatch, stub):
    monkeypatch.setattr("app.mcp.tools.geocode.get_geocoder", lambda: stub)


def test_returns_label_lon_lat(app_client, monkeypatch):
    stub = _Stub([GeocodeResult(label="Tulle", lon=1.77, lat=45.26)])
    _use(monkeypatch, stub)
    with app_client:
        result = call_tool(app_client, "geocode", {"query": "tulle", "limit": 3})
    assert result == {"results": [{"label": "Tulle", "lon": 1.77, "lat": 45.26}]}
    assert stub.calls == [("tulle", 3)]


@pytest.mark.parametrize(
    "args",
    [
        {"query": "ab"},
        {"query": "x" * 201},
        {"query": "tulle", "limit": 0},
        {"query": "tulle", "limit": 11},
    ],
)
def test_rejects_out_of_bounds(app_client, monkeypatch, args):
    stub = _Stub()
    _use(monkeypatch, stub)
    with app_client:
        call_tool_expecting_error(app_client, "geocode", args)
    assert stub.calls == []


@pytest.mark.parametrize("exc", [httpx.ConnectError("x"), EgressBlockedError("x"), KeyError("k")])
def test_upstream_failure_is_an_indisponible_error(app_client, monkeypatch, exc):
    _use(monkeypatch, _Stub(exc=exc))
    with app_client:
        error = call_tool_expecting_error(app_client, "geocode", {"query": "tulle"})
    assert "[502]" in error and "indisponible" in error


def test_call_is_audited(app_client, monkeypatch):
    _use(monkeypatch, _Stub())
    with app_client:
        call_tool(app_client, "geocode", {"query": "tulle"})
    with app_client.session_factory() as session:
        rows = [r for r in session.scalars(select(AuditLog)) if r.action == "mcp.tool_call"]
    assert [r.object_id for r in rows] == ["geocode"]
