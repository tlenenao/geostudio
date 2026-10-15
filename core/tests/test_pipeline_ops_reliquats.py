# SPDX-License-Identifier: Apache-2.0
"""Voie S FME : reliquats dépendant du modèle de pipeline (module ops/reliquats.py + compléments
de readers2/raster2). Fixtures générées par code (< 100 Ko)."""

import json
import os

import duckdb
import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from app.configs.schemas import PipelineNode, PipelinePayload
from app.pipelines import compiler, runtime
from app.pipelines import egress as pipelines_egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import reliquats
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.pipelines.registries import READERS, WRITERS
from tests.test_pipeline_ops_raster2 import env  # noqa: F401
from tests.test_pipeline_ops_raster2 import run as rrun

LANE_OPS = {
    "transform.removeSrid", "transform.localCoordinateSystem", "transform.databaseJoin",
    "writer.topojson",
}  # fmt: skip
_REAL_DSN_GUARD = pipelines_egress.assert_dsn_egress_allowed
_REAL_EGRESS_GUARD = pipelines_egress.assert_egress_allowed


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial; SET memory_limit='768MB'; SET threads=2;")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _fileio(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")


def _compile(conn, op, params, srid=4326, src="src", view="out"):
    sql = compiler.compile_transform_sql(op, params, input_view=src, input_srid=srid)
    conn.execute(f"CREATE OR REPLACE TEMP TABLE {view} AS {sql}")
    return compiler.transform_output_srid(op, params, input_srid=srid)


def test_lane_contracts_and_catalog(monkeypatch):
    assert {c.op for c in reliquats.CONTRACTS} == LANE_OPS
    assert set(reliquats.WRITERS) == {"writer.topojson"} and WRITERS["writer.topojson"]
    assert not reliquats.READERS
    assert all(OPERATIONS[o].engine_license for o in LANE_OPS)
    assert LANE_OPS <= set(ops_catalog())
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert "writer.topojson" not in ops_catalog()  # op fichier masquée quand le flag est éteint
    assert "transform.databaseJoin" in ops_catalog()
    assert READERS  # registre agrégé importable avec le module de voie


# ------------------------------------------------------------------ SRID 0


def test_remove_srid_keeps_coordinates_and_outputs_srid_zero(conn):
    conn.execute("CREATE TABLE src AS SELECT 1 AS id, ST_Point(700000, 6600000) AS geometry")
    assert _compile(conn, "transform.removeSrid", {}, srid=2154) == 0
    assert conn.execute("SELECT id, ST_AsText(geometry) FROM out").fetchall() == [
        (1, "POINT (700000 6600000)")
    ]


def test_srid_zero_refuses_reprojection_and_meter_buffer(conn):
    conn.execute("CREATE TABLE src AS SELECT ST_Point(1, 2) AS geometry")
    with pytest.raises(duckdb.Error, match="EPSG:0"):
        _compile(conn, "transform.reproject", {"targetCrs": "EPSG:4326"}, srid=0)
    with pytest.raises(duckdb.Error, match="EPSG:0"):
        _compile(conn, "transform.buffer", {"distance": 5, "unit": "meters"}, srid=0)


def test_local_cs_from_local_roundtrip(conn):
    # origine (2°E, 48°N), axe Y local tourné de 90° (vers l'est), 1 unité = 2 m
    params = {"originLon": 2.0, "originLat": 48.0, "rotation": 90.0, "scale": 2.0}
    conn.execute("CREATE TABLE src AS SELECT 1 AS id, ST_Point(0, 0) AS geometry UNION ALL "
                 "SELECT 2, ST_Point(0, 500)")  # fmt: skip
    srid = _compile(conn, "transform.localCoordinateSystem",
                    {**params, "direction": "fromLocal", "targetSrid": 4326}, srid=0)  # fmt: skip
    assert srid == 4326
    (x0, y0), (x1, y1) = conn.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out ORDER BY id"
    ).fetchall()
    assert (x0, y0) == pytest.approx((2.0, 48.0), abs=1e-9)
    # 500 unités * 2 m = 1000 m plein est : même latitude, ~0.0134° de longitude à 48°N (ellipsoïde)
    assert y1 == pytest.approx(48.0, abs=1e-4) and x1 - 2.0 == pytest.approx(0.0134003, rel=1e-4)
    # retour : toLocal redonne les coordonnées locales, SRID 0
    srid = _compile(conn, "transform.localCoordinateSystem", {**params, "direction": "toLocal"},
                    srid=4326, src="out", view="back")  # fmt: skip
    assert srid == 0
    got = conn.execute("SELECT ST_X(geometry), ST_Y(geometry) FROM back ORDER BY id").fetchall()
    assert got[0] == pytest.approx((0, 0), abs=1e-6) and got[1] == pytest.approx((0, 500), abs=1e-6)


