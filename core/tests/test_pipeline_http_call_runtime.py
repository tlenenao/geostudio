# SPDX-License-Identifier: Apache-2.0
import json as _json
import threading
import time

import duckdb
import pytest
from werkzeug.wrappers import Response

from app.db import init_db, make_engine, make_session_factory
from app.pipelines import connector_runtime
from app.pipelines import egress as pipelines_egress
from app.pipelines.http_call_runtime import execute_http_call
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_REAL_ASSERT_EGRESS_ALLOWED = pipelines_egress.assert_egress_allowed
TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


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

    def fake_execute(
        c, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
    ):
        seen.update(resolver=secret_resolver, preview=preview, input_srid=input_srid)
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
    assert seen == {"resolver": marker, "preview": True, "input_srid": 4326}


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


def test_page_number_pagination_is_aggregated_into_one_cell(conn, httpserver):
    pages = {"1": [{"v": 1}, {"v": 2}], "2": [{"v": 3}], "3": []}

    def handler(request):
        return Response(
            _json.dumps(pages[request.args.get("page", "1")]), content_type="application/json"
        )

    httpserver.expect_request("/p").respond_with_handler(handler)
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/p')}'", "paginator": "page_number"},
        ids=(1,),
    )
    assert _json.loads(rows[0][1]) == [{"v": 1}, {"v": 2}, {"v": 3}]
    assert rows[0][3] == "success"


def test_pagination_records_path(conn, httpserver):
    httpserver.expect_request("/p").respond_with_json({"data": {"items": [{"v": 1}]}})
    rows = run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/p')}'",
            "paginator": "page_number",
            "paginatorConfig": {"maximumPage": 1},
            "recordsPath": "data.items",
        },
        ids=(1,),
    )
    assert _json.loads(rows[0][1]) == [{"v": 1}]


def test_paginated_5xx_retries_whole_pagination(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/p").respond_with_handler(_recording_handler([503], stamps))
    rows = run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/p')}'",
            "paginator": "page_number",
            "maxRetries": 1,
            "initialBackoffSeconds": 0.0,
        },
        ids=(1,),
    )
    assert rows[0][2:5] == (503, "error", "HTTP 503")
    assert len(stamps) == 2


@pytest.fixture()
def resolver_factory(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session = make_session_factory(engine)()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="u1",
        username="u1",
        email=None,
        first_name="",
        last_name="",
    )

    def make(name, kind, payload):
        ct, nonce = encrypt(payload)
        secrets_repo.create_secret(
            session,
            tenant_id=tenant.id,
            created_by=user.id,
            name=name,
            kind=kind,
            ciphertext=ct,
            nonce=nonce,
        )
        return connector_runtime.PostgresSecretResolver(session, tenant.id, user)

    yield make
    session.close()
    engine.dispose()


def test_bearer_secret_is_sent_and_never_leaks_into_the_error_column(
    conn, httpserver, resolver_factory
):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return Response("denied", status=403)

    httpserver.expect_request("/s").respond_with_handler(handler)
    base = httpserver.url_for("/")
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "SECRET-TOKEN", "baseUrl": base}
    )
    rows = run(
        conn,
        {"urlExpr": f"'{base}s'", "secretName": "tok", "maxRetries": 0},
        ids=(1,),
        resolver=resolver,
    )
    assert seen["auth"] == "Bearer SECRET-TOKEN"
    assert rows[0][2:] == (403, "error", "HTTP 403")
    assert "SECRET-TOKEN" not in repr(
        rows[0][3:]
    )  # colonnes d'erreur ; le corps est celui du serveur


def test_url_outside_secret_scope_makes_no_request(conn, httpserver, resolver_factory):
    hits = []
    httpserver.expect_request("/o").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    resolver = resolver_factory(
        "tok",
        "bearer_token",
        {"kind": "bearer_token", "token": "T", "baseUrl": "https://api.allowed.example/v1"},
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/o')}'", "secretName": "tok"},
        ids=(1,),
        resolver=resolver,
    )
    assert hits == []
    assert rows[0][3:] == ("error", "URL hors de la portée du secret")


def test_secret_without_base_url_fails_the_node(conn, resolver_factory):
    from app.pipelines.errors import PipelineRuntimeError

    resolver = resolver_factory("tok", "bearer_token", {"kind": "bearer_token", "token": "T"})
    with pytest.raises(PipelineRuntimeError, match="baseUrl"):
        run(conn, {"urlExpr": "'http://x/'", "secretName": "tok"}, ids=(1,), resolver=resolver)


def test_secret_name_without_resolver_fails_cleanly(conn):
    from app.pipelines.errors import PipelineRuntimeError

    with pytest.raises(PipelineRuntimeError, match="secret 'tok'"):
        run(conn, {"urlExpr": "'http://x/'", "secretName": "tok"}, ids=(1,), resolver=None)


