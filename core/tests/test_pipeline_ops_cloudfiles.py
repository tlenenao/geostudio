# SPDX-License-Identifier: Apache-2.0
"""Voie D FME : stockage fichier & SaaS (reader.cloudfile, reader.arcgisonline, reader.ckan,
reader.ftp / writer.ftp)."""

import ftplib
import io
import json

import duckdb
import pytest
from pydantic import ValidationError

from app.configs.schemas import PipelineNode
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import egress as pipelines_egress
from app.pipelines.errors import PipelineCancelledError, PipelineRuntimeError
from app.pipelines.ops import cloudfiles as cf
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
_REAL_EGRESS_GUARD = pipelines_egress.assert_egress_allowed

LANE_OPS = {
    "reader.cloudfile",
    "reader.arcgisonline",
    "reader.ckan",
    "reader.ftp",
    "writer.ftp",
}
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
    """Serveur HTTP local : garde d'egress neutralisée, TLS non exigé (sauf test dédié)."""
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    monkeypatch.setattr(cf, "_REQUIRE_TLS_FOR_SECRETS", False)


def _secret(session, tenant, user, name, payload):
    ct, nonce = encrypt(payload)
    secrets_repo.create_secret(
        session, tenant_id=tenant.id, created_by=user.id, name=name,
        kind=payload["kind"], ciphertext=ct, nonce=nonce,
    )  # fmt: skip


def _read(fn, conn, session, tenant, user, **params):
    return fn(
        conn, session=session, tenant_id=tenant.id, node_id="n", view_name="node_n",
        user=user, base_uri="", params=params,
    )  # fmt: skip


def test_lane_contracts_and_catalog():
    assert {c.op for c in cf.CONTRACTS} == LANE_OPS
    assert set(cf.READERS) == {o for o in LANE_OPS if o.startswith("reader.")}
    assert set(cf.WRITERS) == {"writer.ftp"}
    assert LANE_OPS <= set(ops_catalog())
    assert all(OPERATIONS[o].engine_license for o in LANE_OPS)


# ------------------------------------------------------------------ reader.cloudfile

PROVIDER_CASES = [
    # provider, params, méthode, chemin attendu, en-tête exigé
    ("dropbox", {"file": "/dir/f.csv"}, "POST", "/2/files/download", "Dropbox-API-Arg"),
    ("box", {"file": "12345"}, "GET", "/2.0/files/12345/content", None),
    ("googledrive", {"file": "abcDEF_1"}, "GET", "/drive/v3/files/abcDEF_1", None),
    ("onedrive", {"file": "ITEM1"}, "GET", "/v1.0/me/drive/items/ITEM1/content", None),
    ("onedrive", {"file": "ITEM1", "driveId": "b!x"}, "GET",
     "/v1.0/drives/b!x/items/ITEM1/content", None),
    ("sharepoint", {"file": "ITEM1", "siteId": "host,g1,g2"}, "GET",
     "/v1.0/sites/host,g1,g2/drive/items/ITEM1/content", None),
]  # fmt: skip


@pytest.mark.parametrize("provider, extra, method, path, header", PROVIDER_CASES)
def test_cloudfile_providers(
    provider, extra, method, path, header, httpserver, monkeypatch, conn, session, tenant, user
):
    monkeypatch.setitem(cf._API, provider, httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "T",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    httpserver.expect_request(
        path, method=method, headers={"Authorization": "Bearer T"}
    ).respond_with_data(CSV)
    srid = _read(cf.read_cloudfile, conn, session, tenant, user, provider=provider,
                 secretName="s", **extra)  # fmt: skip
    assert srid == 4326
    assert conn.execute("SELECT id, nom FROM node_n ORDER BY id").fetchall() == [(1, "a"), (2, "b")]
    if header:
        assert header in httpserver.log[0][0].headers


def test_cloudfile_azurefiles_and_hdfs(httpserver, monkeypatch, conn, session, tenant, user):
    # Azure Files : hôte dérivé du compte, remplacé ici par le serveur local
    _secret(
        session,
        tenant,
        user,
        "s",
        {
            "kind": "api_key",
            "location": "query",
            "key": "delegation",
            "value": "D",
            "baseUrl": httpserver.url_for("/"),
        },
    )
    httpserver.expect_request(
        "/webhdfs/v1/data/f.csv", query_string="op=OPEN&delegation=D"
    ).respond_with_data(CSV)
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="hdfs", secretName="s",
          file="data/f.csv", baseUrl=httpserver.url_for(""))  # fmt: skip
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (2,)
    req = cf._cloudfile_request(
        cf.ReaderCloudFileParams(
            provider="azurefiles", secretName="s", file="d/f.csv", account="acct", share="sh"
        )
    )
    assert req["url"] == "https://acct.file.core.windows.net/sh/d/f.csv"
    assert req["headers"]["x-ms-file-request-intent"] == "backup"