def test_local_cs_validation_and_srid_zero_to_local(conn):
    with pytest.raises(ValidationError, match="targetSrid requis"):
        OPERATIONS["transform.localCoordinateSystem"].params_schema.model_validate(
            {"originLon": 0, "originLat": 0}
        )
    with pytest.raises(ValidationError):
        OPERATIONS["transform.localCoordinateSystem"].params_schema.model_validate(
            {"originLon": 0, "originLat": 95, "targetSrid": 4326}
        )
    conn.execute("CREATE TABLE src AS SELECT ST_Point(1, 2) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="SRID défini"):
        _compile(conn, "transform.localCoordinateSystem",
                 {"originLon": 0, "originLat": 0, "direction": "toLocal"}, srid=0)  # fmt: skip


def test_local_cs_degenerate_geometries(conn):
    conn.execute(
        "CREATE TABLE src AS SELECT 1 AS id, NULL::GEOMETRY AS geometry UNION ALL "
        "SELECT 2, ST_GeomFromText('POINT EMPTY') UNION ALL "
        "SELECT 3, ST_GeomFromText('LINESTRING Z (0 0 5, 10 0 6)')"
    )
    _compile(conn, "transform.localCoordinateSystem",
             {"originLon": 2, "originLat": 48, "targetSrid": 4326}, srid=0)  # fmt: skip
    got = conn.execute("SELECT id, geometry IS NULL, ST_IsEmpty(geometry), ST_ZMax(geometry) "
                       "FROM out ORDER BY id").fetchall()  # fmt: skip
    assert got[0][1] is True and got[1][2] is True and got[2][3] == 6.0  # Z conservé


def _payload(nodes):
    pairs = enumerate(zip(nodes, nodes[1:], strict=False))
    edges = [{"id": f"e{i}", "from": a["id"], "to": b["id"]} for i, (a, b) in pairs]
    return PipelinePayload.model_validate({"nodes": nodes, "edges": edges})


def _fake_reader(conn, *, view_name, **_):
    conn.execute(f"CREATE TEMP TABLE {view_name} AS SELECT 1 AS id, ST_Point(10, 20) AS geometry")
    return 2154


@pytest.mark.parametrize("writer", ["writer.collection", "writer.dataset"])
def test_collection_writers_refuse_srid_zero(monkeypatch, tmp_path, writer):
    monkeypatch.setitem(READERS, "reader.connector.rest", _fake_reader)
    called = []
    monkeypatch.setitem(WRITERS, writer, lambda *a, **k: called.append(1))
    payload = _payload([
        {"id": "r", "kind": "reader", "op": "reader.connector.rest", "params": {"baseUrl": "https://x.test"}},
        {"id": "t", "kind": "transform", "op": "transform.removeSrid", "params": {}},
        {"id": "w", "kind": "writer", "op": writer, "params": {"collectionId": "c1"}},
    ])  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="SRID non défini"):
        runtime.run_pipeline(None, payload=payload, tenant_id="t", user=None,
                             endpoint_url="http://localhost:9000", access_key="x",
                             secret_key="y", base_uri=str(tmp_path))  # fmt: skip
    assert called == []


