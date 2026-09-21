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
        session,
        tenant_id=tenant.id,
        oidc_sub="u1",
        username="u1",
        email=None,
        first_name="",
        last_name="",
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
        session,
        tenant_id=tenant.id,
        created_by=user.id,
        name=name,
        kind=kind,
        ciphertext=ciphertext,
        nonce=nonce,
    )


def test_materialize_rest_connector_unauthenticated_no_pagination(
    conn, session, tenant, httpserver
):
    httpserver.expect_request("/items").respond_with_json(
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    )
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r1",
        params=params,
        view_name="node_r1",
    )
    rows = conn.execute("SELECT id, name FROM node_r1 ORDER BY id").fetchall()
    assert rows == [(1, "a"), (2, "b")]


def test_materialize_rest_connector_extracts_records_path(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json(
        {"data": {"items": [{"id": 1, "name": "a"}]}}
    )
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        recordsPath="data.items",
    )
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r2",
        params=params,
        view_name="node_r2",
    )
    rows = conn.execute("SELECT id, name FROM node_r2").fetchall()
    assert rows == [(1, "a")]


def test_materialize_rest_connector_injects_bearer_token(conn, session, tenant, user, httpserver):
    _create_secret(
        session,
        tenant,
        user,
        name="my-bearer",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "s3cr3t-tok"},
    )
    httpserver.expect_request(
        "/items",
        headers={"Authorization": "Bearer s3cr3t-tok"},
    ).respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="my-bearer",
    )
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r3",
        params=params,
        view_name="node_r3",
    )
    assert conn.execute("SELECT id FROM node_r3").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_api_key_query_param(
    conn, session, tenant, user, httpserver
):
    _create_secret(
        session,
        tenant,
        user,
        name="my-key",
        kind="api_key",
        payload={"kind": "api_key", "location": "query", "key": "token", "value": "abc123"},
    )
    httpserver.expect_request("/items", query_string="token=abc123").respond_with_json(
        [{"id": 1, "name": "a"}]
    )
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="my-key",
    )
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r4",
        params=params,
        view_name="node_r4",
    )
    assert conn.execute("SELECT id FROM node_r4").fetchall() == [(1,)]


def test_materialize_rest_connector_injects_basic_auth(conn, session, tenant, user, httpserver):
    _create_secret(
        session,
        tenant,
        user,
        name="my-basic",
        kind="basic_auth",
        payload={"kind": "basic_auth", "username": "u", "password": "p"},
    )
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="my-basic",
    )
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r5",
        params=params,
        view_name="node_r5",
    )
    request = httpserver.log[0][0]
    assert request.headers["Authorization"].startswith("Basic ")


def test_materialize_rest_connector_paginates_page_number(conn, session, tenant, httpserver):
    httpserver.expect_request("/items", query_string="page=1").respond_with_json([{"id": 1}])
    httpserver.expect_request("/items", query_string="page=2").respond_with_json([{"id": 2}])
    httpserver.expect_request("/items", query_string="page=3").respond_with_json([])
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        paginator="page_number",
        paginatorConfig={"pageParam": "page", "basePage": 1},
    )
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r6",
        params=params,
        view_name="node_r6",
    )
    rows = conn.execute("SELECT id FROM node_r6 ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]


def test_materialize_rest_connector_wrong_secret_kind_raises(
    conn, session, tenant, user, httpserver
):
    _create_secret(
        session,
        tenant,
        user,
        name="pg-secret",
        kind="postgres_dsn",
        payload={"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"},
    )
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="pg-secret",
    )
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.rest"
    ):
        connector_runtime.materialize_rest_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="r7",
            params=params,
            view_name="node_r7",
        )


def test_materialize_rest_connector_missing_secret_raises(conn, session, tenant, httpserver):
    params = ReaderConnectorRestParams(
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="does-not-exist",
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_rest_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="r8",
            params=params,
            view_name="node_r8",
        )


