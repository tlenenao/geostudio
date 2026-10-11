# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.pipelines import egress as pipelines_egress
from app.pipelines.http_call_runtime import execute_http_call


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    # Comme test_pipeline_connector_runtime.py : pytest-httpserver écoute sur 127.0.0.1, que la
    # vraie garde bloque ; la garde elle-même est testée dans test_http_call_real_egress_guard.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def run(conn, params, *, ids=(1, 2), resolver=None, preview=False, extra_cols=""):
    values = ", ".join(f"({i})" for i in ids)
    conn.execute(f"CREATE TEMP TABLE inp AS SELECT * FROM (VALUES {values}) t(id)")
    if extra_cols:
        conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS SELECT *, {extra_cols} FROM inp")
    execute_http_call(
        conn,
        input_view="inp",
        view_name="out",
        params=params,
        secret_resolver=resolver,
        preview=preview,
    )
    return conn.execute("SELECT * FROM out ORDER BY id").fetchall()


def test_get_one_call_per_row_preserves_input_columns(conn, httpserver):
    httpserver.expect_request("/items/1").respond_with_data("one")
    httpserver.expect_request("/items/2").respond_with_data("two")
    base = httpserver.url_for("/items/")
    rows = run(conn, {"urlExpr": f"'{base}' || id"})
    # colonnes : id, responseBody, httpStatusCode, httpStatus, httpError
    assert rows == [(1, "one", 200, "success", None), (2, "two", 200, "success", None)]


def test_4xx_is_an_error_row_not_a_failed_run(conn, httpserver):
    httpserver.expect_request("/ok").respond_with_data("fine")
    httpserver.expect_request("/missing").respond_with_data("nope", status=404)
    base = httpserver.url_for("/")
    rows = run(conn, {"urlExpr": f"'{base}' || CASE WHEN id = 1 THEN 'ok' ELSE 'missing' END"})
    assert rows[0][3] == "success"
    assert rows[1] == (2, "nope", 404, "error", "HTTP 404")


def test_output_column_collision_with_input_is_refused(conn):
    from app.pipelines.errors import PipelineRuntimeError

    with pytest.raises(PipelineRuntimeError, match="responseBody"):
        run(conn, {"urlExpr": "'http://x/'"}, extra_cols="'a' AS responseBody")


def test_unbounded_expression_is_refused(conn):
    from app.analytics.sql_sandbox import SqlSandboxError

    conn.execute("CREATE TABLE secret_t AS SELECT 1 AS v")
    with pytest.raises(SqlSandboxError):
        run(conn, {"urlExpr": "(SELECT v FROM secret_t)"})


def test_geometry_column_survives(conn, httpserver):
    conn.execute("INSTALL spatial; LOAD spatial;")
    httpserver.expect_request("/g").respond_with_data("x")
    conn.execute("CREATE TEMP TABLE inp AS SELECT 1 AS id, ST_Point(1, 2) AS geometry")
    execute_http_call(
        conn,
        input_view="inp",
        view_name="out",
        params={"urlExpr": f"'{httpserver.url_for('/g')}'"},
    )
    assert conn.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0] == "POINT (1 2)"


def test_runtime_passes_context_only_to_ops_that_ask(monkeypatch, conn):
    from app.configs.schemas import PipelineEdge, PipelineNode
    from app.pipelines import runtime
    from app.pipelines.ops import contracts

    seen = {}

    def fake_execute(c, *, input_view, view_name, params, secret_resolver=None, preview=False):
        seen.update(resolver=secret_resolver, preview=preview)
        c.execute(f'CREATE TEMP TABLE "{view_name}" AS SELECT * FROM "{input_view}"')

    fake = contracts.OperationContract(
        op="transform.fake-http",
        kind="transform",
        params_schema=contracts.TransformFilterParams,
        execute=fake_execute,
        needs_runtime_context=True,
    )
    monkeypatch.setitem(contracts.OPERATIONS, "transform.fake-http", fake)
    conn.execute("CREATE TEMP TABLE node_r AS SELECT 1 AS id")
    nodes = [
        PipelineNode(id="r", kind="reader", op="reader.collection", params={}),
        PipelineNode(id="t", kind="transform", op="transform.fake-http", params={}),
    ]
    edges = [PipelineEdge(id="e", **{"from": "r"}, to="t")]
    marker = object()
    runtime._execute_transform_chain(
        conn, nodes, edges, {"r": "node_r"}, {"r": 4326}, {}, secret_resolver=marker, preview=True
    )
    assert seen == {"resolver": marker, "preview": True}