def test_writer_file_writes_without_srs_for_srid_zero(monkeypatch, tmp_path):
    import pyogrio

    monkeypatch.setitem(READERS, "reader.connector.rest", _fake_reader)
    out = tmp_path / "o.gpkg"
    payload = _payload([
        {"id": "r", "kind": "reader", "op": "reader.connector.rest", "params": {"baseUrl": "https://x.test"}},
        {"id": "t", "kind": "transform", "op": "transform.removeSrid", "params": {}},
        {"id": "w", "kind": "writer", "op": "writer.file", "params": {"path": str(out)}},
    ])  # fmt: skip
    runtime.run_pipeline(None, payload=payload, tenant_id="t", user=None,
                         endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
                         base_uri=str(tmp_path))  # fmt: skip
    info = pyogrio.read_info(str(out))
    # GPKG : un SRS non défini est représenté par srs_id 0 « Undefined geographic SRS »
    assert "Undefined" in (info["crs"] or "Undefined") and info["features"] == 1


def test_raster_and_routing_ops_refuse_srid_zero(conn):
    from types import SimpleNamespace

    from app.pipelines.ops import routing

    conn.execute("CREATE TABLE src AS SELECT ST_Point(1, 2) AS geometry")
    for op, params in (
        ("transform.zonalStats", {"itemId": "x"}),
        ("transform.vectorOnRaster", {"itemId": "x"}),
        ("transform.surfaceDrape", {"itemId": "x"}),
    ):
        with pytest.raises(PipelineRuntimeError, match=r"\(0\)"):
            OPERATIONS[op].execute(
                conn, input_view="src", view_name="o", params=params,
                secret_resolver=SimpleNamespace(session=object(), user=object()),
                preview=False, input_srid=0,
            )  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match=r"\(0\)"):
        routing._origins(conn, "src", [], False, 0)


# ------------------------------------------------------------------ TopoJSON


def _write_topo(conn, path, sql, **params):
    conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS {sql}")
    node = PipelineNode(id="w", kind="writer", op="writer.topojson",
                        params={"path": str(path), **params})  # fmt: skip
    return WRITERS["writer.topojson"](None, conn, node=node, view_by_node={"w": "inp"},
                                      tenant_id="t", user=None)  # fmt: skip


def test_topojson_shared_arcs_roundtrip(conn, tmp_path):
    import pyogrio

    p = tmp_path / "out" / "t.topojson"
    stat = _write_topo(
        conn, p,
        "SELECT 'a' AS name, 1 AS n, ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))') AS geometry "
        "UNION ALL SELECT 'b', 2, ST_GeomFromText('POLYGON((1 0,2 0,2 1,1 1,1 0))') "
        "UNION ALL SELECT 'p', 3, ST_Point(5, 5) "
        "UNION ALL SELECT 'l', 4, ST_GeomFromText('LINESTRING(0 0, 1 0)') "
        "UNION ALL SELECT 'z', 5, NULL",
        objectName="parcelles",
    )  # fmt: skip
    assert stat.rowCount == 5
    doc = json.loads(p.read_text())
    assert doc["type"] == "Topology" and list(doc["objects"]) == ["parcelles"]
    geoms = doc["objects"]["parcelles"]["geometries"]
    assert [g["properties"]["name"] for g in geoms] == ["a", "b", "p", "l", "z"]
    assert geoms[4]["type"] is None and geoms[2] == {
        "type": "Point", "coordinates": [5.0, 5.0], "properties": {"name": "p", "n": 3}
    }  # fmt: skip
    # l'arête commune (1 0)-(1 1) n'est stockée qu'une fois : référencée par a et (inversée) par b
    arcs_a = {a for ring in geoms[0]["arcs"] for a in ring}
    arcs_b = {a for ring in geoms[1]["arcs"] for a in ring}
    shared = {a if a >= 0 else ~a for a in arcs_a} & {a if a >= 0 else ~a for a in arcs_b}
    assert len(shared) == 1
    # relu par GDAL (pilote TopoJSON) : géométries reconstruites identiques
    gdf = pyogrio.read_dataframe(str(p))
    by = dict(zip(gdf["name"], gdf.geometry, strict=True))
    assert by["a"].equals(__import__("shapely").box(0, 0, 1, 1))
    assert by["b"].equals(__import__("shapely").box(1, 0, 2, 1))