def test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard(
    monkeypatch,
    conn,
    session,
    tenant,
    user,
    httpserver,
):
    # Cette table réactive la VRAIE garde pour ce seul test : l'autouse
    # fixture `_no_ssrf_guard` neutralise `assert_egress_allowed` pour tout
    # ce fichier (les autres tests exercent le connecteur, pas la garde), ce
    # qui masquerait justement le trou SSRF qu'on veut couvrir ici.
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_ASSERT_EGRESS_ALLOWED)
    _create_secret(
        session,
        tenant,
        user,
        name="my-oauth2",
        kind="oauth2_client_credentials",
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
        baseUrl=httpserver.url_for("/"),
        path="items",
        secretName="my-oauth2",
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
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="r10",
            params=params,
            view_name="node_r10",
        )
    exc = excinfo.value
    while exc is not None and not isinstance(exc, pipelines_egress.EgressBlockedError):
        exc = exc.__cause__
    assert isinstance(exc, pipelines_egress.EgressBlockedError), (
        f"expected EgressBlockedError somewhere in the cause chain of {excinfo.value!r}"
    )
    assert "127.0.0.1" in str(exc)


def test_materialize_rest_connector_data_url_egress_block_raises_connector_runtime_error(
    monkeypatch,
    conn,
    session,
    tenant,
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
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="r11",
            params=params,
            view_name="node_r11",
        )


def test_materialize_rest_connector_drops_dlt_plumbing_columns(conn, session, tenant, httpserver):
    httpserver.expect_request("/items").respond_with_json([{"id": 1, "name": "a"}])
    params = ReaderConnectorRestParams(baseUrl=httpserver.url_for("/"), path="items")
    connector_runtime.materialize_rest_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="r9",
        params=params,
        view_name="node_r9",
    )
    cols = {d[0] for d in conn.execute("SELECT * FROM node_r9 LIMIT 0").description}
    assert "_dlt_id" not in cols
    assert "_dlt_load_id" not in cols
    assert cols == {"id", "name"}


from app.pipelines.ops.schemas import (  # noqa: E402
    ReaderConnectorPostgresParams,
    ReaderConnectorSnowflakeParams,
)


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
        session,
        tenant,
        user,
        name="warehouse-pg",
        kind="postgres_dsn",
        payload={"kind": "postgres_dsn", "dsn": _pg_dsn(pg_engine)},
    )


def test_materialize_postgres_connector_round_trips_query(
    conn, session, tenant, pg_engine, pg_secret
):
    from sqlalchemy import text

    with pg_engine.begin() as db_conn:
        db_conn.execute(text("CREATE TABLE IF NOT EXISTS sp15f_towns (id int, name text)"))
        db_conn.execute(text("DELETE FROM sp15f_towns"))
        db_conn.execute(text("INSERT INTO sp15f_towns (id, name) VALUES (1, 'Nord'), (2, 'Sud')"))

    params = ReaderConnectorPostgresParams(
        secretName="warehouse-pg", query="SELECT id, name FROM sp15f_towns ORDER BY id"
    )
    connector_runtime.materialize_postgres_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="p1",
        params=params,
        view_name="node_p1",
    )
    rows = conn.execute("SELECT id, name FROM node_p1 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]


def test_materialize_postgres_connector_rejects_non_select(conn, session, tenant, pg_secret):
    params = ReaderConnectorPostgresParams(
        secretName="warehouse-pg", query="DELETE FROM sp15f_towns"
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_postgres_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="p2",
            params=params,
            view_name="node_p2",
        )


def test_materialize_postgres_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorPostgresParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.postgres"
    ):
        connector_runtime.materialize_postgres_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="p3",
            params=params,
            view_name="node_p3",
        )


def test_materialize_postgres_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorPostgresParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_postgres_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="p4",
            params=params,
            view_name="node_p4",
        )


