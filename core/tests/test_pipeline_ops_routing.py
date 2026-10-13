# SPDX-License-Identifier: Apache-2.0
"""ARC-34 : ops transform.isochrone / transform.route (faux Valhalla, DuckDB en mémoire)."""

import duckdb
import httpx
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.routing.client import Valhalla
from tests.test_routing import fake_valhalla


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE src (id INTEGER, dlon DOUBLE, dlat DOUBLE, geometry GEOMETRY)")
    c.execute(
        "INSERT INTO src VALUES (1, 1.53, 45.16, ST_Point(1.77, 45.26)),"
        " (2, 1.53, 45.16, ST_Point(0, 0)),"  # lon 0 : le faux Valhalla répond « pas de route »
        " (3, NULL, NULL, NULL)"
    )
    return c


@pytest.fixture()
def seen(monkeypatch):
    calls: list = []
    transport = httpx.MockTransport(fake_valhalla(calls))
    monkeypatch.setattr(
        "app.pipelines.ops.routing.get_routing",
        lambda: Valhalla("http://valhalla:8002", lambda: httpx.Client(transport=transport)),
    )
    return calls


def _run(conn, op, params, **kw):
    OPERATIONS[op].execute(conn, input_view="src", view_name="out", params=params, **kw)


def test_registered_in_catalog():
    for op in ("transform.isochrone", "transform.route"):
        assert op in OPERATIONS and op in ops_catalog()
        assert OPERATIONS[op].engine_license


def test_isochrone_one_row_per_contour_and_keeps_unsolved_rows(conn, seen):
    _run(conn, "transform.isochrone", {"minutes": [5, 10]})
    rows = conn.execute(
        "SELECT id, contour_minutes, routing_status, ST_GeometryType(geometry)::VARCHAR "
        "FROM out ORDER BY id, contour_minutes"
    ).fetchall()
    assert rows == [
        (1, 5, "ok", "POLYGON"),
        (1, 10, "ok", "POLYGON"),
        (2, 5, "ok", "POLYGON"),  # le faux Valhalla ne refuse que /route
        (2, 10, "ok", "POLYGON"),
        (3, None, "non_trouvé", None),  # pas d'origine : conservée, géométrie NULL
    ]
    assert len(seen) == 2  # 1 appel par origine valide


def test_route_adds_distance_duration_and_linestring(conn, seen):
    _run(conn, "transform.route", {"destLonColumn": "dlon", "destLatColumn": "dlat"})
    rows = conn.execute(
        "SELECT id, routing_status, route_distance_km, route_duration_s, "
        "ST_GeometryType(geometry)::VARCHAR FROM out ORDER BY id"
    ).fetchall()
    assert rows == [
        (1, "ok", 25.4, 1800.0, "LINESTRING"),
        (2, "non_trouvé", None, None, None),
        (3, "non_trouvé", None, None, None),
    ]


def test_preview_is_bounded(conn, seen):
    _run(conn, "transform.isochrone", {"minutes": [5]}, preview=True)
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] == 3  # < PREVIEW_ROWS


def test_row_cap(conn, seen, monkeypatch):
    monkeypatch.setattr("app.pipelines.ops.routing.MAX_ROWS", 2)
    with pytest.raises(PipelineRuntimeError, match="cap"):
        _run(conn, "transform.isochrone", {"minutes": [5]})
    assert seen == []


def test_service_absent_fails_the_run_readably(conn, monkeypatch):
    monkeypatch.setenv("CORE_ROUTING_URL", "")
    with pytest.raises(PipelineRuntimeError, match="désactivé"):
        _run(conn, "transform.isochrone", {"minutes": [5]})


def test_missing_column_and_bad_params(conn, seen):
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _run(conn, "transform.route", {"destLonColumn": "nope", "destLatColumn": "dlat"})
    with pytest.raises(ValueError):
        _run(conn, "transform.isochrone", {"minutes": [1, 2, 3, 4, 5]})