def test_redirects_are_not_followed_when_a_secret_is_bound(conn, httpserver, resolver_factory):
    base = httpserver.url_for("/")
    httpserver.expect_request("/r").respond_with_data(
        "", status=302, headers={"Location": base + "t"}
    )
    httpserver.expect_request("/t").respond_with_data("target")
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "T", "baseUrl": base}
    )
    rows = run(conn, {"urlExpr": f"'{base}r'", "secretName": "tok"}, ids=(1,), resolver=resolver)
    assert rows[0][2:] == (302, "error", "redirection non suivie")


def test_row_cap_fails_the_node_before_any_call(conn, monkeypatch, httpserver):
    from app.pipelines.errors import PipelineRuntimeError

    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_ROWS", "2")
    hits = []
    httpserver.expect_request("/x").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    with pytest.raises(PipelineRuntimeError, match="plafond"):
        run(conn, {"urlExpr": f"'{httpserver.url_for('/x')}'"}, ids=(1, 2, 3))
    assert hits == []


def test_response_size_cap_is_a_row_error(conn, monkeypatch, httpserver):
    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES", "10")
    httpserver.expect_request("/big").respond_with_data("x" * 100)
    rows = run(conn, {"urlExpr": f"'{httpserver.url_for('/big')}'"}, ids=(1,))
    assert rows[0][3:] == ("error", "réponse trop volumineuse")


def test_response_size_cap_applies_to_decompressed_gzip_bytes(conn, monkeypatch, httpserver):
    import gzip

    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_RESPONSE_BYTES", "1000")
    payload = gzip.compress(b"x" * 100_000)  # ~100 octets compressés, 100 ko décompressés
    assert len(payload) < 1000
    httpserver.expect_request("/gz").respond_with_handler(
        lambda r: Response(payload, headers={"Content-Encoding": "gzip"})
    )
    rows = run(conn, {"urlExpr": f"'{httpserver.url_for('/gz')}'"}, ids=(1,))
    assert rows[0][3:] == ("error", "réponse trop volumineuse")


def test_paginated_request_honours_the_page_cap(conn, monkeypatch, httpserver):
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_PAGES", "2")
    httpserver.expect_request("/p").respond_with_handler(
        lambda r: Response(_json.dumps([{"v": 1}]), content_type="application/json")
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/p')}'", "paginator": "page_number"},
        ids=(1,),
    )
    assert rows[0][3:] == ("error", "plafond de 2 pages dépassé")


def test_max_concurrency_is_respected_by_measuring_overlap(conn):
    from pytest_httpserver import HTTPServer

    # Serveur threadé : le fixture `httpserver` sérialise les requêtes (recouvrement masqué).
    httpserver = HTTPServer(threaded=True)
    httpserver.start()
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def handler(request):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.2)
        with lock:
            state["now"] -= 1
        return Response("ok")

    httpserver.expect_request("/slow").respond_with_handler(handler)
    run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/slow')}'", "maxConcurrency": 2},
        ids=tuple(range(6)),
    )
    httpserver.stop()
    assert state["max"] == 2  # plafond atteint ET jamais dépassé


def test_requests_per_second_spaces_calls(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/q").respond_with_handler(_recording_handler([200], stamps))
    run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/q')}'", "requestsPerSecond": 5, "maxConcurrency": 4},
        ids=(1, 2, 3),
    )
    stamps.sort()
    assert stamps[1] - stamps[0] >= 0.15 and stamps[2] - stamps[1] >= 0.15  # 1/5 s = 0.2


def test_preview_only_runs_get_and_skips_the_rest(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/pv')}'", "method": "POST"},
        ids=(1, 2),
        preview=True,
    )
    assert hits == []
    assert rows[0][3:] == ("skipped", "non exécuté en aperçu")


def test_preview_limits_get_calls(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/pv')}'"},
        ids=tuple(range(25)),
        preview=True,
    )
    assert len(hits) == 20
    assert [r[3] for r in rows].count("skipped") == 5


def test_malformed_urls_with_secret_are_row_errors_without_request(
    conn, httpserver, resolver_factory
):
    hits = []
    httpserver.expect_request("/ok").respond_with_handler(
        lambda r: (hits.append(1), Response("fine"))[1]
    )
    base = httpserver.url_for("/")
    host = base.split("//")[1].split("/")[0].split(":")[0]
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "T", "baseUrl": base}
    )
    urlexpr = (
        f"CASE id WHEN 1 THEN 'http://{host}:abc/v1' WHEN 2 THEN 'https://[::1/v1' "
        f"ELSE '{base}ok' END"
    )
    rows = run(conn, {"urlExpr": urlexpr, "secretName": "tok"}, ids=(1, 2, 3), resolver=resolver)
    assert [r[3:] for r in rows[:2]] == [("error", "URL hors de la portée du secret")] * 2
    assert rows[2][3:] == ("success", None)
    assert hits == [1]


