# SPDX-License-Identifier: Apache-2.0
import os

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

# Capturée à l'import du module, AVANT que l'autouse fixture `_no_ssrf_guard`
# ne monkeypatch `pipelines_egress.assert_egress_allowed` — permet à un test
# isolé de réactiver la VRAIE garde (cf.
# test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard).
_REAL_ASSERT_EGRESS_ALLOWED = pipelines_egress.assert_egress_allowed


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


def test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard(
    monkeypatch, conn, session, tenant, user, httpserver,
):
    # Cette table réactive la VRAIE garde pour ce seul test : l'autouse
    # fixture `_no_ssrf_guard` neutralise `assert_egress_allowed` pour tout
    # ce fichier (les autres tests exercent le connecteur, pas la garde), ce
    # qui masquerait justement le trou SSRF qu'on veut couvrir ici.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_ASSERT_EGRESS_ALLOWED)
    _create_secret(
        session, tenant, user, name="my-oauth2", kind="oauth2_client_credentials",
        payload={
            "kind": "oauth2_client_credentials",
            # Cible loopback interdite par la vraie garde — aucune connexion
            # réelle n'est censée être tentée, la garde doit bloquer avant.
            "tokenUrl": "http://127.0.0.1:1/oauth/token",
            "clientId": "cid",
            "clientSecret": "csecret",
        },
    )
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"), path="items", secretName="my-oauth2",
    )
    # dlt exécute le générateur `_records` (donc le premier appel à
    # `auth.__call__` → `obtain_token()`) à l'intérieur de son propre pipeline
    # d'extraction, et enveloppe toute exception levée là dans
    # `ResourceExtractionError` puis `PipelineStepFailed` (chaîné via
    # `__cause__`) plutôt que de la laisser remonter telle quelle — vérifié
    # empiriquement, pas dans la doc dlt. Le test doit donc chercher
    # `EgressBlockedError` dans la chaîne de causes, pas au premier niveau.
    with pytest.raises(Exception) as excinfo:
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r10", params=params, view_name="node_r10",
        )
    exc = excinfo.value
    while exc is not None and not isinstance(exc, pipelines_egress.EgressBlockedError):
        exc = exc.__cause__
    assert isinstance(exc, pipelines_egress.EgressBlockedError), (
        f"expected EgressBlockedError somewhere in the cause chain of {excinfo.value!r}"
    )
    assert "127.0.0.1" in str(exc)


def test_materialize_rest_connector_data_url_egress_block_raises_connector_runtime_error(
    monkeypatch, conn, session, tenant,
):
    # Contrepartie du test OAuth2 ci-dessus, mais pour l'URL de DONNÉES (pas
    # l'URL de jeton) : réactive la VRAIE garde pour ce seul test, cible un
    # hôte loopback interdit comme baseUrl. Avant Finding #1, cette
    # EgressBlockedError (enveloppée par dlt en ResourceExtractionError/
    # PipelineStepFailed) fuyait telle quelle hors de
    # materialize_rest_connector — ici on vérifie qu'elle ressort traduite en
    # ConnectorRuntimeError, avec un message qui rend le blocage SSRF aussi
    # lisible qu'un rejet pré-flight (secret manquant, mauvais type...).
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_ASSERT_EGRESS_ALLOWED)
    params = ReaderConnectorRestParams(baseUrl="http://127.0.0.1:1/", path="items")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="egress blocked"):
        connector_runtime.materialize_rest_connector(
            conn, session=session, tenant_id=tenant.id, node_id="r11", params=params, view_name="node_r11",
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


from app.analytics.sql_sandbox import SqlSandboxError  # noqa: E402
from app.pipelines.ops.schemas import ReaderConnectorPostgresParams  # noqa: E402


def _pg_dsn(pg_engine) -> str:
    # Même conversion que conftest.py::pg_engine_with_procrastinate_schema :
    # CORE_TEST_DATABASE_URL est au format SQLAlchemy "postgresql+psycopg://",
    # le DSN d'un secret postgres_dsn est un DSN "postgresql://" ordinaire
    # (format vérifié par SP-15e's test_secrets_repository.py). Lu depuis la
    # variable d'environnement (comme conftest.py) plutôt que via
    # `str(pg_engine.url)` : `URL.__str__` masque le mot de passe
    # (`gis:***@...`) et casserait l'authentification — vérifié
    # empiriquement (échec `password authentication failed`), pas dans la
    # doc SQLAlchemy.
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
def pg_secret(session, tenant, user, pg_engine):
    # `_create_secret` (défini plus haut dans ce fichier) exige un `user`
    # réel (FK `created_by` sur `connector_secrets`) — absent de la
    # signature donnée par le brief SP-15f, adapté ici pour matcher l'état
    # réel de ce module (cf. autres tests de ce fichier, ex. `my-bearer`).
    return _create_secret(
        session, tenant, user, name="warehouse-pg", kind="postgres_dsn",
        payload={"kind": "postgres_dsn", "dsn": _pg_dsn(pg_engine)},
    )


def test_materialize_postgres_connector_round_trips_query(conn, session, tenant, pg_engine, pg_secret):
    from sqlalchemy import text

    with pg_engine.begin() as db_conn:
        db_conn.execute(text("CREATE TABLE IF NOT EXISTS sp15f_towns (id int, name text)"))
        db_conn.execute(text("DELETE FROM sp15f_towns"))
        db_conn.execute(text("INSERT INTO sp15f_towns (id, name) VALUES (1, 'Nord'), (2, 'Sud')"))

    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="SELECT id, name FROM sp15f_towns ORDER BY id")
    connector_runtime.materialize_postgres_connector(
        conn, session=session, tenant_id=tenant.id, node_id="p1", params=params, view_name="node_p1",
    )
    rows = conn.execute("SELECT id, name FROM node_p1 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]


def test_materialize_postgres_connector_rejects_non_select(conn, session, tenant, pg_secret):
    params = ReaderConnectorPostgresParams(secretName="warehouse-pg", query="DELETE FROM sp15f_towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p2", params=params, view_name="node_p2",
        )


def test_materialize_postgres_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(session, tenant, user, name="bearer-secret", kind="bearer_token",
                    payload={"kind": "bearer_token", "token": "tok"})
    params = ReaderConnectorPostgresParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.postgres"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p3", params=params, view_name="node_p3",
        )


def test_materialize_postgres_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorPostgresParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_postgres_connector(
            conn, session=session, tenant_id=tenant.id, node_id="p4", params=params, view_name="node_p4",
        )