def test_materialize_snowflake_connector_rejects_non_select(conn, session, tenant):
    params = ReaderConnectorSnowflakeParams(secretName="does-not-matter", query="DELETE FROM towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_snowflake_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="sf1",
            params=params,
            view_name="node_sf1",
        )


def test_materialize_snowflake_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorSnowflakeParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.snowflake"
    ):
        connector_runtime.materialize_snowflake_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="sf2",
            params=params,
            view_name="node_sf2",
        )


def test_materialize_snowflake_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorSnowflakeParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_snowflake_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="sf3",
            params=params,
            view_name="node_sf3",
        )


def test_snowflake_dialect_resolves_lazily_without_network():
    # Vérifie la forme du DSN (design §2.2/§3.3) sans se connecter à un
    # compte réel : sa.create_engine() est paresseux (aucun appel réseau
    # avant .connect()) — ce test échouerait si snowflake-sqlalchemy
    # n'était pas installé, ou si le DSN n'était pas de la forme attendue.
    # Aucune fixture DB nécessaire (pas de session, pas de connexion) —
    # import local de sqlalchemy, même convention que le `from sqlalchemy
    # import text` local de test_materialize_postgres_connector_round_trips_query
    # dans ce même fichier (aucun import sqlalchemy au niveau module ici).
    import sqlalchemy as sa

    engine = sa.create_engine(
        "snowflake://u:s3cr3t-pass@myaccount/mydb/myschema?warehouse=wh1&role=role1"
    )
    try:
        assert engine.dialect.name == "snowflake"
        assert "s3cr3t-pass" not in str(engine.url)  # le mot de passe est masqué par défaut
    finally:
        engine.dispose()


@pytest.mark.snowflake
def test_materialize_snowflake_connector_round_trips_query(
    conn, session, tenant, user, snowflake_test_dsn
):
    # MANUEL UNIQUEMENT (design §12/§3.3, Global Constraints) : requiert un
    # compte Snowflake réel, jamais câblé en CI. La table `sp_gap16_towns`
    # doit exister dans le schéma/warehouse référencé par
    # CORE_TEST_SNOWFLAKE_DSN avec au moins les colonnes (id int, name
    # varchar) — à créer manuellement une fois avant de lancer ce test :
    #   CREATE OR REPLACE TABLE sp_gap16_towns (id INT, name VARCHAR);
    #   INSERT INTO sp_gap16_towns VALUES (1, 'Nord'), (2, 'Sud');
    _create_secret(
        session,
        tenant,
        user,
        name="warehouse-sf",
        kind="snowflake_dsn",
        payload={"kind": "snowflake_dsn", "dsn": snowflake_test_dsn},
    )
    params = ReaderConnectorSnowflakeParams(
        secretName="warehouse-sf", query="SELECT id, name FROM sp_gap16_towns ORDER BY id"
    )
    connector_runtime.materialize_snowflake_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
        node_id="sf4",
        params=params,
        view_name="node_sf4",
    )
    rows = conn.execute("SELECT id, name FROM node_sf4 ORDER BY id").fetchall()
    assert rows == [(1, "Nord"), (2, "Sud")]


from app.pipelines.ops.schemas import ReaderConnectorBigQueryParams  # noqa: E402

