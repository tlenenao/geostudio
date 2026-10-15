# SPDX-License-Identifier: Apache-2.0
"""Voie R FME : nouveaux kinds de secret — `oauth2_client` (jeton obtenu/renouvelé à
l'exécution par reader.cloudfile & co) et `mongodb_uri` (reader.mongodb)."""

import datetime as dt
import json

import bson
import duckdb
import pytest
from bson.raw_bson import RawBSONDocument
from pydantic import ValidationError

from app.audit.models import AuditLog
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import egress as pipelines_egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import cloudfiles as cf
from app.pipelines.ops import dbio2
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.pipelines.registries import READERS
from app.secrets import repository as secrets_repo
from app.secrets.crypto import decrypt, encrypt
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretCreate
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
_REAL_EGRESS_GUARD = pipelines_egress.assert_egress_allowed
CSV = b"id,nom\n1,a\n2,b\n"


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def user(session, tenant):
    return get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="u1", username="u1",
        email=None, first_name="", last_name="",
    )  # fmt: skip


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    monkeypatch.setattr(cf, "_REQUIRE_TLS_FOR_SECRETS", False)
    cf._TOKEN_CACHE.clear()
    yield
    cf._TOKEN_CACHE.clear()


def _secret(session, tenant, user, name, payload):
    ct, nonce = encrypt(payload)
    secrets_repo.create_secret(
        session, tenant_id=tenant.id, created_by=user.id, name=name,
        kind=payload["kind"], ciphertext=ct, nonce=nonce,
    )  # fmt: skip
    session.commit()


def _read(fn, conn, session, tenant, user, **params):
    return fn(
        conn, session=session, tenant_id=tenant.id, node_id="n", view_name="node_n",
        user=user, base_uri="", params=params,
    )  # fmt: skip


# ------------------------------------------------------------------ schémas


def test_oauth2_client_schema():
    ok = SecretCreate.model_validate({"name": "dbx", "payload": {
        "kind": "oauth2_client", "grantType": "refresh_token", "tokenUrl": "https://t.example/tok",
        "clientId": "c", "clientSecret": "s", "refreshToken": "r", "baseUrl": "https://api.example",
    }})  # fmt: skip
    assert ok.payload.kind == "oauth2_client" and ok.payload.refreshToken == "r"
    base = {"kind": "oauth2_client", "tokenUrl": "https://t.example/tok", "clientId": "c",
            "clientSecret": "s"}  # fmt: skip
    assert SECRET_PAYLOAD_ADAPTER.validate_python(base).grantType == "client_credentials"
    with pytest.raises(ValidationError, match="refreshToken is required"):
        SECRET_PAYLOAD_ADAPTER.validate_python({**base, "grantType": "refresh_token"})
    for bad in ("ftp://t.example", "https://u:p@t.example/tok", "https://t.example/?a=1"):
        with pytest.raises(ValidationError):
            SECRET_PAYLOAD_ADAPTER.validate_python({**base, "tokenUrl": bad})


def test_mongodb_uri_schema():
    p = SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "mongodb_uri", "uri": "mongodb+srv://h"})
    assert p.uri == "mongodb+srv://h"
    with pytest.raises(ValidationError):
        SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "mongodb_uri", "uri": "http://h"})


# ------------------------------------------------------------------ oauth2_client


def _dropbox(httpserver, monkeypatch, expect_token="ACCESS"):
    monkeypatch.setitem(cf._API, "dropbox", httpserver.url_for(""))
    httpserver.expect_request(
        "/2/files/download", method="POST", headers={"Authorization": f"Bearer {expect_token}"}
    ).respond_with_data(CSV)