@pytest.mark.parametrize(
    "extra",
    [
        {"provider": "dropbox", "file": "../etc/passwd"},
        {"provider": "dropbox", "file": "a\nb"},
        {"provider": "box", "file": "1/../2"},
        {"provider": "sharepoint", "file": "x"},  # siteId manquant
        {"provider": "azurefiles", "file": "x", "account": "ev.il", "share": "s"},
        {"provider": "hdfs", "file": "x", "baseUrl": "ftp://h"},
    ],
)
def test_cloudfile_rejects_bad_params(extra):
    with pytest.raises(ValidationError):
        cf.ReaderCloudFileParams(secretName="s", **extra)


def test_cloudfile_secret_scope_kind_missing(httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    kw = dict(provider="box", file="1")
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": "https://evil.example/"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="baseUrl must cover"):
        _read(cf.read_cloudfile, conn, session, tenant, user, secretName="s", **kw)
    assert httpserver.log == []  # rien n'est parti
    _secret(session, tenant, user, "pg", {"kind": "postgres_dsn", "dsn": "postgresql://u:p@h/d"})
    with pytest.raises(PipelineRuntimeError, match="expected one of"):
        _read(cf.read_cloudfile, conn, session, tenant, user, secretName="pg", **kw)
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _read(cf.read_cloudfile, conn, session, tenant, user, secretName="absent", **kw)


def test_secret_not_sent_over_plain_http(httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setattr(cf, "_REQUIRE_TLS_FOR_SECRETS", True)
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="https"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s")  # fmt: skip
    assert httpserver.log == []


def test_redirect_out_of_scope_never_carries_the_secret(
    httpserver, monkeypatch, conn, session, tenant, user
):
    """Box/Drive/Graph redirigent vers une URL pré-signée : un en-tête `api_key` custom ne doit
    pas suivre le saut (requests ne nettoie que `Authorization`)."""
    from pytest_httpserver import HTTPServer

    with HTTPServer() as other:  # 2e origine (autre port = autre portée)
        other.expect_request("/blob").respond_with_data(CSV)
        monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
        _secret(session, tenant, user, "s", {"kind": "api_key", "location": "header",
                "key": "X-Secret", "value": "SHH", "baseUrl": httpserver.url_for("/")})  # fmt: skip
        httpserver.expect_request("/2.0/files/1/content").respond_with_data(
            "", status=302, headers={"Location": other.url_for("/blob")}
        )
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s")  # fmt: skip
        assert "X-Secret" in httpserver.log[0][0].headers
        assert "X-Secret" not in other.log[0][0].headers
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (2,)


def test_redirect_loop_and_http_error(httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    httpserver.expect_request("/2.0/files/1/content").respond_with_data(
        "", status=302, headers={"Location": httpserver.url_for("/2.0/files/1/content")}
    )
    kw = dict(provider="box", secretName="s")
    with pytest.raises(PipelineRuntimeError, match="too many redirects"):
        _read(cf.read_cloudfile, conn, session, tenant, user, file="1", **kw)
    httpserver.clear()
    httpserver.expect_request("/2.0/files/2/content").respond_with_data("no", status=403)
    with pytest.raises(PipelineRuntimeError, match="HTTP 403"):
        _read(cf.read_cloudfile, conn, session, tenant, user, file="2", **kw)


def test_egress_guard_blocks_internal(monkeypatch, conn, session, tenant, user):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": "https://127.0.0.1/"})  # fmt: skip
    monkeypatch.setitem(cf._API, "box", "https://127.0.0.1")
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s")  # fmt: skip


@pytest.mark.parametrize("fmt, body, msg", [
    ("csv", b"", "not valid csv"),
    ("geojson", b"{}", "not valid geojson"),
    ("jsonl", b"not json", "not valid jsonl"),
    ("parquet", b"nope", "not valid parquet"),
    ("csv", b"id,geometry\n1,x\n", "column collision"),
])  # fmt: skip
def test_degenerate_files(fmt, body, msg, httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    httpserver.expect_request("/2.0/files/1/content").respond_with_data(body)
    with pytest.raises(PipelineRuntimeError, match=msg):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s", format=fmt)  # fmt: skip


def test_row_and_byte_caps(httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    httpserver.expect_request("/2.0/files/1/content").respond_with_data(CSV)
    kw = dict(provider="box", file="1", secretName="s")
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS", "1")
    with pytest.raises(PipelineRuntimeError, match="plafond"):
        _read(cf.read_cloudfile, conn, session, tenant, user, **kw)
    monkeypatch.delenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS")
    monkeypatch.setattr(cf, "MAX_BYTES", 5)
    with pytest.raises(PipelineRuntimeError, match="larger than"):
        _read(cf.read_cloudfile, conn, session, tenant, user, **kw)


def test_geojson_and_parquet(httpserver, monkeypatch, conn, session, tenant, user):
    import pandas as pd

    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    gj = {
        "features": [
            {
                "properties": {"n": 1, "o": {"k": 1}},
                "geometry": {"type": "Point", "coordinates": [2, 48]},
            },
            {"properties": {"n": 2}, "geometry": None},
        ]
    }
    httpserver.expect_request("/2.0/files/1/content").respond_with_json(gj)
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
          secretName="s", format="geojson")  # fmt: skip
    assert conn.execute("SELECT n, ST_AsText(geometry) FROM node_n ORDER BY n").fetchall() == [
        (1, "POINT (2 48)"), (2, None)]  # fmt: skip
    conn.execute("DROP TABLE node_n")
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(buf)
    httpserver.clear()
    httpserver.expect_request("/2.0/files/1/content").respond_with_data(buf.getvalue())
    _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
          secretName="s", format="parquet")  # fmt: skip
    assert conn.execute("SELECT sum(a) FROM node_n").fetchone() == (6,)


# ------------------------------------------------------------------ reader.arcgisonline


def test_arcgis_paginates_with_token(httpserver, monkeypatch, conn, session, tenant, user):
    monkeypatch.setattr(cf, "_ARCGIS_PAGE", 2)
    _secret(session, tenant, user, "s", {"kind": "api_key", "location": "query", "key": "token",
            "value": "TK", "baseUrl": httpserver.url_for("/")})  # fmt: skip

    def feat(i):
        return {"properties": {"oid": i}, "geometry": {"type": "Point", "coordinates": [i, 0]}}

    def handler(request):
        from werkzeug.wrappers import Response

        assert request.args["token"] == "TK" and request.args["f"] == "geojson"
        off = int(request.args["resultOffset"])
        data = [feat(i) for i in range(5)][off : off + 2]
        return Response(json.dumps({"features": data, "exceededTransferLimit": off + 2 < 5}))

    httpserver.expect_request("/arcgis/rest/services/S/FeatureServer/0/query").respond_with_handler(
        handler
    )
    _read(cf.read_arcgisonline, conn, session, tenant, user, secretName="s",
          layerUrl=httpserver.url_for("/arcgis/rest/services/S/FeatureServer/0"))  # fmt: skip
    assert conn.execute("SELECT count(*), max(oid) FROM node_n").fetchone() == (5, 4)


def test_arcgis_max_features_and_service_error(httpserver, conn, session, tenant, user):
    url = httpserver.url_for("/L/FeatureServer/0")
    httpserver.expect_request("/L/FeatureServer/0/query").respond_with_json(
        {"features": [{"properties": {"a": i}, "geometry": None} for i in range(10)],
         "exceededTransferLimit": True}
    )  # fmt: skip
    # AUD-082 : la source signale encore des données -> refus explicite, plus de coupe muette
    with pytest.raises(PipelineRuntimeError, match="tronqué"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url, maxFeatures=3)
    httpserver.clear()
    httpserver.expect_request("/L/FeatureServer/0/query").respond_with_json(
        {"error": {"code": 498, "message": "Invalid token"}}
    )
    with pytest.raises(PipelineRuntimeError, match="service error 498"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url)
    with pytest.raises(ValidationError):
        cf.ReaderArcgisOnlineParams(layerUrl="https://x.example/L?token=leak")


# ------------------------------------------------------------------ reader.ckan


def test_ckan_resolves_dataset_to_resource(httpserver, conn, session, tenant, user):
    base = httpserver.url_for("")
    req = httpserver.expect_request("/api/3/action/package_show", query_string="id=ds1")
    req.respond_with_json(
        {"result": {"resources": [
            {"id": "r0", "format": "PDF", "url": base + "/doc.pdf"},
            {"id": "r1", "format": "csv", "url": base + "/files/data.csv"},
        ]}}
    )  # fmt: skip
    httpserver.expect_request("/files/data.csv").respond_with_data(CSV)
    _read(cf.read_ckan, conn, session, tenant, user, baseUrl=base, datasetId="ds1")
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (2,)
    with pytest.raises(PipelineRuntimeError, match="no readable resource"):
        _read(cf.read_ckan, conn, session, tenant, user, baseUrl=base, datasetId="ds1",
              resourceId="r0")  # fmt: skip


def test_ckan_secret_not_sent_to_foreign_resource_host(httpserver, conn, session, tenant, user):
    from pytest_httpserver import HTTPServer

    with HTTPServer() as files:
        files.expect_request("/d.csv").respond_with_data(CSV)
        _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "PRIV",
                "baseUrl": httpserver.url_for("/")})  # fmt: skip
        httpserver.expect_request("/api/3/action/package_show").respond_with_json(
            {"result": {"resources": [{"format": "CSV", "url": files.url_for("/d.csv")}]}}
        )
        _read(cf.read_ckan, conn, session, tenant, user, baseUrl=httpserver.url_for(""),
              datasetId="x", secretName="s")  # fmt: skip
        assert "Authorization" in httpserver.log[0][0].headers
        assert "Authorization" not in files.log[0][0].headers


def test_ckan_bad_answer(httpserver, conn, session, tenant, user):
    httpserver.expect_request("/api/3/action/package_show").respond_with_json({"success": False})
    with pytest.raises(PipelineRuntimeError, match="unexpected package_show"):
        _read(cf.read_ckan, conn, session, tenant, user, baseUrl=httpserver.url_for(""),
              datasetId="x")  # fmt: skip


# ------------------------------------------------------------------ FTPS


class FakeFtp:
    instances: list = []
    store: dict = {}
    fail_login = False

    def __init__(self, context=None, timeout=None):
        self.context, self.timeout, self.calls = context, timeout, []
        FakeFtp.instances.append(self)

    def connect(self, host, port):
        self.calls.append(("connect", host, port))

    def login(self, user, pw):
        if FakeFtp.fail_login:
            raise ftplib.error_perm("530 no")
        self.calls.append(("login", user, pw))

    def prot_p(self):
        self.calls.append(("prot_p",))

    def retrbinary(self, cmd, cb):
        self.calls.append(("retr", cmd))
        data = FakeFtp.store[cmd.removeprefix("RETR ")]
        for i in range(0, len(data), 4):
            cb(data[i : i + 4])

    def storbinary(self, cmd, fp):
        self.calls.append(("stor", cmd))
        FakeFtp.store[cmd.removeprefix("STOR ")] = fp.read()

    def rename(self, a, b):
        self.calls.append(("rename", a, b))
        FakeFtp.store[b] = FakeFtp.store.pop(a)

    def delete(self, a):
        self.calls.append(("delete", a))
        FakeFtp.store.pop(a, None)

    def close(self):
        self.calls.append(("close",))


@pytest.fixture()
def ftp(monkeypatch, session, tenant, user):
    FakeFtp.instances, FakeFtp.store, FakeFtp.fail_login = [], {"/in.csv": CSV}, False
    monkeypatch.setattr(cf.ftplib, "FTP_TLS", FakeFtp)
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: "203.0.113.9")
    _secret(session, tenant, user, "f", {"kind": "basic_auth", "username": "u", "password": "p",
            "baseUrl": "https://ftp.example.org"})  # fmt: skip
    return FakeFtp