def test_topojson_guards(conn, tmp_path, monkeypatch):
    with pytest.raises(PipelineRuntimeError, match="absolu"):
        _write_topo(conn, "rel/t.json", "SELECT ST_Point(0, 0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _write_topo(conn, tmp_path / "t.json", "SELECT 1 AS a")
    monkeypatch.setattr(reliquats, "MAX_TOPOJSON_FEATURES", 1)
    with pytest.raises(PipelineRuntimeError, match="entités"):
        _write_topo(
            conn, tmp_path / "t.json", "SELECT ST_Point(i, 0) AS geometry FROM range(2) t(i)"
        )
    monkeypatch.setattr(reliquats, "MAX_TOPOJSON_FEATURES", 10)
    monkeypatch.setattr(reliquats, "MAX_TOPOJSON_VERTICES", 3)
    with pytest.raises(PipelineRuntimeError, match="sommets"):
        _write_topo(
            conn,
            tmp_path / "t.json",
            "SELECT ST_GeomFromText('LINESTRING(0 0,1 1,2 2,3 3)') AS geometry",
        )
    assert not os.path.exists(tmp_path / "t.json")  # rien d'écrit sur refus
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
        _write_topo(conn, tmp_path / "t.json", "SELECT ST_Point(0, 0) AS geometry")


def test_topojson_empty_and_multi(conn, tmp_path):
    p = tmp_path / "m.json"
    _write_topo(
        conn, p,
        "SELECT ST_GeomFromText('MULTIPOLYGON(((0 0,1 0,1 1,0 0)),((5 5,6 5,6 6,5 5)))') "
        "AS geometry "
        "UNION ALL SELECT ST_GeomFromText('POLYGON EMPTY') "
        "UNION ALL SELECT ST_GeomFromText('MULTILINESTRING((0 0,1 1),(2 2,3 3))')",
    )  # fmt: skip
    g = json.loads(p.read_text())["objects"]["data"]["geometries"]
    assert g[0]["type"] == "MultiPolygon" and len(g[0]["arcs"]) == 2
    assert g[1]["type"] is None and g[2]["type"] == "MultiLineString"


# ------------------------------------------------------------------ DatabaseJoiner


class _Resolver:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, name):
        return self.payloads[name]