def test_client_credentials_token_is_fetched_cached_and_used(
    httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token", method="POST").respond_with_json(
        {"access_token": "ACCESS", "token_type": "Bearer", "expires_in": 3600}
    )
    _dropbox(httpserver, monkeypatch)
    _secret(session, tenant, user, "s", {
        "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
        "clientId": "CID", "clientSecret": "CSECRET", "scope": "files.read",
        "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip
    for _ in range(2):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="s")  # fmt: skip
        conn.execute("DROP TABLE node_n")
    token_calls = [r for r, _ in httpserver.log if r.path == "/oauth/token"]
    assert len(token_calls) == 1  # 2e run servi par le cache mémoire
    assert dict(token_calls[0].form) == {
        "grant_type": "client_credentials", "client_id": "CID", "client_secret": "CSECRET",
        "scope": "files.read",
    }  # fmt: skip
    assert "Authorization" not in token_calls[0].headers  # rien d'autre que le formulaire


def test_refresh_token_rotation_is_written_back_to_the_vault(
    httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token", method="POST").respond_with_json(
        {"access_token": "ACCESS", "expires_in": 3600, "refresh_token": "R2"}
    )
    _dropbox(httpserver, monkeypatch)
    _secret(session, tenant, user, "s", {
        "kind": "oauth2_client", "grantType": "refresh_token",
        "tokenUrl": httpserver.url_for("/oauth/token"), "clientId": "CID",
        "clientSecret": "CSECRET", "refreshToken": "R1", "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox", file="/f.csv",
          secretName="s")  # fmt: skip
    form = dict(httpserver.log[0][0].form)
    assert form["grant_type"] == "refresh_token" and form["refresh_token"] == "R1"
    session.expire_all()
    row = secrets_repo.get_secret_by_name(session, tenant_id=tenant.id, name="s")
    stored = decrypt(row.ciphertext, row.nonce)
    assert stored["refreshToken"] == "R2" and stored["clientSecret"] == "CSECRET"
    audits = session.query(AuditLog).filter_by(action="secret.oauth2_refresh_rotated").all()
    assert len(audits) == 1 and "R2" not in json.dumps(audits[0].payload)
    # cache vidé : le run suivant présente le refresh_token renouvelé
    cf._TOKEN_CACHE.clear()
    conn.execute("DROP TABLE node_n")
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox", file="/f.csv",
          secretName="s")  # fmt: skip
    token_calls = [r for r, _ in httpserver.log if r.path == "/oauth/token"]
    assert dict(token_calls[-1].form)["refresh_token"] == "R2"


def test_token_endpoint_redirect_is_never_followed(
    httpserver, monkeypatch, conn, session, tenant, user
):
    """Le client_secret ne suit jamais une redirection (307 rejouerait le POST ailleurs)."""
    from pytest_httpserver import HTTPServer

    with HTTPServer() as other:
        other.expect_request("/steal").respond_with_json({"access_token": "X"})
        httpserver.expect_request("/oauth/token").respond_with_data(
            "", status=307, headers={"Location": other.url_for("/steal")}
        )
        _dropbox(httpserver, monkeypatch)
        _secret(session, tenant, user, "s", {
            "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
            "clientId": "CID", "clientSecret": "CSECRET", "baseUrl": httpserver.url_for("/"),
        })  # fmt: skip
        with pytest.raises(PipelineRuntimeError, match="too many redirects"):
            _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
                  file="/f.csv", secretName="s")  # fmt: skip
        assert other.log == []