def test_ftp_reader_uses_tls_pinned_ip_and_verified_cert(ftp, conn, session, tenant, user):
    _read(cf.read_ftp, conn, session, tenant, user, host="ftp.example.org", path="/in.csv",
          secretName="f")  # fmt: skip
    inst = ftp.instances[0]
    assert inst.context.verify_mode.name == "CERT_REQUIRED" and inst.context.check_hostname
    assert ("connect", "203.0.113.9", 21) in inst.calls  # IP validée, pas le nom
    assert inst.calls.index(("prot_p",)) > inst.calls.index(("login", "u", "p"))
    assert inst.calls[-1] == ("close",)
    assert conn.execute("SELECT count(*) FROM node_n").fetchone() == (2,)


def test_ftp_secret_host_binding_and_injection(ftp, conn, session, tenant, user):
    with pytest.raises(PipelineRuntimeError, match="host/port must be"):
        _read(cf.read_ftp, conn, session, tenant, user, host="evil.example.org", path="/in.csv",
              secretName="f")  # fmt: skip
    assert ftp.instances == []  # aucune connexion, donc aucun identifiant envoyé
    for bad in ("/in.csv\r\nDELE x", "../x", "-l"):
        with pytest.raises(ValidationError):
            cf.ReaderFtpParams(host="ftp.example.org", path=bad, secretName="f")