def _dsn():
    return os.environ["CORE_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
def remote(pg_engine, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(pipelines_egress, "assert_dsn_egress_allowed", lambda dsn: None)
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    with pg_engine.begin() as db:
        db.execute(sa.text("DROP TABLE IF EXISTS fme_s_ref"))
        db.execute(sa.text(
            "CREATE TABLE fme_s_ref (code int, zone text, label text, pop numeric(10,2), "
            "secret text)"
        ))  # fmt: skip
        db.execute(sa.text(
            "INSERT INTO fme_s_ref VALUES (1,'A','un',1.5,'x'),(2,'A','deux',2,'y'),"
            "(2,'B','deux-b',3,'z'),(9,'A','neuf',9,'w')"
        ))  # fmt: skip
    yield _Resolver({
        "ext": SimpleNamespace(kind="postgres_dsn", dsn=_dsn()),
        "rest": SimpleNamespace(kind="api_key", dsn=None),
    })  # fmt: skip
    with pg_engine.begin() as db:
        db.execute(sa.text("DROP TABLE IF EXISTS fme_s_ref"))


def _join(conn, resolver, preview=False, **params):
    conn.execute("DROP TABLE IF EXISTS out")
    OPERATIONS["transform.databaseJoin"].execute(
        conn, input_view="src", view_name="out",
        params={"secretName": "ext", "table": "fme_s_ref", **params},
        secret_resolver=resolver, preview=preview, input_srid=4326,
    )  # fmt: skip
    return conn.execute("SELECT * FROM out ORDER BY ALL").fetchall()


@pytest.mark.postgis
def test_database_join_left_inner_columns_prefix(remote, conn):
    conn.execute(
        "CREATE TABLE src AS SELECT * FROM (VALUES (1,'p'),(2,'q'),(3,'r'),(NULL,'s')) t(code, nom)"
    )
    got = _join(conn, remote, inputKeys=["code"], columns=["label", "pop"], joinType="left")
    assert got == [(1, "p", "un", 1.5), (2, "q", "deux", 2.0), (2, "q", "deux-b", 3.0),
                   (3, "r", None, None), (None, "s", None, None)]  # fmt: skip
    got = _join(
        conn, remote, inputKeys=["code"], columns=["label"], joinType="inner", prefix="ref_"
    )
    assert got == [(1, "p", "un"), (2, "q", "deux"), (2, "q", "deux-b")]
    assert "ref_label" in [d[0] for d in conn.execute("SELECT * FROM out").description]
    # composite + tableKeys différents, toutes colonnes non clés par défaut ; aperçu autorisé
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT 2 AS c, 'B' AS z")
    got = _join(conn, remote, preview=True, inputKeys=["c", "z"], tableKeys=["code", "zone"])
    assert got == [(2, "B", "deux-b", 3.0, "z")]


@pytest.mark.postgis
def test_database_join_pushes_keys_and_caps(remote, conn, monkeypatch):
    seen = []
    real_exec = sa.engine.Connection.execute

    def spy(self, stmt, *a, **k):
        if isinstance(stmt, sa.Select) and "fme_s_ref" in str(stmt):
            seen.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return real_exec(self, stmt, *a, **k)

    monkeypatch.setattr(sa.engine.Connection, "execute", spy)
    conn.execute("CREATE TABLE src AS SELECT 9 AS code")
    assert _join(conn, remote, inputKeys=["code"], columns=["label"]) == [(9, "neuf")]
    assert any("IN (9)" in s for s in seen)  # seules les clés d'entrée sont demandées
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT 2 AS code")
    with pytest.raises(PipelineRuntimeError, match="plafond de 1 lignes"):
        _join(conn, remote, inputKeys=["code"], maxRows=1)
    monkeypatch.setattr(reliquats, "MAX_JOIN_KEYS", 1)
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT * FROM (VALUES (1),(2)) t(code)")
    with pytest.raises(PipelineRuntimeError, match="clés distinctes"):
        _join(conn, remote, inputKeys=["code"])


@pytest.mark.postgis
def test_database_join_errors_and_injection(remote, conn):
    conn.execute("CREATE TABLE src AS SELECT 1 AS code, ST_Point(0,0) AS geometry, 'u' AS label")
    with pytest.raises(PipelineRuntimeError, match="absente.*entrée"):
        _join(conn, remote, inputKeys=["nope"])
    with pytest.raises(PipelineRuntimeError, match="géométrie"):
        _join(conn, remote, inputKeys=["geometry"])
    with pytest.raises(PipelineRuntimeError, match="déjà présente"):
        _join(conn, remote, inputKeys=["code"], columns=["label"])
    with pytest.raises(PipelineRuntimeError, match="absente.*fme_s_ref"):
        _join(conn, remote, inputKeys=["code"], columns=["nope"])
    with pytest.raises(PipelineRuntimeError, match="introuvable"):
        _join(conn, remote, inputKeys=["code"], table="fme_s_absente")
    with pytest.raises(PipelineRuntimeError, match="expected postgres_dsn"):
        _join(conn, remote, inputKeys=["code"], secretName="rest")
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _join(conn, remote, inputKeys=["code"], secretName="absent")
    for bad in ({"table": "t; DROP TABLE x"}, {"columns": ["a b"]}, {"tableKeys": ["a", "b"]}):
        with pytest.raises(ValidationError):
            _join(conn, remote, inputKeys=["code"], **bad)
    # valeur de clé hostile : paramètre lié, jamais concaténée
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT '1'' OR ''1''=''1' AS zone")
    assert _join(conn, remote, inputKeys=["zone"], columns=["label"], joinType="inner") == []
    # entrée sans aucune clé non nulle : résultat vide typé (jointure gauche conservée)
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT NULL::INTEGER AS code")
    assert _join(conn, remote, inputKeys=["code"], columns=["label"]) == [(None, None)]


@pytest.mark.postgis
def test_database_join_egress_guard_is_real(remote, conn, monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_dsn_egress_allowed", _REAL_DSN_GUARD)
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    conn.execute("CREATE TABLE src AS SELECT 1 AS code")
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _join(conn, remote, inputKeys=["code"])


# ------------------------------------------------------------------ SurfaceDraper (3D)


@pytest.fixture()
def renv(request):
    return request.getfixturevalue("env")


def _dem(e):
    import numpy as np

    # z = 10 * colonne (monte vers l'est), pixels de 0,001°, origine (2, 45)
    return e.add("dem", np.tile(np.arange(8) * 10.0, (8, 1)), res=0.001, y0=45.0)


def _drape(e, conn, srid=4326, **params):
    conn.execute("DROP TABLE IF EXISTS out")
    rrun(e, "transform.surfaceDrape", {"mode": "geometry", **params}, conn=conn, srid=srid)
    return conn.execute("SELECT n, ST_AsText(geometry), drape_error FROM out ORDER BY n").fetchall()


def test_drape_lines_and_polygons_in_3d(renv, conn):
    a = _dem(renv)
    conn.execute("CREATE TABLE src (n INT, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO src VALUES (1, ST_Point(2.0035, 44.9965)), "
        "(2, ST_GeomFromText('LINESTRING(2.0005 44.9995, 2.0035 44.9995)')), "
        "(3, ST_GeomFromText('POLYGON((2.0005 44.9995, 2.0025 44.9995, 2.0025 44.9975, "
        "2.0005 44.9995))')), (4, NULL), (5, ST_GeomFromText('LINESTRING EMPTY')), "
        "(6, ST_GeomFromText('LINESTRING(2.0005 44.9995, 9 9)'))"
    )
    got = _drape(renv, conn, densify=False, itemId=a)
    assert got[0][1] == "POINT Z (2.0035 44.9965 30)"
    assert got[1][1] == "LINESTRING Z (2.0005 44.9995 0, 2.0035 44.9995 30)"
    assert got[2][1].startswith("POLYGON Z ((2.0005 44.9995 0, 2.0025 44.9995 20,")
    assert got[3][1] is None and got[4][1] == "LINESTRING EMPTY"
    assert got[5][2] and got[5][1] == "LINESTRING (2.0005 44.9995, 9 9)"  # hors raster
    # densification au pas du pixel : la ligne suit le relief cellule par cellule
    got = _drape(renv, conn, itemId=a)
    zs = [float(v.split()[-1]) for v in got[1][1][len("LINESTRING Z (") : -1].split(", ")]
    assert zs == [0.0, 10.0, 20.0, 30.0]
    # outsideZ : sommets hors raster remplacés
    got = _drape(renv, conn, densify=False, outsideZ=-1, itemId=a)
    assert got[5][1] == "LINESTRING Z (2.0005 44.9995 0, 9 9 -1)" and got[5][2] is None


def test_drape_geometry_reprojects_and_caps(renv, conn, monkeypatch):
    from app.pipelines.ops import raster2

    a = _dem(renv)
    conn.execute("CREATE TABLE src (n INT, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO src SELECT 1, ST_Transform(ST_GeomFromText('LINESTRING(2.0005 44.9995, "
        "2.0035 44.9995)'), 'EPSG:4326', 'EPSG:3857', always_xy := true)"
    )
    got = _drape(renv, conn, srid=3857, densify=False, itemId=a)
    assert got[0][1].startswith("LINESTRING Z (222") and got[0][1].endswith(" 30)")
    monkeypatch.setattr(raster2, "MAX_DRAPE_VERTICES", 3)
    with pytest.raises(PipelineRuntimeError, match="vertices"):
        _drape(renv, conn, srid=3857, itemId=a)
    conn.execute(
        "CREATE OR REPLACE TABLE src AS SELECT 1 AS drape_error, ST_Point(0, 0) AS geometry"
    )
    with pytest.raises(PipelineRuntimeError, match="already has"):
        rrun(renv, "transform.surfaceDrape", {"mode": "geometry", "itemId": a}, conn=conn)