@pytest.mark.parametrize("status, body, msg", [
    (401, b'{"error": "invalid_client", "client": "CSECRET"}', "HTTP 401"),
    (200, b'{"token_type": "bearer"}', "unexpected OAuth2 token answer"),
    (200, b"not json", "unexpected OAuth2 token answer"),
    (200, b'{"access_token": "A", "token_type": "mac"}', "not 'bearer'"),
])  # fmt: skip
def test_token_errors_never_leak_secrets(
    status, body, msg, httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token").respond_with_data(body, status=status)
    _dropbox(httpserver, monkeypatch)
    _secret(session, tenant, user, "s", {
        "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
        "clientId": "CID", "clientSecret": "CSECRET", "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match=msg) as exc:
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="s")  # fmt: skip
    assert "CSECRET" not in str(exc.value) and "CID" not in str(exc.value)
    assert [r.path for r, _ in httpserver.log] == ["/oauth/token"]  # rien téléchargé


def test_token_url_requires_https_and_egress(monkeypatch, conn, session, tenant, user):
    _secret(session, tenant, user, "s", {
        "kind": "oauth2_client", "tokenUrl": "http://t.example/tok", "clientId": "c",
        "clientSecret": "s", "baseUrl": "https://content.dropboxapi.com/",
    })  # fmt: skip
    monkeypatch.setattr(cf, "_REQUIRE_TLS_FOR_SECRETS", True)
    with pytest.raises(PipelineRuntimeError, match="tokenUrl must use https"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="s")  # fmt: skip
    _secret(session, tenant, user, "s2", {
        "kind": "oauth2_client", "tokenUrl": "https://127.0.0.1/tok", "clientId": "c",
        "clientSecret": "s", "baseUrl": "https://content.dropboxapi.com/",
    })  # fmt: skip
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="s2")  # fmt: skip


def test_access_token_stays_within_base_url_and_azurefiles(
    httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token").respond_with_json({"access_token": "AAD"})
    _secret(session, tenant, user, "s", {
        "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
        "clientId": "c", "clientSecret": "s", "scope": "https://storage.azure.com/.default",
        "baseUrl": "https://evil.example/",
    })  # fmt: skip
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    with pytest.raises(PipelineRuntimeError, match="baseUrl must cover"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s")  # fmt: skip
    assert not [r for r, _ in httpserver.log if r.path.startswith("/2.0")]
    # Azure Files + jeton Azure AD : Bearer + en-têtes x-ms obligatoires
    _secret(session, tenant, user, "az", {
        "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
        "clientId": "c2", "clientSecret": "s2", "scope": "https://storage.azure.com/.default",
        "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip
    httpserver.expect_request(
        "/share/dir/f.csv", headers={"Authorization": "Bearer AAD", "x-ms-version": "2022-11-02"}
    ).respond_with_data(CSV)
    real = cf._cloudfile_request

    def local(p):
        req = real(p)
        req["url"] = httpserver.url_for("/share/dir/f.csv")
        return req

    monkeypatch.setattr(cf, "_cloudfile_request", local)
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="azurefiles",
          file="dir/f.csv", account="acct", share="share", secretName="az")  # fmt: skip
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (2,)


# ------------------------------------------------------------------ reader.mongodb


class _FakeCursor(list):
    pass


class _FakeClient:
    instances: list = []
    docs: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.find_args = None
        _FakeClient.instances.append(self)

    def __getitem__(self, db):
        client = self

        class _Db:
            def __getitem__(self, coll):
                class _Coll:
                    def find(self, flt, **kw):
                        client.find_args = (db, coll, flt, kw)
                        return iter([RawBSONDocument(bson.encode(d)) for d in _FakeClient.docs])

                return _Coll()

        return _Db()

    def close(self):
        self.closed = True


@pytest.fixture()
def mongo(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.docs = []
    monkeypatch.setattr(dbio2, "MongoClient", _FakeClient)
    return _FakeClient


def test_mongodb_lane_contract_and_registry():
    assert {c.op for c in dbio2.CONTRACTS} == {"reader.mongodb"}
    assert READERS["reader.mongodb"] is dbio2.read_mongodb
    assert "reader.mongodb" in ops_catalog()
    assert "pymongo (Apache-2.0)" in OPERATIONS["reader.mongodb"].engine_license


def test_mongodb_reads_flattens_and_types(mongo, conn, session, tenant, user):
    oid = bson.ObjectId()
    mongo.docs = [
        {"_id": oid, "name": "a", "addr": {"city": "Tulle", "zip": 19000}, "tags": ["x", "y"],
         "at": dt.datetime(2026, 1, 2, 3, 4, 5), "loc": {"type": "Point", "coordinates": [1, 2]},
         "mixed": 1},
        {"_id": bson.ObjectId(), "name": "b", "loc": {"type": "Nope"}, "mixed": "deux"},
    ]  # fmt: skip
    _secret(session, tenant, user, "m", {"kind": "mongodb_uri",
            "uri": "mongodb://u:pw@db.example:27018/shop?authSource=admin"})  # fmt: skip
    srid = _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m",
                 collection="clients", geometryField="loc", projection=["name", "addr"],
                 filter={"name": {"$in": ["a", "b"]}}, maxDocuments=5)  # fmt: skip
    assert srid == 4326
    client = mongo.instances[0]
    assert client.closed
    kw = client.kwargs
    assert kw["host"] == "db.example" and kw["port"] == 27018
    assert kw["directConnection"] is True and kw["tls"] is True
    assert kw["username"] == "u" and kw["authSource"] == "admin"
    db, coll, flt, find_kw = client.find_args
    assert (db, coll, flt) == ("shop", "clients", {"name": {"$in": ["a", "b"]}})
    assert find_kw["projection"] == {"name": 1, "addr": 1} and find_kw["limit"] == 6
    rows = conn.execute(
        'SELECT _id, name, "addr.city", "addr.zip", tags, "at", ST_AsText(geometry), mixed, _error '
        "FROM node_n ORDER BY name"
    ).fetchall()
    assert rows[0][0] == str(oid)
    assert rows[0][1:6] == ("a", "Tulle", 19000, '["x", "y"]', dt.datetime(2026, 1, 2, 3, 4, 5))
    assert rows[0][6] == "POINT (1 2)" and rows[0][7] == "1" and rows[0][8] is None
    assert rows[1][6] is None and "not valid GeoJSON" in rows[1][8]  # erreur par ligne


def test_mongodb_uri_security(mongo, monkeypatch, conn, session, tenant, user):
    cases = {
        "nontls": ("mongodb://db.example/d?tls=false", "TLS with certificate"),
        "insecure": ("mongodb://db.example/d?tlsInsecure=true", "TLS with certificate"),
        "badcert": ("mongodb://db.example/d?tlsAllowInvalidCertificates=true", "TLS with"),
        "aws": ("mongodb://u:p@db.example/d?authMechanism=MONGODB-AWS", "authMechanism"),
        "garbage": ("mongodb://u:SECRETPW@db.example/d?proxyHost=x", "invalid MongoDB URI"),
    }
    for name, (uri, msg) in cases.items():
        _secret(session, tenant, user, name, {"kind": "mongodb_uri", "uri": uri})
        with pytest.raises(PipelineRuntimeError, match=msg) as exc:
            _read(dbio2.read_mongodb, conn, session, tenant, user, secretName=name,
                  collection="c")  # fmt: skip
        assert "SECRETPW" not in str(exc.value)
    assert mongo.instances == []  # aucune connexion tentée
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    _secret(session, tenant, user, "local", {"kind": "mongodb_uri",
            "uri": "mongodb://u:p@127.0.0.1:27017/d"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="local",
              collection="c")  # fmt: skip
    assert mongo.instances == []
    _secret(session, tenant, user, "pg", {"kind": "postgres_dsn", "dsn": "postgresql://h/d"})
    with pytest.raises(PipelineRuntimeError, match="expected mongodb_uri"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="pg", collection="c")


@pytest.mark.parametrize("params", [
    {"collection": "system.users"},
    {"collection": "$cmd"},
    {"collection": "c", "filter": {"$where": "sleep(1)"}},
    {"collection": "c", "filter": {"a": {"$elemMatch": {"$function": {}}}}},
    {"collection": "c", "projection": ["$x"]},
    {"collection": "c", "database": "a/b"},
])  # fmt: skip
def test_mongodb_params_rejected(params):
    with pytest.raises(ValidationError):
        dbio2.ReaderMongoDbParams(secretName="m", **params)


def test_mongodb_caps_and_degenerate(mongo, monkeypatch, conn, session, tenant, user):
    _secret(session, tenant, user, "m", {"kind": "mongodb_uri", "uri": "mongodb://db.example/d"})
    # maxDocuments = limite de l'auteur : tronque sans erreur
    mongo.docs = [{"i": i} for i in range(5)]
    _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c",
          maxDocuments=3)  # fmt: skip
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (3,)
    conn.execute("DROP TABLE node_n")
    # plafond plateforme : erreur explicite, jamais une troncature silencieuse
    monkeypatch.setattr(dbio2, "_max_rows", lambda: 2)
    with pytest.raises(PipelineRuntimeError, match="plafond de 2 lignes"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")
    monkeypatch.setattr(dbio2, "MAX_BYTES", 10)
    with pytest.raises(PipelineRuntimeError, match="larger than 10 bytes"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c",
              maxDocuments=1)  # fmt: skip
    monkeypatch.setattr(dbio2, "MAX_BYTES", 10**8)
    # collection vide : vue créée, colonne _error seule
    mongo.docs = []
    _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (0,)
    conn.execute("DROP TABLE node_n")
    # champ « geometry » sans geometryField : collision explicite
    mongo.docs = [{"geometry": 1}]
    with pytest.raises(PipelineRuntimeError, match="column collision"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")
    # collision après aplatissement : erreur sur la ligne seulement
    mongo.docs = [{"a": {"b": 1}, "a.b": 2}, {"a": {"b": 3}}]
    _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")
    rows = conn.execute('SELECT "a.b", _error FROM node_n ORDER BY "a.b" NULLS FIRST').fetchall()
    assert rows[0][0] is None and "twice" in rows[0][1] and rows[1] == (3, None)


def test_mongodb_no_database(mongo, conn, session, tenant, user):
    _secret(session, tenant, user, "m", {"kind": "mongodb_uri", "uri": "mongodb://db.example"})
    with pytest.raises(PipelineRuntimeError, match="no database"):
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")


def test_refresh_uses_the_vault_value_not_a_stale_copy(httpserver, session, tenant, user):
    """Un autre worker a déjà fait tourner le refresh_token : la valeur relue sous verrou
    prime sur la copie déchiffrée en début de run (sinon refresh_token révoqué consommé)."""
    httpserver.expect_request("/oauth/token").respond_with_json({"access_token": "A"})
    payload = {
        "kind": "oauth2_client", "grantType": "refresh_token",
        "tokenUrl": httpserver.url_for("/oauth/token"), "clientId": "CID",
        "clientSecret": "S", "refreshToken": "FRESH", "baseUrl": httpserver.url_for("/"),
    }  # fmt: skip
    _secret(session, tenant, user, "s", payload)
    stale = SECRET_PAYLOAD_ADAPTER.validate_python({**payload, "refreshToken": "STALE"})
    assert cf._refresh_and_rotate("op", session, tenant.id, user, "s", stale)[0] == "A"
    assert dict(httpserver.log[0][0].form)["refresh_token"] == "FRESH"


# ------------------------------------------------------------------ revue voie R (correctifs)


def _refresh_secret(session, tenant, user, httpserver, name="s", refresh="R1"):
    _secret(session, tenant, user, name, {
        "kind": "oauth2_client", "grantType": "refresh_token",
        "tokenUrl": httpserver.url_for("/oauth/token"), "clientId": "CID",
        "clientSecret": "CSECRET", "refreshToken": refresh, "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip


def _stored_refresh(session, tenant, name="s"):
    session.expire_all()
    row = secrets_repo.get_secret_by_name(session, tenant_id=tenant.id, name=name)
    return decrypt(row.ciphertext, row.nonce)["refreshToken"]


def test_rotated_refresh_token_saved_even_if_answer_is_otherwise_invalid(
    httpserver, monkeypatch, conn, session, tenant, user
):
    """Le fournisseur a déjà révoqué R1 : R2 doit être persisté même si la suite de la
    réponse est refusée (token_type), sinon le compte est perdu."""
    httpserver.expect_request("/oauth/token").respond_with_json(
        {"access_token": "A", "token_type": "mac", "refresh_token": "R2"}
    )
    _dropbox(httpserver, monkeypatch)
    _refresh_secret(session, tenant, user, httpserver)
    with pytest.raises(PipelineRuntimeError, match="not 'bearer'"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="s")  # fmt: skip
    assert _stored_refresh(session, tenant) == "R2"


def test_rotated_refresh_token_survives_a_failed_commit(
    httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token").respond_with_json(
        {"access_token": "A", "refresh_token": "R2"}
    )
    _dropbox(httpserver, monkeypatch, expect_token="A")
    _refresh_secret(session, tenant, user, httpserver)
    real_commit = cf.Session.commit
    calls = {"n": 0}

    def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connexion perdue")
        return real_commit(self)

    monkeypatch.setattr(cf.Session, "commit", flaky_commit)
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox", file="/f.csv",
          secretName="s")  # fmt: skip
    monkeypatch.setattr(cf.Session, "commit", real_commit)
    assert calls["n"] >= 2 and _stored_refresh(session, tenant) == "R2"


def test_lost_refresh_token_asks_for_reauthorization(
    httpserver, monkeypatch, session, tenant, user
):
    httpserver.expect_request("/oauth/token").respond_with_json(
        {"access_token": "A", "refresh_token": "R2"}
    )
    _refresh_secret(session, tenant, user, httpserver)

    def broken(self):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(cf.Session, "commit", broken)
    stale = SECRET_PAYLOAD_ADAPTER.validate_python(
        decrypt(*(lambda r: (r.ciphertext, r.nonce))(
            secrets_repo.get_secret_by_name(session, tenant_id=tenant.id, name="s")))
    )  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="re-authorize the secret 's'") as exc:
        cf._oauth2_access_token("op", session, tenant.id, user, "s", stale)
    assert "R2" not in str(exc.value)


def test_preview_never_renews_a_refresh_token(httpserver, monkeypatch, conn, session, tenant, user):
    from app.pipelines.ops.operation_contract import IN_PREVIEW

    httpserver.expect_request("/oauth/token").respond_with_json({"access_token": "ACCESS"})
    _dropbox(httpserver, monkeypatch)
    _refresh_secret(session, tenant, user, httpserver)
    _secret(session, tenant, user, "cc", {
        "kind": "oauth2_client", "tokenUrl": httpserver.url_for("/oauth/token"),
        "clientId": "C2", "clientSecret": "S2", "baseUrl": httpserver.url_for("/"),
    })  # fmt: skip
    tok = IN_PREVIEW.set(True)
    try:
        with pytest.raises(PipelineRuntimeError, match="preview cannot renew"):
            _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
                  file="/f.csv", secretName="s")  # fmt: skip
        assert httpserver.log == []
        # client_credentials : aucune écriture dans le coffre, l'aperçu est permis
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox",
              file="/f.csv", secretName="cc")  # fmt: skip
    finally:
        IN_PREVIEW.reset(tok)


def test_cache_does_not_survive_a_replaced_refresh_token(
    httpserver, monkeypatch, conn, session, tenant, user
):
    httpserver.expect_request("/oauth/token").respond_with_json({"access_token": "ACCESS"})
    _dropbox(httpserver, monkeypatch)
    _refresh_secret(session, tenant, user, httpserver)
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox", file="/f.csv",
          secretName="s")  # fmt: skip
    row = secrets_repo.get_secret_by_name(session, tenant_id=tenant.id, name="s")
    payload = decrypt(row.ciphertext, row.nonce)
    row.ciphertext, row.nonce = encrypt({**payload, "refreshToken": "OTHER-ACCOUNT"})
    session.commit()
    conn.execute("DROP TABLE node_n")
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="dropbox", file="/f.csv",
          secretName="s")  # fmt: skip
    token_calls = [r for r, _ in httpserver.log if r.path == "/oauth/token"]
    assert [dict(r.form)["refresh_token"] for r in token_calls] == ["R1", "OTHER-ACCOUNT"]


def test_token_url_error_message():
    with pytest.raises(ValidationError, match="tokenUrl must look like"):
        SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "oauth2_client",
            "tokenUrl": "ftp://x", "clientId": "c", "clientSecret": "s"})  # fmt: skip


