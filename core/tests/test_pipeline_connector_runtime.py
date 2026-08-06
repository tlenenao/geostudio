# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.pipelines import connector_runtime
from app.pipelines import egress as pipelines_egress
from app.pipelines.ops.schemas import ReaderConnectorRestParams
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def user(session, tenant):
    # `created_by` sur `connector_secrets` est une vraie FK vers `users.id`
    # (cf. app/secrets/models.py) — contrairement au brief initial qui
    # passait une chaîne littérale "u1", il faut un utilisateur réel pour ne
    # pas violer la contrainte sous SQLite (PRAGMA foreign_keys=ON).
    return get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="u1", username="u1",
        email=None, first_name="", last_name="",
    )


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    # Ces tests exercent le CONNECTEUR (dlt, pagination, injection d'auth),
    # pas la garde SSRF elle-même (déjà couverte isolément par
    # test_pipeline_egress.py) — le serveur pytest-httpserver écoute sur
    # 127.0.0.1, que la vraie garde bloquerait légitimement en tant que cible
    # loopback. Neutralisée ici pour isoler ce que ce fichier teste.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


def _create_secret(session, tenant, user, *, name, kind, payload):
    ciphertext, nonce = encrypt(payload)
    return secrets_repo.create_secret(
        session, tenant_id=tenant.id, created_by=user.id, name=name, kind=kind,
        ciphertext=ciphertext, nonce=nonce,
    )


def test_materialize_rest_connector_unauthenticated_no_pagination(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r1", params=params, view_name="node_r1",
    )
    rows = conn.execute("SELECT id, name FROM node_r1 ORDER BY id").fetchall()
    assert rows == [(1, "a"), (2, "b")]


def test_materialize_rest_connector_extracts_records_path(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json(
        {"data": {"items": [{"id": 1, "name": "a"}]}}
    )
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", recordsPath="data.items",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r2", params=params, view_name="node_r2",
    )
    rows = conn.execute("SELECT id, name FROM node_r2").fetchall()
    assert rows == [(1, "a")]


def test_materialize_rest_connector_injects_bearer_token(conn, session, tenant, user, httpserver):
    _create_secret(session, tenant, user, name="my-bearer", kind="bearer_token",
                    payload={"kind": "bearer_token", "token": "s3cr3t-tok"})
    httpserver.expect_request(
        "/items", headers={"Authorization": "Bearer s3cr3t-tok"},
    ).respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-bearer",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r3", params=params, view_name="node_r3",
    )
    assert conn.execute("SELECT id FROM node_r3").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_api_key_query_param(conn, session, tenant, user, httpserver):
    _create_secret(session, tenant, user, name="my-key", kind="api_key",
                    payload={"kind": "api_key", "location": "query", "key": "token", "value": "abc123"})
    httpserver.expect_request("/items", query_string="token=abc123").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-key",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r4", params=params, view_name="node_r4",
    )
    assert conn.execute("SELECT id FROM node_r4").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_basic_auth(conn, session, tenant, user, httpserver):
    _create_secret(session, tenant, user, name="my-basic", kind="basic_auth",
                    payload={"kind": "basic_auth", "username": "u", "password": "p"})
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-basic",
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r5", params=params, view_name="node_r5",
    )
    request = httpserver.log[0][0]
    assert request.headers["Authorization"].startswith("Basic ")


def test_materialize_rest_connector_paginates_page_number(conn, session, tenant, httpserver):
    httpserver.expect_request("/items", query_string="page=1").respond_with_json([{"id": 1}])
    httpserver.expect_request("/items", query_string="page=2").respond_with_json([{"id": 2}])
    httpserver.expect_request("/items", query_string="page=3").respond_with_json([])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", paginator="page_number",
        paginatorConfig={"pageParam": "page", "basePage": 1},
    )
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r6", params=params, view_name="node_r6",
    )
    rows = conn.execute("SELECT id FROM node_r6 ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]


def test_materialize_rest_connector_wrong_secret_kind_raises(conn, session, tenant, user, httpserver):
    _create_secret(session, tenant, user, name="pg-secret", kind="postgres_dsn",
                    payload={"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"})
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="pg-secret",
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.rest"):
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r7", params=params, view_name="node_r7",
        )


def test_materialize_rest_connector_missing_secret_raises(conn, session, tenant, httpserver):
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="does-not-exist",
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r8", params=params, view_name="node_r8",
        )


def test_materialize_rest_connector_drops_dlt_plumbing_columns(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn, session=session, tenant_id=tenant.id, node_id="r9", params=params, view_name="node_r9",
    )
    cols = {d[0] for d in conn.execute("SELECT * FROM node_r9 LIMIT 0").description}
    assert "_dlt_id" not in cols
    assert "_dlt_load_id" not in cols
    assert cols == {"id", "name"}
