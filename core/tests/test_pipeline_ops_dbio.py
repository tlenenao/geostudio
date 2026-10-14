# SPDX-License-Identifier: Apache-2.0
"""Voie B FME : DatabaseUpdater/DatabaseDeleter (writer.connector.postgres.*),
Google Sheets (reader.connector.googlesheets), TopoJSON (reader.file via GDAL)."""

import os

import duckdb
import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from app.configs.schemas import PipelineNode
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import egress as pipelines_egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import dbio
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
_REAL_DSN_GUARD = pipelines_egress.assert_dsn_egress_allowed
_REAL_EGRESS_GUARD = pipelines_egress.assert_egress_allowed

LANE_OPS = {
    "writer.connector.postgres.update",
    "writer.connector.postgres.delete",
    "reader.connector.googlesheets",
}


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
def _no_guard(monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    monkeypatch.setattr(pipelines_egress, "assert_dsn_egress_allowed", lambda dsn: None)


def _secret(session, tenant, user, name, payload):
    ct, nonce = encrypt(payload)
    secrets_repo.create_secret(
        session, tenant_id=tenant.id, created_by=user.id, name=name,
        kind=payload["kind"], ciphertext=ct, nonce=nonce,
    )  # fmt: skip


def test_lane_contracts_and_catalog():
    assert {c.op for c in dbio.CONTRACTS} == LANE_OPS
    assert set(dbio.WRITERS) == {o for o in LANE_OPS if o.startswith("writer.")}
    assert set(dbio.READERS) == {"reader.connector.googlesheets"}
    exposed = set(ops_catalog())
    assert LANE_OPS <= exposed
    assert all(OPERATIONS[o].engine_license for o in LANE_OPS)


# ------------------------------------------------------------------ DatabaseUpdater / Deleter


@pytest.fixture()
def remote(pg_engine, session, tenant, user):
    dsn = os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    _secret(session, tenant, user, "ext-pg", {"kind": "postgres_dsn", "dsn": dsn})
    with pg_engine.begin() as db:
        db.execute(sa.text("DROP TABLE IF EXISTS fme_b_t"))
        db.execute(sa.text("CREATE TABLE fme_b_t (id int PRIMARY KEY, name text, qty int)"))
        db.execute(sa.text("INSERT INTO fme_b_t VALUES (1,'a',10),(2,'b',20),(3,'c',30)"))
    yield pg_engine
    with pg_engine.begin() as db:
        db.execute(sa.text("DROP TABLE IF EXISTS fme_b_t"))


def _table(engine):
    with engine.connect() as db:
        return db.execute(sa.text("SELECT id, name, qty FROM fme_b_t ORDER BY id")).fetchall()


def _run(op, conn, session, tenant, user, params, sql):
    conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS {sql}")
    node = PipelineNode(id="w", kind="writer", op=op, params={"secretName": "ext-pg", **params})
    return dbio.WRITERS[op](
        session, conn, node=node, view_by_node={"w": "inp"}, tenant_id=tenant.id, user=user
    )


def test_update_by_key(remote, conn, session, tenant, user):
    stat = _run(
        "writer.connector.postgres.update", conn, session, tenant, user,
        {"table": "fme_b_t", "keyColumns": ["id"], "updateColumns": ["name"]},
        "SELECT * FROM (VALUES (1,'A'),(3,'C2'),(99,'zz')) t(id,name)",
    )  # fmt: skip
    assert (stat.rowCount, stat.extra["unmatched"]) == (2, 1)
    assert _table(remote) == [(1, "A", 10), (2, "b", 20), (3, "C2", 30)]


def test_delete_by_key(remote, conn, session, tenant, user):
    stat = _run(
        "writer.connector.postgres.delete", conn, session, tenant, user,
        {"table": "public.fme_b_t", "keyColumns": ["id"]},
        "SELECT * FROM (VALUES (2),(99)) t(id)",
    )  # fmt: skip
    assert stat.rowCount == 1
    assert [r[0] for r in _table(remote)] == [1, 3]


def test_injection_in_values_is_inert(remote, conn, session, tenant, user):
    evil = "x'; DROP TABLE fme_b_t; --"
    _run(
        "writer.connector.postgres.update", conn, session, tenant, user,
        {"table": "fme_b_t", "keyColumns": ["name"], "updateColumns": ["qty"]},
        f"SELECT '{evil.replace(chr(39), chr(39) * 2)}' AS name, 5 AS qty",
    )  # fmt: skip
    assert len(_table(remote)) == 3  # table intacte, aucune ligne touchée


def test_injection_in_delete_key_never_widens_where(remote, conn, session, tenant, user):
    stat = _run(
        "writer.connector.postgres.delete", conn, session, tenant, user,
        {"table": "fme_b_t", "keyColumns": ["name"]},
        "SELECT '''a'' OR 1=1 --' AS name",
    )  # fmt: skip
    assert stat.rowCount == 0
    assert len(_table(remote)) == 3


@pytest.mark.parametrize("table", ['fme_b_t"; DROP TABLE x; --', "a.b.c", "t t", "", "x;y"])
def test_table_injection_rejected_by_schema(table):
    with pytest.raises(ValidationError):
        dbio.WriterConnectorPostgresDeleteParams(secretName="s", table=table, keyColumns=["id"])


def test_column_injection_rejected(remote, conn, session, tenant, user):
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _run(
            "writer.connector.postgres.update", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"], "updateColumns": ['name" = 1; --']},
            "SELECT 1 AS id, 'x' AS \"name\"\"=1; --\"",
        )  # fmt: skip
    # colonne présente en entrée mais absente de la table distante
    with pytest.raises(PipelineRuntimeError, match="not found in 'fme_b_t'"):
        _run(
            "writer.connector.postgres.update", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"], "updateColumns": ["nope"]},
            "SELECT 1 AS id, 'x' AS nope",
        )  # fmt: skip
    assert _table(remote)[0] == (1, "a", 10)


def test_no_key_is_unconstructible():
    for model, extra in (
        (dbio.WriterConnectorPostgresDeleteParams, {}),
        (dbio.WriterConnectorPostgresUpdateParams, {"updateColumns": ["a"]}),
    ):
        with pytest.raises(ValidationError):
            model(secretName="s", table="t", keyColumns=[], **extra)
    with pytest.raises(ValidationError):  # clé = colonne mise à jour
        dbio.WriterConnectorPostgresUpdateParams(
            secretName="s", table="t", keyColumns=["id"], updateColumns=["id"]
        )


def test_null_key_refused_and_nothing_written(remote, conn, session, tenant, user):
    with pytest.raises(PipelineRuntimeError, match="NULL"):
        _run(
            "writer.connector.postgres.delete", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"]},
            "SELECT * FROM (VALUES (1),(NULL)) t(id)",
        )  # fmt: skip
    assert len(_table(remote)) == 3


def test_empty_input_is_noop(remote, conn, session, tenant, user):
    stat = _run(
        "writer.connector.postgres.delete", conn, session, tenant, user,
        {"table": "fme_b_t", "keyColumns": ["id"]},
        "SELECT 1 AS id WHERE false",
    )  # fmt: skip
    assert stat.rowCount == 0 and len(_table(remote)) == 3


def test_single_transaction_rolls_back_on_row_error(remote, conn, session, tenant, user):
    with pytest.raises(sa.exc.DBAPIError):  # 2e ligne : texte dans une colonne int
        _run(
            "writer.connector.postgres.update", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"], "updateColumns": ["qty"]},
            "SELECT * FROM (VALUES (1,'7'),(2,'pas un entier')) t(id,qty)",
        )  # fmt: skip
    assert _table(remote)[0] == (1, "a", 10)  # la 1re ligne n'est pas restée appliquée


def test_row_cap(remote, conn, session, tenant, user, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS", "2")
    with pytest.raises(PipelineRuntimeError, match="plafond"):
        _run(
            "writer.connector.postgres.delete", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"]},
            "SELECT * FROM (VALUES (1),(2),(3)) t(id)",
        )  # fmt: skip
    assert len(_table(remote)) == 3


def test_wrong_secret_kind_and_missing_secret(remote, conn, session, tenant, user):
    _secret(session, tenant, user, "tok", {"kind": "bearer_token", "token": "t"})
    p = {"table": "fme_b_t", "keyColumns": ["id"]}
    op = "writer.connector.postgres.delete"
    node = PipelineNode(id="w", kind="writer", op=op, params={"secretName": "tok", **p})
    conn.execute("CREATE TEMP TABLE inp AS SELECT 1 AS id")
    kw = {"view_by_node": {"w": "inp"}, "tenant_id": tenant.id, "user": user}
    with pytest.raises(PipelineRuntimeError, match="expected postgres_dsn"):
        dbio.WRITERS[op](session, conn, node=node, **kw)
    node.params["secretName"] = "absent"
    with pytest.raises(PipelineRuntimeError, match="not found"):
        dbio.WRITERS[op](session, conn, node=node, **kw)


def test_egress_guard_blocks_internal_dsn(remote, conn, session, tenant, user, monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_dsn_egress_allowed", _REAL_DSN_GUARD)
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    with pytest.raises(pipelines_egress.EgressBlockedError):
        _run(
            "writer.connector.postgres.delete", conn, session, tenant, user,
            {"table": "fme_b_t", "keyColumns": ["id"]},
            "SELECT 1 AS id",
        )  # fmt: skip
    assert len(_table(remote)) == 3


def test_audit_written_before_write(remote, conn, session, tenant, user):
    from app.audit.models import AuditLog

    _run(
        "writer.connector.postgres.delete", conn, session, tenant, user,
        {"table": "fme_b_t", "keyColumns": ["id"]}, "SELECT 1 AS id",
    )  # fmt: skip
    row = session.query(AuditLog).filter_by(action="pipeline.external_write").one()
    assert row.payload["table"] == "fme_b_t"


# ------------------------------------------------------------------ Google Sheets

SHEET_ID = "1AbCdEfGhIjKlMnOp"


@pytest.fixture()
def sheets(httpserver, monkeypatch):
    monkeypatch.setattr(dbio, "_SHEETS_BASE", httpserver.url_for("/v4/spreadsheets"))
    return httpserver


def _read(conn, session, tenant, user, **p):
    return dbio.read_googlesheets(
        conn, session=session, tenant_id=tenant.id, node_id="g", view_name="node_g",
        user=user, base_uri="",
        params={"secretName": "gs", "spreadsheetId": SHEET_ID, **p},
    )  # fmt: skip


def test_googlesheets_reads_range_with_bearer(sheets, conn, session, tenant, user):
    base = sheets.url_for("/v4/")
    _secret(session, tenant, user, "gs", {"kind": "bearer_token", "token": "tok", "baseUrl": base})
    sheets.expect_request(
        f"/v4/spreadsheets/{SHEET_ID}/values/Feuil1!A:C", headers={"Authorization": "Bearer tok"}
    ).respond_with_json({"values": [["id", "nom", "mix"], [1, "a", 1], [2, "b", "x"], [3]]})
    assert _read(conn, session, tenant, user, range="Feuil1!A:C") == 4326
    rows = conn.execute("SELECT id, nom, mix FROM node_g ORDER BY id").fetchall()
    assert rows == [(1, "a", "1"), (2, "b", "x"), (3, None, None)]


def test_googlesheets_api_key_query(sheets, conn, session, tenant, user):
    _secret(session, tenant, user, "gs", {"kind": "api_key", "location": "query", "key": "key",
            "value": "K", "baseUrl": sheets.url_for("/v4/")})  # fmt: skip
    sheets.expect_request(
        f"/v4/spreadsheets/{SHEET_ID}/values/A:ZZ",
        query_string="valueRenderOption=UNFORMATTED_VALUE&majorDimension=ROWS&key=K",
    ).respond_with_json({"values": [["x"], [1.5]]})
    _read(conn, session, tenant, user)
    assert conn.execute("SELECT x FROM node_g").fetchall() == [(1.5,)]


def test_googlesheets_secret_scope_and_kind(sheets, conn, session, tenant, user):
    _secret(session, tenant, user, "gs",
            {"kind": "bearer_token", "token": "t", "baseUrl": "https://evil.example/"})  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="baseUrl"):
        _read(conn, session, tenant, user)
    _secret(session, tenant, user, "pg", {"kind": "postgres_dsn", "dsn": "postgresql://u:p@h/d"})
    with pytest.raises(PipelineRuntimeError, match="expected bearer_token or api_key"):
        _read(conn, session, tenant, user, secretName="pg")
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _read(conn, session, tenant, user, secretName="absent")


@pytest.mark.parametrize(
    "values, msg",
    [([], "empty range"), ([["a", "a"], [1, 2]], "duplicate"), ([["a", ""], [1, 2]], "empty or")],
)
def test_googlesheets_degenerate_ranges(sheets, conn, session, tenant, user, values, msg):
    _secret(session, tenant, user, "gs",
            {"kind": "bearer_token", "token": "t", "baseUrl": sheets.url_for("/v4/")})  # fmt: skip
    sheets.expect_request(f"/v4/spreadsheets/{SHEET_ID}/values/A:ZZ").respond_with_json(
        {"values": values}
    )
    with pytest.raises(PipelineRuntimeError, match=msg):
        _read(conn, session, tenant, user)


def test_googlesheets_http_error_and_bad_id(sheets, conn, session, tenant, user):
    _secret(session, tenant, user, "gs",
            {"kind": "bearer_token", "token": "t", "baseUrl": sheets.url_for("/v4/")})  # fmt: skip
    sheets.expect_request(f"/v4/spreadsheets/{SHEET_ID}/values/A:ZZ").respond_with_data("no", 403)
    with pytest.raises(PipelineRuntimeError, match="HTTP 403"):
        _read(conn, session, tenant, user)
    with pytest.raises(ValidationError):
        _read(conn, session, tenant, user, spreadsheetId="../../x")


# ------------------------------------------------------------------ TopoJSON

TOPO = (
    '{"type":"Topology","transform":{"scale":[1,1],"translate":[0,0]},'
    '"objects":{"pts":{"type":"GeometryCollection","geometries":['
    '{"type":"Point","coordinates":[2,3],"properties":{"n":"a"}}]}},"arcs":[]}'
)


def test_topojson_read_via_reader_file(tmp_path, conn, session, tenant, user, monkeypatch):
    """TopoJSON (lecture) est couvert par reader.file (pilote GDAL TopoJSON, lecture seule)."""
    from app.pipelines.runtime import _read_file

    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    f = tmp_path / "t.topojson"
    f.write_text(TOPO)
    _read_file(
        conn, session=session, tenant_id=tenant.id, node_id="t", params={"path": str(f)},
        view_name="node_t", user=user, base_uri="",
    )  # fmt: skip
    assert conn.execute("SELECT n, ST_AsText(geometry) FROM node_t").fetchall() == [
        ("a", "POINT (2 3)")
    ]
