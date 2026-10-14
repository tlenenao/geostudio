# SPDX-License-Identifier: Apache-2.0
"""ARC-34 : ops transform.isochrone / transform.route (faux Valhalla, DuckDB en mémoire)."""

import duckdb
import httpx
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.routing import client as rc
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
        lambda throttle=None: Valhalla(
            "http://valhalla:8002", lambda: httpx.Client(transport=transport), throttle=throttle
        ),
    )
    monkeypatch.setattr("app.pipelines.ops.routing.rate_window", rc._Window())
    return calls


@pytest.fixture()
def actor(tmp_path):
    """Résolveur adossé à une vraie base : l'acteur du run (rôle par défaut, analytics.view)."""
    from app.db import init_db, make_engine, make_session_factory
    from app.pipelines.connector_runtime import PostgresSecretResolver
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import get_or_create_user

    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'ops.db'}")
    init_db(engine)
    session = make_session_factory(engine)()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="s",
        username="u",
        email=None,
        first_name="U",
        last_name="U",
    )
    session.commit()
    resolver = PostgresSecretResolver(session, tenant.id, user)
    yield resolver
    session.close()
    engine.dispose()


def _run(conn, op, params, **kw):
    OPERATIONS[op].execute(conn, input_view="src", view_name="out", params=params, **kw)


def test_registered_in_catalog():
    for op in ("transform.isochrone", "transform.route"):
        assert op in OPERATIONS and op in ops_catalog()
        assert OPERATIONS[op].engine_license


def test_isochrone_one_row_per_contour_and_keeps_unsolved_rows(conn, seen, actor):
    _run(conn, "transform.isochrone", {"minutes": [5, 10]}, secret_resolver=actor)
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


def test_route_adds_distance_duration_and_linestring(conn, seen, actor):
    _run(
        conn,
        "transform.route",
        {"destLonColumn": "dlon", "destLatColumn": "dlat"},
        secret_resolver=actor,
    )
    rows = conn.execute(
        "SELECT id, routing_status, route_distance_km, route_duration_s, "
        "ST_GeometryType(geometry)::VARCHAR FROM out ORDER BY id"
    ).fetchall()
    assert rows == [
        (1, "ok", 25.4, 1800.0, "LINESTRING"),
        (2, "non_trouvé", None, None, None),
        (3, "non_trouvé", None, None, None),
    ]


def test_preview_is_bounded(conn, seen, actor):
    _run(conn, "transform.isochrone", {"minutes": [5]}, preview=True, secret_resolver=actor)
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] == 3  # < PREVIEW_ROWS


def test_row_cap(conn, seen, monkeypatch, actor):
    monkeypatch.setattr("app.pipelines.ops.routing.MAX_ROWS", 2)
    with pytest.raises(PipelineRuntimeError, match="cap"):
        _run(conn, "transform.isochrone", {"minutes": [5]}, secret_resolver=actor)
    assert seen == []


def test_service_absent_fails_the_run_readably(conn, monkeypatch, actor):
    monkeypatch.setenv("CORE_ROUTING_URL", "")
    with pytest.raises(PipelineRuntimeError, match="désactivé"):
        _run(conn, "transform.isochrone", {"minutes": [5]}, secret_resolver=actor)


def test_missing_column_and_bad_params(conn, seen, actor):
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _run(
            conn,
            "transform.route",
            {"destLonColumn": "nope", "destLatColumn": "dlat"},
            secret_resolver=actor,
        )
    with pytest.raises(ValueError):
        _run(conn, "transform.isochrone", {"minutes": [1, 2, 3, 4, 5]}, secret_resolver=actor)


def test_preview_truncates_before_the_row_cap(conn, seen, monkeypatch, actor):
    monkeypatch.setattr("app.pipelines.ops.routing.MAX_ROWS", 2)
    monkeypatch.setattr("app.pipelines.ops.routing.PREVIEW_ROWS", 2)
    _run(conn, "transform.isochrone", {"minutes": [5]}, preview=True, secret_resolver=actor)
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] == 2


@pytest.mark.parametrize(
    "op,params",
    [
        ("transform.isochrone", {"minutes": [5]}),
        ("transform.route", {"destLonColumn": "dlon", "destLatColumn": "dlat"}),
    ],
)
def test_op_requires_analytics_view(conn, seen, actor, op, params):
    from app.roles.repository import create_role

    session, user = actor.session, actor.user
    role = create_role(session, tenant_id=user.tenant_id, name="sans-routage", privileges=[])
    user.role_id = role.id
    session.commit()
    with pytest.raises(PipelineRuntimeError, match="analytics.view"):
        _run(conn, op, params, secret_resolver=actor)
    assert seen == []


def test_op_without_actor_is_refused(conn, seen):
    with pytest.raises(PipelineRuntimeError, match="analytics.view"):
        _run(conn, "transform.isochrone", {"minutes": [5]}, secret_resolver=None)
    assert seen == []


def test_op_is_audited_once_per_node(conn, seen, actor):
    from sqlalchemy import select

    from app.audit.models import AuditLog

    _run(conn, "transform.isochrone", {"minutes": [5]}, secret_resolver=actor)
    rows = [r for r in actor.session.scalars(select(AuditLog)) if r.action.startswith("routing.")]
    assert [(r.action, r.object_id, r.payload) for r in rows] == [
        (
            "routing.pipeline_op",
            "transform.isochrone",
            {"op": "transform.isochrone", "costing": "auto", "calls": 2},
        )
    ]


def test_op_consumes_the_shared_rate_budget(conn, seen, monkeypatch, actor):
    monkeypatch.setattr("app.pipelines.ops.routing.rate_window", rc._Window(budget=1))
    monkeypatch.setattr("app.pipelines.ops.routing.RATE_WAIT_S", 0.0)
    with pytest.raises(PipelineRuntimeError, match="budget"):
        _run(conn, "transform.isochrone", {"minutes": [5]}, secret_resolver=actor)
    assert len(seen) == 1  # le 2e appel amont est refusé


def test_projected_input_is_reprojected_to_wgs84(conn, seen, actor):
    """Entrée en Lambert-93 : sans reprojection, les centroïdes (mètres) seraient hors limites
    et toutes les lignes sortiraient `non_trouvé`."""
    conn.execute(
        "CREATE TABLE lam AS SELECT 1 AS id, "
        "ST_Transform(ST_Point(1.77, 45.26), 'EPSG:4326', 'EPSG:2154', true) AS geometry"
    )
    OPERATIONS["transform.isochrone"].execute(
        conn,
        input_view="lam",
        view_name="out",
        params={"minutes": [5]},
        secret_resolver=actor,
        input_srid=2154,
    )
    assert conn.execute("SELECT routing_status FROM out").fetchall() == [("ok",)]