def test_mongodb_review_minors(mongo, monkeypatch, conn, session, tenant, user):
    deep: dict = {"a": 1}
    for _ in range(3000):
        deep = {"$and": [deep]}
    for bad in ({"geometryField": "loc.geo"}, {"filter": deep}):
        with pytest.raises(ValidationError):
            dbio2.ReaderMongoDbParams(secretName="m", collection="c", **bad)
    _secret(session, tenant, user, "m", {"kind": "mongodb_uri", "uri": "mongodb://db.example/d"})
    # champ « Geometry » (casse différente) avec geometryField : erreur sur la ligne
    mongo.docs = [{"Geometry": 1, "loc": {"type": "Point", "coordinates": [0, 0]}}]
    _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c",
          geometryField="loc")  # fmt: skip
    assert "reserved column" in conn.execute("SELECT _error FROM node_n").fetchone()[0]
    # construction du client dans le try : message assaini
    from pymongo.errors import ConfigurationError

    def boom(**kw):
        raise ConfigurationError("mongodb://u:SECRETPW@db.example détail brut")

    monkeypatch.setattr(dbio2, "MongoClient", boom)
    with pytest.raises(PipelineRuntimeError, match=r"MongoDB error \(ConfigurationError\)") as e:
        _read(dbio2.read_mongodb, conn, session, tenant, user, secretName="m", collection="c")
    assert "SECRETPW" not in str(e.value)