def test_non_string_url_with_secret_is_out_of_scope(conn, resolver_factory):
    resolver = resolver_factory(
        "tok",
        "bearer_token",
        {"kind": "bearer_token", "token": "T", "baseUrl": "https://a.example/"},
    )
    rows = run(conn, {"urlExpr": "5", "secretName": "tok"}, ids=(1,), resolver=resolver)
    assert rows[0][3:] == ("error", "URL hors de la portée du secret")


def test_paginated_redirect_is_not_followed_with_secret(conn, httpserver, resolver_factory):
    hits = []
    base = httpserver.url_for("/")
    httpserver.expect_request("/pr").respond_with_data(
        "", status=302, headers={"Location": base + "t"}
    )
    httpserver.expect_request("/t").respond_with_handler(
        lambda r: (hits.append(1), Response("[]", content_type="application/json"))[1]
    )
    resolver = resolver_factory(
        "tok", "bearer_token", {"kind": "bearer_token", "token": "T", "baseUrl": base}
    )
    rows = run(
        conn,
        {"urlExpr": f"'{base}pr'", "secretName": "tok", "paginator": "page_number"},
        ids=(1,),
        resolver=resolver,
    )
    assert hits == []
    assert rows[0][2:] == (302, "error", "redirection non suivie")


def test_percent_encoded_dotdot_is_out_of_scope():
    from app.pipelines.connector_runtime import _url_within_scope

    assert not _url_within_scope(
        "https://api.allowed.example/v1", "https://api.allowed.example/v1/%2e%2e/admin"
    )


def test_preview_skipped_rows_do_not_wait_on_the_rate_limiter(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    t0 = time.monotonic()
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/pv')}'",
            "method": "POST",
            "requestsPerSecond": 0.2,
        },
        ids=(1, 2, 3, 4, 5),
        preview=True,
    )
    assert time.monotonic() - t0 < 2
    assert hits == []


def test_preview_deadline_skips_remaining_rows(conn, monkeypatch, httpserver):
    monkeypatch.setenv("CORE_PIPELINES_PREVIEW_TIMEOUT_S", "0")
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(
        lambda r: (hits.append(1), Response("x"))[1]
    )
    rows = run(conn, {"urlExpr": f"'{httpserver.url_for('/pv')}'"}, ids=(1, 2), preview=True)
    assert all(r[3:] == ("skipped", "délai d'aperçu dépassé") for r in rows)
    assert hits == []


def test_preview_does_not_retry(conn, httpserver):
    hits = []
    httpserver.expect_request("/pv").respond_with_handler(
        lambda r: (hits.append(1), Response("x", status=503))[1]
    )
    run(
        conn, {"urlExpr": f"'{httpserver.url_for('/pv')}'", "maxRetries": 3}, ids=(1,), preview=True
    )
    assert len(hits) == 1


def test_retries_also_wait_on_the_rate_limiter(conn, httpserver):
    stamps: list[float] = []
    httpserver.expect_request("/q").respond_with_handler(_recording_handler([503, 200], stamps))
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/q')}'",
            "requestsPerSecond": 5,
            "maxRetries": 1,
            "initialBackoffSeconds": 0,
        },
        ids=(1,),
    )
    stamps.sort()
    assert stamps[1] - stamps[0] >= 0.15


def test_cumulative_response_budget_turns_later_rows_into_errors(conn, monkeypatch, httpserver):
    monkeypatch.setenv("CORE_PIPELINES_HTTP_CALL_MAX_TOTAL_BYTES", "50")
    httpserver.expect_request("/b").respond_with_data("x" * 40)
    rows = run(
        conn,
        {"urlExpr": f"'{httpserver.url_for('/b')}'", "maxConcurrency": 1},
        ids=(1, 2, 3),
    )
    assert rows[0][3] == "success"
    errs = [r for r in rows if r[-1] == "budget de réponse dépassé"]
    assert len(errs) == 2 and all(r[1] is None for r in errs)


def test_form_body_skips_null_values_and_lowercases_bools(conn, httpserver):
    seen = _capture(httpserver)
    run(
        conn,
        {
            "urlExpr": f"'{httpserver.url_for('/c')}'",
            "method": "POST",
            "bodyType": "form",
            "bodyExpr": "json_object('a', NULL, 'b', true)",
        },
        ids=(3,),
    )
    assert seen["data"] == b"b=true"