# Clé RSA jetable générée localement pour ce fichier de test uniquement
# (jamais associée à un vrai compte de service Google) — nécessaire car
# sa.create_engine() pour le dialecte "bigquery" n'est PAS totalement
# paresseux comme pour postgres/snowflake : il construit localement un objet
# google.auth.service_account.Credentials à partir du JSON embarqué dans
# `credentials_base64`, ce qui exige une clé syntaxiquement valide (vérifié
# empiriquement : un JSON avec une clé absente/mal formée échoue ici, avant
# tout appel réseau, cf. BigQueryDsnPayload).
_FAKE_SERVICE_ACCOUNT_RSA_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCzr+PZqf6u837c
j+igCwaoMBhlnWDEuHMSmOLH/cDkZdV6R+p2RZSQ00ZSBCMpLL/EyDqcE2wjilUr
ySpLTjbw27xXnBoFw9MZH2iuIF366EnBAKg50foQSZPMZZFso1jFvYvSrsbYMNOp
NdrLtQ25YpXAj/mogwUX1ToJTaDBvel7QrXAcdhRA0CURgD91DtU+l6VRh3CrvP6
GyT7KtExILLMlE5eq3TVHSy48E8/BuVdLNBdSOEqOjJXYP/m3/m7jeqG07tfA3wB
ps9BtP9CqGq/urd2oz1mhz10I9PhM7my5bgiOLHZBvg1ptXnAH33kAh7wN8zcVnk
JHl8UWoHAgMBAAECggEAPp82EU2lbON/eu7Ma7pr/4GDfyZx6x09PWX64ygUaYTz
+UHG/KETPcXj5AF9H4Rw8Ou3QV2jel9jf3cEPmpry1VJNl840nmEwGSp3sV4+1Cp
I5JPDpeXRsXdtIZRQENNVNzSNgKjWgTqPzZ9ojDfL5SkDBAhOhEvXTb6mvNq6xnm
Y64hcTwTDxyoG5Qos6sss53Vv5J+igyjtD1yG3CJXyuTKPGDjdudSQYVYvzQBeVr
OJzri0B1va1KaFEhmusv7y4NT+XFmpJcbFcNM0RifbbAZEpLeQ1br7B6IMzxvOIw
DZdfHiEdccRBd7QkHBKvDbkJuCDxOGm0gG2BoCP6wQKBgQDsvX4TwfZpljD3CKYN
z1QMgIxE71EY8yc8bKpfpCoaCfGE7DB01DC+LGFKrQEdoZsaoZdkItUQDru3QPqw
qIzN7UC+VZxDUcvRXcl0CEtk9nhHtyKTFVX4ZI2jUD0/jCoF6OABIHXddgZNN5b2
oqBp43GiFKI5himdBYBmwilwWwKBgQDCTivfPnFXeGGVlKIkxQIyQC6CxHD1yQnZ
b9Zh45JH+A21C0nLvT2GdLBsZCRsIyTDT/s8+MVnJD9ap571LBGXpicxanq/VU9w
jN7z/cQaI7vzBwozlgRRJVjO8J8WD2mAUpeM+x+BaYd9wXlHMGSdzYyybXTNYmAS
el7Tt6wcxQKBgD5xRL3lXR9AdC3UZCgkVWDuzxCnptZT3Dd92fpcDJbNpJyQx78o
8KpYflj6BN9R7t05XfsVjOktWaneQ8Ew0+LE/1y0rAC9pGrWt/oY7fn1YIhZ746o
BAL+UrWOxnjqeXMRl3P0oeIF7WeUkAcBohoL2b8MfjV6A6Pc/Z8c+10dAoGAKqSb
TkhW+Zpq2Dghia5O+BZL3tkb7WUsqzK3Ow6FuRPAdl4+2N70VMDhQziLIcxoshCo
k84JDMTQvqWQ5j/AsKZ/bYHv5HPllk7kU2n7Er2K7yA5Ze7jjaeDoQ7/6wiA3+/A
YOlwFafCW6ANbMk7G8LTwQjynGydpxCCJTbnJ/0CgYEAkBsMsYzGFA3dax2SjEuu
kzSMd5CNRnSUIEvkEtwtuFWwVSBp+EmEuL/j67+XdJ1V9/hVh8QsriWVlr3gbS5F
ObcY9WWAl9CwLRlBjp2QKQRzbg1P1608gcqA3ePi7/psTO332q3YBR1nYe7s7VRV
orLyAE2SpSrRYUkemuAJaoA=
-----END PRIVATE KEY-----
"""


def _bigquery_dsn() -> str:
    import base64
    import json

    info = {
        "type": "service_account",
        "project_id": "sp15f-test-project",
        "private_key_id": "abc123",
        "private_key": _FAKE_SERVICE_ACCOUNT_RSA_PEM,
        "client_email": "sp15f-test@sp15f-test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    encoded = base64.b64encode(json.dumps(info).encode()).decode()
    return f"bigquery://sp15f-test-project/sp15f_dataset?credentials_base64={encoded}"


def test_materialize_bigquery_connector_rejects_non_select(conn, session, tenant):
    params = ReaderConnectorBigQueryParams(secretName="does-not-matter", query="DELETE FROM towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_bigquery_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="bq1",
            params=params,
            view_name="node_bq1",
        )


def test_materialize_bigquery_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorBigQueryParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.bigquery"
    ):
        connector_runtime.materialize_bigquery_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="bq2",
            params=params,
            view_name="node_bq2",
        )


def test_materialize_bigquery_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorBigQueryParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_bigquery_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="bq3",
            params=params,
            view_name="node_bq3",
        )


def test_bigquery_dialect_resolves_without_network_given_well_formed_credentials():
    # Vérifie la forme du DSN (BigQueryDsnPayload) sans se connecter à un
    # vrai projet BigQuery. Contrairement à
    # test_snowflake_dialect_resolves_lazily_without_network, sa.create_engine()
    # n'est PAS totalement paresseux pour ce dialecte : il construit
    # localement des Credentials à partir du JSON de compte de service
    # embarqué dans `credentials_base64` — d'où l'usage d'une clé RSA
    # syntaxiquement valide (bien que jetable) plutôt que d'un texte
    # arbitraire, sans quoi cet appel échouerait localement avant même
    # d'atteindre ce test. Aucun appel réseau n'a lieu ici (pas de
    # .connect()) — vérifié empiriquement (design Vague 2 §6.1).
    import sqlalchemy as sa

    engine = sa.create_engine(_bigquery_dsn())
    try:
        assert engine.dialect.name == "bigquery"
    finally:
        engine.dispose()


from app.pipelines.ops.schemas import ReaderConnectorMssqlParams  # noqa: E402


def test_materialize_mssql_connector_rejects_non_select(conn, session, tenant):
    params = ReaderConnectorMssqlParams(secretName="does-not-matter", query="DELETE FROM towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_mssql_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ms1",
            params=params,
            view_name="node_ms1",
        )


def test_materialize_mssql_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorMssqlParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.mssql"
    ):
        connector_runtime.materialize_mssql_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ms2",
            params=params,
            view_name="node_ms2",
        )


def test_materialize_mssql_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorMssqlParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_mssql_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ms3",
            params=params,
            view_name="node_ms3",
        )


def test_mssql_dialect_resolves_lazily_without_network():
    # Vérifie la forme du DSN (Vague 2 §6.1) sans se connecter à un vrai
    # serveur : comme pour postgres/snowflake (et contrairement à bigquery,
    # cf. ci-dessus), sa.create_engine() pour le dialecte "mssql+pymssql"
    # est paresseux — aucun appel réseau avant .connect(). Ce test
    # échouerait si pymssql n'était pas installé, ou si le DSN n'était pas
    # de la forme attendue (mssql+pymssql://user:pass@host:port/dbname,
    # cf. ReaderConnectorMssqlParams).
    import sqlalchemy as sa

    engine = sa.create_engine("mssql+pymssql://u:s3cr3t-pass@myhost:1433/mydb")
    try:
        assert engine.dialect.name == "mssql"
        assert engine.dialect.driver == "pymssql"
        assert "s3cr3t-pass" not in str(engine.url)  # le mot de passe est masqué par défaut
    finally:
        engine.dispose()


from app.pipelines.ops.schemas import ReaderConnectorOracleParams  # noqa: E402


def test_materialize_oracle_connector_rejects_non_select(conn, session, tenant):
    params = ReaderConnectorOracleParams(secretName="does-not-matter", query="DELETE FROM towns")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="query rejected"):
        connector_runtime.materialize_oracle_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ora1",
            params=params,
            view_name="node_ora1",
        )


def test_materialize_oracle_connector_wrong_secret_kind_raises(conn, session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="bearer-secret",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "tok"},
    )
    params = ReaderConnectorOracleParams(secretName="bearer-secret", query="SELECT 1")
    with pytest.raises(
        connector_runtime.ConnectorRuntimeError, match="not usable by reader.connector.oracle"
    ):
        connector_runtime.materialize_oracle_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ora2",
            params=params,
            view_name="node_ora2",
        )


def test_materialize_oracle_connector_missing_secret_raises(conn, session, tenant):
    params = ReaderConnectorOracleParams(secretName="does-not-exist", query="SELECT 1")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="not found"):
        connector_runtime.materialize_oracle_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id),
            node_id="ora3",
            params=params,
            view_name="node_ora3",
        )


def test_oracle_dialect_resolves_lazily_in_thin_mode_without_network():
    # Vérifie la forme du DSN (Vague 2 §6.1) sans se connecter à un vrai
    # serveur : comme pour postgres/snowflake/mssql (et contrairement à
    # bigquery, cf. ci-dessus), sa.create_engine() pour le dialecte
    # "oracle+oracledb" est paresseux — aucun appel réseau avant .connect()
    # (vérifié empiriquement : retour immédiat, aucune exception). Vérifie
    # aussi que le mode thin (pur Python, sans client Oracle natif) est bien
    # celui utilisé par défaut, sans appel explicite à
    # oracledb.init_oracle_client() ni thick_mode=True — vérifié
    # empiriquement contre oracledb.is_thin_mode() (True par défaut avant
    # toute connexion, cf. ReaderConnectorOracleParams/OracleDsnPayload pour
    # la vérification contre le code source réel du dialecte SQLAlchemy).
    import oracledb
    import sqlalchemy as sa

    engine = sa.create_engine(
        "oracle+oracledb://scott:s3cr3t-pass@myhost:1521/?service_name=orclpdb1"
    )
    try:
        assert engine.dialect.name == "oracle"
        assert engine.dialect.driver == "oracledb"
        assert "s3cr3t-pass" not in str(engine.url)  # le mot de passe est masqué par défaut
        assert oracledb.is_thin_mode() is True
    finally:
        engine.dispose()


def test_postgres_secret_resolver_get_returns_payload(session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="my-bearer",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "s3cr3t-tok"},
    )
    resolver = connector_runtime.PostgresSecretResolver(session, tenant.id)
    payload = resolver.get("my-bearer")
    assert payload.kind == "bearer_token"
    assert payload.token == "s3cr3t-tok"


def test_postgres_secret_resolver_get_raises_keyerror_when_missing(session, tenant):
    resolver = connector_runtime.PostgresSecretResolver(session, tenant.id)
    with pytest.raises(KeyError):
        resolver.get("does-not-exist")


def test_postgres_secret_resolver_get_does_not_mask_backend_failure_as_not_found(
    session, tenant, user, monkeypatch
):
    # Un secret RÉEL existe (donc le "not found" serait faux), mais le
    # backend de chiffrement ne peut pas déchiffrer sans
    # CORE_SECRETS_MASTER_KEY (cf. app.secrets.crypto.load_master_key) : la
    # KeyError('CORE_SECRETS_MASTER_KEY') levée par os.environ[...] ne doit
    # jamais être confondue avec la KeyError(name) « secret absent » de ce
    # Protocol.
    _create_secret(
        session,
        tenant,
        user,
        name="my-bearer",
        kind="bearer_token",
        payload={"kind": "bearer_token", "token": "s3cr3t-tok"},
    )
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    resolver = connector_runtime.PostgresSecretResolver(session, tenant.id)
    with pytest.raises(RuntimeError) as exc_info:
        resolver.get("my-bearer")
    message = str(exc_info.value)
    assert "not found" not in message
    assert "CORE_SECRETS_MASTER_KEY" in message
