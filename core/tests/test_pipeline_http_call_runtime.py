# SPDX-License-Identifier: Apache-2.0
import json as _json
import threading
import time

import duckdb
import pytest
from werkzeug.wrappers import Response

from app.pipelines import egress as pipelines_egress
from app.pipelines.http_call_runtime import execute_http_call

_REAL_ASSERT_EGRESS_ALLOWED = pipelines_egress.assert_egress_allowed


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


def test_output_collision_drops_the_stage_table(conn):
    from app.pipelines.errors import PipelineRuntimeError

    with pytest.raises(PipelineRuntimeError):
        run(conn, {"urlExpr": "'http://x/'"}, extra_cols="'a' AS responseBody")
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'out__stage'"
    ).fetchall()
    assert tables == []


def test_egress_refusal_message_is_fixed_and_leaks_no_url(conn, monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_ASSERT_EGRESS_ALLOWED)
    rows = run(
        conn,
        {
            "urlExpr": (
                "CASE WHEN id = 1 THEN 'https:///x?token=SECRET' ELSE 'http://127.0.0.1:9/' END"
            )
        },
    )
    # `requests` rejette l'URL sans hôte (InvalidURL) avant la garde : seule exigence, pas de fuite.
    assert rows[1][-1] == "egress refusé"
    assert "SECRET" not in repr(rows)


def test_runtime_does_not_pass_context_to_ops_that_do_not_ask(monkeypatch, conn):
    from app.configs.schemas import PipelineEdge, PipelineNode
    from app.pipelines import runtime
    from app.pipelines.ops import contracts

    def fake_execute(c, *, input_view, view_name, params):  # TypeError si kwargs de contexte
        c.execute(f'CREATE TEMP TABLE "{view_name}" AS SELECT * FROM "{input_view}"')

    fake = contracts.OperationContract(
        op="transform.fake-plain",
        kind="transform",
        params_schema=contracts.TransformFilterParams,
        execute=fake_execute,
    )
    monkeypatch.setitem(contracts.OPERATIONS, "transform.fake-plain", fake)
    conn.execute("CREATE TEMP TABLE node_r AS SELECT 1 AS id")
    nodes = [
        PipelineNode(id="r", kind="reader", op="reader.collection", params={}),
        PipelineNode(id="t", kind="transform", op="transform.fake-plain", params={}),
    ]
    edges = [PipelineEdge(id="e", **{"from": "r"}, to="t")]
    runtime._execute_transform_chain(
        conn, nodes, edges, {"r": "node_r"}, {"r": 4326}, {}, secret_resolver=object(), preview=True
    )


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


def _recording_handler(statuses, stamps, headers=None):
    it = iter(statuses)
    lock = threading.Lock()

    def handler(request):
        with lock:
            stamps.append(time.monotonic())
            code = next(it, statuses[-1])
        return Response("body", status=code, headers=headers or {})

    return handler


def test_retry_503_then_200_waits_for_exponential_backoff(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/r").respond_with_handler(
        _recording_handler([503, 503, 200], stamps)
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/r')}'", "initialBackoffSeconds": 0.2, "maxRetries": 3},
        ids=(1,),
    )
    assert rows[0][2:] == (200, "success", None)
    assert len(stamps) == 3
    # attente 0.2 puis 0.4 s : on mesure les intervalles réels, pas la durée totale
    assert stamps[1] - stamps[0] >= 0.2
    assert stamps[2] - stamps[1] >= 0.4


def test_retry_after_header_overrides_backoff(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/r").respond_with_handler(
        _recording_handler([429, 200], stamps, headers={"Retry-After": "1"})
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/r')}'", "initialBackoffSeconds": 0.0},
        ids=(1,),
    )
    assert rows[0][3:] == ("success", None)
    assert stamps[1] - stamps[0] >= 1.0


def test_retries_exhausted_keeps_last_status_and_only_that_row_fails(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/bad").respond_with_handler(_recording_handler([500], stamps))
    httpserver.expect_request("/good").respond_with_data("ok")
    base = httpserver.url_for("/")
    rows = run(
        conn,
        {
            "urlExpr": f"'{base}' || CASE WHEN id = 1 THEN 'bad' ELSE 'good' END",
            "maxRetries": 2,
            "initialBackoffSeconds": 0.0,
        },
    )
    assert rows[0][2:] == (500, "error", "HTTP 500")
    assert rows[1][3] == "success"
    assert len(stamps) == 3  # 1 + 2 retries


def test_connection_error_is_retried_then_reported(conn):
    rows = run(
        conn,
        {"urlExpr": "'http://127.0.0.1:1/'", "maxRetries": 1, "initialBackoffSeconds": 0.0},
        ids=(1,),
    )
    assert rows[0][3:] == ("error", "ConnectionError")


def test_4xx_is_not_retried(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/n").respond_with_handler(_recording_handler([404], stamps))
    run(conn, {"urlExpr": f"'{httpserver.url_for('/n')}'"}, ids=(1,))
    assert len(stamps) == 1


def _capture(httpserver, path="/c"):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["ctype"] = request.headers.get("Content-Type", "")
        seen["auth"] = request.headers.get("X-Test")
        seen["data"] = request.get_data()
        return Response("ok")

    httpserver.expect_request(path).respond_with_handler(handler)
    return seen


def test_json_body_and_headers(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "json",
            "bodyExpr": "json_object('id', id)",
            "headersExpr": "json_object('X-Test', 'v')",
        },
        ids=(7,),
    )
    assert seen["method"] == "POST"
    assert seen["ctype"].startswith("application/json")
    assert seen["auth"] == "v"
    assert _json.loads(seen["data"]) == {"id": 7}


def test_form_body(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "form",
            "bodyExpr": "json_object('a', 'x y', 'n', id)",
        },
        ids=(3,),
    )
    assert seen["ctype"].startswith("application/x-www-form-urlencoded")
    assert seen["data"] in (b"a=x+y&n=3", b"n=3&a=x+y")


def test_raw_body(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "PUT",
            "bodyType": "raw",
            "bodyExpr": "'hello ' || id",
        },
        ids=(1,),
    )
    assert seen["data"] == b"hello 1"


def test_multipart_with_file_from_blob_column(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "multipart",
            "multipartFields": [
                {"name": "title", "valueExpr": "'doc-' || id"},
                {
                    "name": "file",
                    "valueExpr": "CAST('PAYLOAD' AS BLOB)",
                    "isFile": True,
                    "filename": "a.bin",
                    "contentType": "application/octet-stream",
                },
            ],
        },
        ids=(1,),
    )
    assert seen["ctype"].startswith("multipart/form-data")
    assert b'name="title"' in seen["data"] and b"doc-1" in seen["data"]
    assert b'filename="a.bin"' in seen["data"] and b"PAYLOAD" in seen["data"]


def test_invalid_headers_json_is_a_row_error(conn, httpserver):
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/c')}'", "headersExpr": "'not json'"},
        ids=(1,),
    )
    assert rows[0][3:] == ("error", "headersExpr n'est pas du JSON valide")