def test_ftp_login_failure_and_caps(ftp, monkeypatch, conn, session, tenant, user):
    ftp.fail_login = True
    with pytest.raises(PipelineRuntimeError, match="FTPS connection failed"):
        _read(cf.read_ftp, conn, session, tenant, user, host="ftp.example.org", path="/in.csv",
              secretName="f")  # fmt: skip
    ftp.fail_login = False
    monkeypatch.setattr(cf, "MAX_BYTES", 6)
    with pytest.raises(PipelineRuntimeError, match="larger than"):
        _read(cf.read_ftp, conn, session, tenant, user, host="ftp.example.org", path="/in.csv",
              secretName="f")  # fmt: skip


def test_ftp_egress_guard(ftp, monkeypatch, conn, session, tenant, user):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    _secret(session, tenant, user, "loc", {"kind": "basic_auth", "username": "u", "password": "p",
            "baseUrl": "https://127.0.0.1"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _read(cf.read_ftp, conn, session, tenant, user, host="127.0.0.1", path="/in.csv",
              secretName="loc")  # fmt: skip
    assert ftp.instances == []


def _write(conn, session, tenant, user, sql, **kw):
    conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS {sql}")
    node = PipelineNode(id="w", kind="writer", op="writer.ftp", params={
        "host": "ftp.example.org", "path": "/out.csv", "secretName": "f", **kw})  # fmt: skip
    return cf.WRITERS["writer.ftp"](
        session, conn, node=node, view_by_node={"w": "inp"}, tenant_id=tenant.id, user=user,
        should_cancel=kw.pop("should_cancel", None),
    )  # fmt: skip


def test_ftp_writer_roundtrip_idempotent_and_audited(ftp, conn, session, tenant, user):
    from app.audit.models import AuditLog

    sql = "SELECT * FROM (VALUES (1,'a'),(2,'b')) t(id,nom)"
    stat = _write(conn, session, tenant, user, sql)
    first = ftp.store["/out.csv"]
    assert stat.rowCount == 2 and first.decode().splitlines() == ["id,nom", "1,a", "2,b"]
    _write(conn, session, tenant, user, sql)  # rejeu : même contenu, pas d'accumulation
    assert ftp.store["/out.csv"] == first
    assert session.query(AuditLog).filter_by(action="pipeline.external_write").count() == 2
    _write(conn, session, tenant, user, sql, format="jsonl")
    assert json.loads(ftp.store["/out.csv"].splitlines()[0]) == {"id": 1, "nom": "a"}


def test_ftp_writer_guards(ftp, monkeypatch, conn, session, tenant, user):
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _write(conn, session, tenant, user, "SELECT ST_Point(1,2) AS g")
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS", "1")
    with pytest.raises(PipelineRuntimeError, match="plafond"):
        _write(conn, session, tenant, user, "SELECT * FROM range(3) t(i)")
    monkeypatch.delenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS")
    conn.execute("CREATE OR REPLACE TEMP TABLE inp AS SELECT 1 AS i")
    node = PipelineNode(id="w", kind="writer", op="writer.ftp", params={
        "host": "ftp.example.org", "path": "/out.csv", "secretName": "f"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="cancelled"):
        cf.WRITERS["writer.ftp"](
            session,
            conn,
            node=node,
            view_by_node={"w": "inp"},
            tenant_id=tenant.id,
            user=user,
            should_cancel=lambda: True,
        )
    assert ftp.instances == [] and "/out.csv" not in ftp.store  # annulé avant toute connexion
    _write_empty = _write(conn, session, tenant, user, "SELECT 1 AS i WHERE false")
    assert _write_empty.rowCount == 0


def test_ftp_writer_is_atomic_via_part_file_and_cleans_up(
    ftp, monkeypatch, conn, session, tenant, user
):
    _write(conn, session, tenant, user, "SELECT 1 AS i")
    calls = ftp.instances[-1].calls
    assert ("stor", "STOR /out.csv.part") in calls and (
        "rename",
        "/out.csv.part",
        "/out.csv",
    ) in calls
    assert not any(c == ("stor", "STOR /out.csv") for c in calls)

    def boom(self, cmd, fp):
        self.calls.append(("stor", cmd))
        FakeFtp.store[cmd.removeprefix("STOR ")] = b"tron"
        raise OSError("coupure")

    old = ftp.store["/out.csv"]
    monkeypatch.setattr(FakeFtp, "storbinary", boom)
    with pytest.raises(PipelineRuntimeError, match="transfer failed"):
        _write(conn, session, tenant, user, "SELECT 2 AS i")
    assert ftp.store["/out.csv"] == old and "/out.csv.part" not in ftp.store


def test_ftp_writer_cancel_is_a_cancellation_not_a_failure(ftp, conn, session, tenant, user):
    """I1 : une annulation finit le run « cancelled » (PipelineCancelledError), jamais
    « failed » donc reprenable ; rien n'est transféré."""
    conn.execute("CREATE OR REPLACE TEMP TABLE inp AS SELECT 1 AS i")
    node = PipelineNode(id="w", kind="writer", op="writer.ftp", params={
        "host": "ftp.example.org", "path": "/cancel.csv", "secretName": "f"})  # fmt: skip
    with pytest.raises(PipelineCancelledError, match="cancelled"):
        cf.WRITERS["writer.ftp"](
            session, conn, node=node, view_by_node={"w": "inp"}, tenant_id=tenant.id,
            user=user, should_cancel=lambda: True,
        )  # fmt: skip
    assert "/cancel.csv" not in ftp.store


def test_ftp_secret_port_binding(ftp, conn, session, tenant, user):
    _secret(session, tenant, user, "f2", {"kind": "basic_auth", "username": "u", "password": "p",
            "baseUrl": "https://ftp.example.org:2121"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="host/port"):
        _read(cf.read_ftp, conn, session, tenant, user, host="ftp.example.org", path="/in.csv",
              secretName="f2")  # fmt: skip
    _read(cf.read_ftp, conn, session, tenant, user, host="ftp.example.org", port=2121,
          path="/in.csv", secretName="f2")  # fmt: skip


def test_parquet_decompression_bomb(httpserver, monkeypatch, conn, session, tenant, user):
    import pandas as pd

    monkeypatch.setitem(cf._API, "box", httpserver.url_for(""))
    _secret(session, tenant, user, "s", {"kind": "bearer_token", "token": "t",
            "baseUrl": httpserver.url_for("/")})  # fmt: skip
    buf = io.BytesIO()
    pd.DataFrame({"a": ["x" * 10_000] * 2_000}).to_parquet(buf, compression="zstd")
    assert len(buf.getvalue()) < 100_000  # minuscule, ~20 Mo décompressés
    httpserver.expect_request("/2.0/files/1/content").respond_with_data(buf.getvalue())
    monkeypatch.setattr(cf, "MAX_BYTES", 1_000_000)  # plafond décompressé = 4 Mo
    with pytest.raises(PipelineRuntimeError, match="decompresses beyond"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s", format="parquet")  # fmt: skip
    # métadonnées mensongères : le contrôle par row group réel rattrape
    import pyarrow.parquet as pq

    class Liar(pq.ParquetFile):
        @property
        def metadata(self):
            real = super().metadata
            rg = type("R", (), {"total_byte_size": 1})()
            return type("M", (), {"num_rows": real.num_rows, "num_row_groups": real.num_row_groups,
                                  "row_group": lambda self, i: rg})()  # fmt: skip

    monkeypatch.setattr(pq, "ParquetFile", Liar)
    with pytest.raises(PipelineRuntimeError, match="decompresses beyond"):
        _read(cf.read_cloudfile, conn, session, tenant, user, provider="box", file="1",
              secretName="s", format="parquet")  # fmt: skip


def test_arcgis_page_limit_byte_budget_and_malformed(
    httpserver, monkeypatch, conn, session, tenant, user
):
    url = httpserver.url_for("/L/FeatureServer/0")
    ep = "/L/FeatureServer/0/query"
    one = {"features": [{"properties": {"a": 1}, "geometry": None}], "exceededTransferLimit": True}
    httpserver.expect_request(ep).respond_with_json(one)  # ignore resultOffset, ne finit jamais
    monkeypatch.setattr(cf, "_ARCGIS_PAGE", 1)
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_PAGES", "3")
    with pytest.raises(PipelineRuntimeError, match="page limit"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url)
    monkeypatch.delenv("CORE_PIPELINES_CONNECTOR_MAX_PAGES")
    monkeypatch.setattr(cf, "MAX_BYTES", 150)  # budget cumulé : ~2 pages
    with pytest.raises(PipelineRuntimeError, match="larger than"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url)
    monkeypatch.setattr(cf, "MAX_BYTES", 100 * 1024 * 1024)
    monkeypatch.setattr(cf, "_ARCGIS_PAGE", 1000)
    httpserver.clear()
    httpserver.expect_request(ep).respond_with_json({"features": ["pas un dict"]})
    with pytest.raises(PipelineRuntimeError, match="malformed feature"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url)
    httpserver.clear()
    httpserver.expect_request(ep).respond_with_json({"features": [{"properties": 3}]})
    with pytest.raises(PipelineRuntimeError, match="malformed feature"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, layerUrl=url)


def test_arcgis_refuses_a_truncated_answer(httpserver, monkeypatch, conn, session, tenant, user):
    """AUD-082 : la source signale encore des données au-delà de maxFeatures -> refus."""
    _secret(session, tenant, user, "s", {"kind": "api_key", "location": "query", "key": "token",
            "value": "TK", "baseUrl": httpserver.url_for("/")})  # fmt: skip
    feats = [
        {"properties": {"oid": i}, "geometry": {"type": "Point", "coordinates": [i, 0]}}
        for i in range(2)
    ]
    httpserver.expect_request("/arcgis/rest/services/S/FeatureServer/0/query").respond_with_json(
        {"features": feats, "exceededTransferLimit": True}
    )
    with pytest.raises(PipelineRuntimeError, match="tronqué"):
        _read(cf.read_arcgisonline, conn, session, tenant, user, secretName="s", maxFeatures=2,
              layerUrl=httpserver.url_for("/arcgis/rest/services/S/FeatureServer/0"))  # fmt: skip


def test_csv_serialization_neutralizes_formulas():
    # AUD-152 : writer.ftp CSV neutralise comme les autres sorties CSV (cell_safety).
    import pandas as pd

    from app.pipelines.ops.cloudfiles import _serialize

    frame = pd.DataFrame({"=cmd": ['=HYPERLINK("http://evil","x")', "ok"], "n": [-5, 1]})
    lines = _serialize(frame, "csv").decode().splitlines()
    assert lines[0] == "'=cmd,n"
    assert lines[1].startswith("\"'=HYPERLINK(")
    assert lines[1].endswith(",-5")  # un nombre typé négatif reste numérique
    assert lines[2] == "ok,1"