# ------------------------------------------------------------------ postgis : verrou réel


@pytest.mark.postgis
def test_concurrent_refreshes_call_the_provider_once(httpserver, pg_engine, monkeypatch):
    """FOR UPDATE réel : deux runs simultanés sur le même secret refresh_token → un seul
    appel au fournisseur (le second trouve le jeton en cache sous le verrou), R2 conservé."""
    import threading
    import time as _time
    import uuid

    from werkzeug import Response

    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    from app.db import Base, core_table_names

    core_table_names()  # enregistre les modèles
    Base.metadata.create_all(pg_engine)
    factory = make_session_factory(pg_engine)
    calls: list[str] = []

    def handler(request):
        calls.append(request.form.get("refresh_token"))
        _time.sleep(0.5)  # les deux runs se chevauchent
        if request.form.get("refresh_token") != "R1":
            return Response('{"error": "invalid_grant"}', status=400)
        return Response(
            json.dumps({"access_token": "A1", "refresh_token": "R2", "expires_in": 3600}),
            content_type="application/json",
        )

    httpserver.expect_request("/oauth/token").respond_with_handler(handler)
    name = f"oauth-{uuid.uuid4().hex[:8]}"
    payload = {
        "kind": "oauth2_client", "grantType": "refresh_token",
        "tokenUrl": httpserver.url_for("/oauth/token"), "clientId": "CID",
        "clientSecret": "S", "refreshToken": "R1", "baseUrl": httpserver.url_for("/"),
    }  # fmt: skip
    with factory() as s:
        tenant = get_or_create_default_tenant(s)
        u = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="voie-r", username="voie-r",
                               email=None, first_name="", last_name="")  # fmt: skip
        tenant_id, user_id = tenant.id, u.id
        ct, nonce = encrypt(payload)
        secrets_repo.create_secret(s, tenant_id=tenant_id, created_by=user_id, name=name,
                                   kind="oauth2_client", ciphertext=ct, nonce=nonce)  # fmt: skip
        s.commit()
    stale = SECRET_PAYLOAD_ADAPTER.validate_python(payload)
    results: list = []

    class _U:
        id = user_id

    def run():
        with factory() as s:
            try:
                results.append(cf._oauth2_access_token("op", s, tenant_id, _U(), name, stale))
            except Exception as exc:  # pragma: no cover - affiché par l'assertion
                results.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert results == ["A1", "A1"], results
        assert calls == ["R1"]
        with factory() as s:
            row = secrets_repo.get_secret_by_name(s, tenant_id=tenant_id, name=name)
            assert decrypt(row.ciphertext, row.nonce)["refreshToken"] == "R2"
    finally:
        with factory() as s:
            row = secrets_repo.get_secret_by_name(s, tenant_id=tenant_id, name=name)
            if row is not None:
                s.delete(row)
                s.commit()
