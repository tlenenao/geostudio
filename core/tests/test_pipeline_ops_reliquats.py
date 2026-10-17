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
    with pytest.raises(PipelineRuntimeError, match="setSrid"):  # AUD-077 : refus explicite
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
    with pytest.raises(PipelineRuntimeError, match="sans SRID"):
        _compile(conn, "transform.localCoordinateSystem",
                 {"originLon": 0, "originLat": 0, "targetSrid": 4326}, srid=4326)  # fmt: skip


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


@pytest.mark.parametrize(
    "writer", ["writer.collection", "writer.dataset", "writer.export", "writer.topojson"]
)
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
    with pytest.raises(PipelineRuntimeError, match="NaN"):
        _write_topo(conn, tmp_path / "t.json",
                    "SELECT 'NaN'::DOUBLE AS v, ST_Point(0, 0) AS geometry")  # fmt: skip
    assert not os.path.exists(tmp_path / "t.json")
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
    for bad in (
        {"table": "t; DROP TABLE x"}, {"columns": ["a b"]}, {"tableKeys": ["a", "b"]},
        {"columns": ["label", "label"]},
    ):  # fmt: skip
        with pytest.raises(ValidationError):
            _join(conn, remote, inputKeys=["code"], **bad)
    # valeur de clé hostile : paramètre lié, jamais concaténée
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT '1'' OR ''1''=''1' AS zone")
    assert _join(conn, remote, inputKeys=["zone"], columns=["label"], joinType="inner") == []
    # entrée sans aucune clé non nulle : résultat vide typé (jointure gauche conservée)
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT NULL::INTEGER AS code")
    assert _join(conn, remote, inputKeys=["code"], columns=["label"]) == [(None, None)]
    # schéma de sortie stable, résultat vide ou non (types issus de la table distante)
    types = {}
    for code in ("NULL::INTEGER", "1"):
        conn.execute(f"CREATE OR REPLACE TABLE src AS SELECT {code} AS code")
        _join(conn, remote, inputKeys=["code"], columns=["label", "pop"])
        types[code] = conn.execute(
            "SELECT column_name, data_type FROM duckdb_columns() "
            "WHERE table_name = 'out' ORDER BY column_index"
        ).fetchall()
    assert types["1"] == types["NULL::INTEGER"]
    assert [t for _, t in types["1"]] == ["INTEGER", "VARCHAR", "DOUBLE"]


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
    # ligne très longue (hors MNT) : refusée AVANT densification, sans allouer ses sommets
    import shapely

    monkeypatch.setattr(raster2, "MAX_DRAPE_VERTICES", 1000)
    calls = []
    real_seg = shapely.segmentize
    monkeypatch.setattr(shapely, "segmentize", lambda *a, **k: calls.append(a) or real_seg(*a, **k))
    conn.execute("CREATE OR REPLACE TABLE src AS SELECT 1 AS n, "
                 "ST_GeomFromText('LINESTRING(2.0005 44.9995, 12 50)') AS geometry")  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="vertices"):
        _drape(renv, conn, itemId=a)
    assert calls == []
    conn.execute(
        "CREATE OR REPLACE TABLE src AS SELECT 1 AS drape_error, ST_Point(0, 0) AS geometry"
    )
    with pytest.raises(PipelineRuntimeError, match="already has"):
        rrun(renv, "transform.surfaceDrape", {"mode": "geometry", "itemId": a}, conn=conn)


# ------------------------------------------------------------------ CityJSON 3D


def _read(fn, conn, **params):
    return fn(
        conn, session=None, tenant_id="t", node_id="n", view_name="v", user=None, base_uri="",
        params=params,
    )  # fmt: skip


def test_cityjson_solid3d_keeps_z_lod_attributes(tmp_path, conn):
    from app.pipelines.ops import readers2 as r2
    from tests.test_pipeline_ops_readers2 import _city_doc, _cityjson

    p = _cityjson(tmp_path / "c.city.json")
    assert _read(r2.read_cityjson, conn, path=p, geometry="solid3d") == 2154
    row = conn.execute(
        "SELECT id, lod, attributes, ST_GeometryType(geometry), ST_HasZ(geometry), "
        "ST_NumGeometries(geometry), ST_ZMin(geometry), ST_ZMax(geometry), "
        "ST_XMin(geometry), ST_YMax(geometry) FROM v WHERE id = 'b1'"
    ).fetchone()
    # cube LoD2 : 6 faces (verticales comprises), Z réel 100..105, translate appliqué
    assert row == ("b1", "2", '{"h": 5}', "MULTIPOLYGON", True, 6, 100.0, 105.0, 1000.0, 2010.0)
    conn.execute("DROP TABLE v")
    _read(r2.read_cityjson, conn, path=p, geometry="solid3d", lod="1")
    assert conn.execute("SELECT ST_NumGeometries(geometry) FROM v WHERE id='b1'").fetchone() == (2,)
    conn.execute("DROP TABLE v")
    # entrée dégénérée : erreur de ligne, pas d'échec du nœud
    _read(r2.read_cityjson, conn, geometry="solid3d",
          path=_city_doc(tmp_path / "d.json", [[[0, 1]]]))  # fmt: skip
    got = conn.execute("SELECT id, error, ST_AsText(geometry) FROM v ORDER BY id").fetchall()
    assert "3 sommets" in got[0][1] and got[0][2] is None
    assert got[1] == ("ok", None, "MULTIPOLYGON Z (((0 0 0, 1 0 0, 1 1 0, 0 1 0, 0 0 0)))")


# ------------------------------------------------------------------ Sentinel-2 / Landsat-8 produit

_MTD = """<?xml version="1.0"?>
<n1:Level-2A_User_Product xmlns:n1="https://psd-14.sentinel2.eo.esa.int/PSD/User_Product_Level-2A.xsd">
<n1:General_Info><Product_Info><PRODUCT_START_TIME>2024-06-01T10:30:00Z</PRODUCT_START_TIME>
<PRODUCT_TYPE>S2MSI2A</PRODUCT_TYPE><PROCESSING_BASELINE>05.10</PROCESSING_BASELINE>
<Datatake><SPACECRAFT_NAME>Sentinel-2A</SPACECRAFT_NAME></Datatake></Product_Info>
<Product_Image_Characteristics><QUANTIFICATION_VALUES_LIST>
<BOA_QUANTIFICATION_VALUE unit="none">10000</BOA_QUANTIFICATION_VALUE>
</QUANTIFICATION_VALUES_LIST><BOA_ADD_OFFSET_VALUES_LIST>
<BOA_ADD_OFFSET band_id="1">-1000</BOA_ADD_OFFSET><BOA_ADD_OFFSET band_id="3">-1000</BOA_ADD_OFFSET>
<BOA_ADD_OFFSET band_id="8">-1000</BOA_ADD_OFFSET>
</BOA_ADD_OFFSET_VALUES_LIST></Product_Image_Characteristics></n1:General_Info>
<n1:Quality_Indicators_Info><Cloud_Coverage_Assessment>12.5</Cloud_Coverage_Assessment>
</n1:Quality_Indicators_Info></n1:Level-2A_User_Product>"""


def _write(path, arr, res, driver="JP2OpenJPEG"):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    arr = np.asarray(arr, dtype="uint16")
    opts = {"REVERSIBLE": "YES", "QUALITY": "100"} if driver == "JP2OpenJPEG" else {}
    with rasterio.open(
        path, "w", driver=driver, width=arr.shape[1], height=arr.shape[0], count=1,
        dtype="uint16", crs="EPSG:32631", transform=from_origin(500000, 4000040, res, res), **opts,
    ) as d:  # fmt: skip
        d.write(arr, 1)


def _s2_product(tmp_path, mtd=True):
    import numpy as np

    root = tmp_path / "S2A_MSIL2A.SAFE"
    g = root / "GRANULE" / "L2A_T31" / "IMG_DATA"
    for r in ("R10m", "R20m"):
        (g / r).mkdir(parents=True)
    b04 = np.full((4, 4), 2000)
    b04[0, 0] = 0  # pas de donnée
    _write(g / "R10m" / "T31_B02_10m.jp2", np.full((4, 4), 1500), 10)
    _write(g / "R10m" / "T31_B04_10m.jp2", b04, 10)
    _write(g / "R20m" / "T31_B8A_20m.jp2", [[3000, 3000], [3000, 3000]], 20)
    _write(g / "R20m" / "T31_SCL_20m.jp2", [[4, 9], [4, 4]], 20)  # 9 = nuage haute proba
    if mtd:
        (root / "MTD_MSIL2A.xml").write_text(_MTD)
    return str(root)


def test_sentinel2_multiband_reflectance_scl_mask_metadata(tmp_path, conn):
    from app.pipelines.ops import readers2 as r2

    root = _s2_product(tmp_path)
    opts = {"reflectance": True, "maskScl": [9], "includeQuality": True, "includeMetadata": True}
    srid = _read(r2.read_sentinel2, conn, path=root, bands=["B02", "B04", "B8A"], **opts)
    assert srid == 32631
    cols = [r[0] for r in conn.execute("DESCRIBE v").fetchall()]
    assert cols == ["x", "y", "B02", "B04", "B8A", "scl", "metadata", "geometry"]
    rows = conn.execute("SELECT B02, B04, B8A, scl, metadata FROM v").fetchall()
    # 16 cellules - 1 DN 0 (B04) - 4 sous le pixel SCL nuageux (quart nord-est) = 11
    assert len(rows) == 11 and {r[3] for r in rows} == {4}
    # réflectance L2A = (DN + offset) / quantification ; B02 est band_id 1, B04 3, B8A 8
    assert {tuple(round(v, 9) for v in r[:3]) for r in rows} == {(0.05, 0.1, 0.2)}
    meta = json.loads(rows[0][4])
    assert meta == {
        "product_type": "S2MSI2A", "spacecraft": "Sentinel-2A", "processing_baseline": "05.10",
        "sensing_time": "2024-06-01T10:30:00Z", "cloud_cover": 12.5,
    }  # fmt: skip
    conn.execute("DROP TABLE v")
    # DN bruts sans option : colonnes nommées par bande, dtype entier conservé
    _read(r2.read_sentinel2, conn, path=root, bands=["B04"])
    assert conn.execute("SELECT count(*), min(B04), max(B04) FROM v").fetchone() == (15, 2000, 2000)
    conn.execute("DROP TABLE v")
    # ancien comportement (une bande, colonne value, DN 0 conservé) inchangé
    _read(r2.read_sentinel2, conn, path=root, band="B04")
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 16


def test_sentinel2_degenerate_inputs(tmp_path, conn, monkeypatch):
    from app.pipelines.ops import readers2 as r2

    root = _s2_product(tmp_path, mtd=False)
    with pytest.raises(PipelineRuntimeError, match="quantification"):
        _read(r2.read_sentinel2, conn, path=root, bands=["B04"], reflectance=True)
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_sentinel2, conn, path=root, bands=["B04", "B11"])
    with pytest.raises(PipelineRuntimeError, match="réflectance réservée"):
        _read(r2.read_sentinel2, conn, path=root, band="SCL", reflectance=True)
    for bad in ({"maskScl": [12]}, {"bands": ["B04", "B04"]}, {"bands": ["TCI"]}):
        with pytest.raises(ValidationError):
            _read(r2.read_sentinel2, conn, path=root, **bad)
    # emprise différente : bande décalée refusée (pas de rééchantillonnage silencieux)
    g = os.path.join(root, "GRANULE", "L2A_T31", "IMG_DATA", "R20m")
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
        os.path.join(g, "T31_B11_20m.jp2"), "w", driver="JP2OpenJPEG", width=2, height=2,
        count=1, dtype="uint16", crs="EPSG:32631", transform=from_origin(600000, 4000040, 20, 20),
    ) as d:  # fmt: skip
        d.write(np.ones((2, 2), dtype="uint16"), 1)
    with pytest.raises(PipelineRuntimeError, match="emprise"):
        _read(r2.read_sentinel2, conn, path=root, bands=["B04", "B11"])
    # MTD hostile (entité XML) : refusé par defusedxml, sans expansion
    (tmp_path / "S2A_MSIL2A.SAFE" / "MTD_MSIL2A.xml").write_text(
        '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>'
    )
    with pytest.raises(PipelineRuntimeError, match="MTD illisible"):
        _read(r2.read_sentinel2, conn, path=root, bands=["B04"], includeMetadata=True)
    # plafond cellules x couches
    monkeypatch.setattr(r2, "MAX_PRODUCT_LAYER_CELLS", 8)
    _read(r2.read_sentinel2, conn, path=root, bands=["B02", "B04"])
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] <= 4


_MTL = """GROUP = LANDSAT_METADATA_FILE
  GROUP = IMAGE_ATTRIBUTES
    SPACECRAFT_ID = "LANDSAT_8"
    DATE_ACQUIRED = 2024-06-01
    SCENE_CENTER_TIME = "10:30:00.0Z"
    CLOUD_COVER = 3.25
    SUN_ELEVATION = 30.0
  END_GROUP = IMAGE_ATTRIBUTES
  GROUP = PRODUCT_CONTENTS
    COLLECTION_NUMBER = 02
    PROCESSING_LEVEL = "L1TP"
  END_GROUP = PRODUCT_CONTENTS
  GROUP = LEVEL1_RADIOMETRIC_RESCALING
    REFLECTANCE_MULT_BAND_4 = 2.0000E-05
    REFLECTANCE_ADD_BAND_4 = -0.100000
    REFLECTANCE_MULT_BAND_5 = 2.0000E-05
    REFLECTANCE_ADD_BAND_5 = -0.100000
  END_GROUP = LEVEL1_RADIOMETRIC_RESCALING
END_GROUP = LANDSAT_METADATA_FILE
END
"""


def _l8_product(tmp_path, mtl=True):
    d = tmp_path / "LC08_L1TP_199029"
    d.mkdir()
    _write(d / "LC08_L1TP_199029_B4.TIF", [[10000, 10000], [10000, 0]], 30, "GTiff")
    _write(d / "LC08_L1TP_199029_B5.TIF", [[20000, 20000], [20000, 20000]], 30, "GTiff")
    _write(d / "LC08_L1TP_199029_B10.TIF", [[300, 300], [300, 300]], 30, "GTiff")
    # QA_PIXEL : bit 3 nuage sur la cellule (0, 1), bit 7 eau sur (1, 0)
    _write(d / "LC08_L1TP_199029_QA_PIXEL.TIF", [[0, 1 << 3], [1 << 7, 0]], 30, "GTiff")
    if mtl:
        (d / "LC08_L1TP_199029_MTL.txt").write_text(_MTL)
    return str(d)


def test_landsat8_multiband_toa_reflectance_qa_mask(tmp_path, conn):
    from app.pipelines.ops import readers2 as r2

    root = _l8_product(tmp_path)
    _read(r2.read_landsat8, conn, path=root, bands=[4, 5], reflectance=True, maskQa=["cloud"],
          includeQuality=True, includeMetadata=True)  # fmt: skip
    rows = conn.execute("SELECT B4, B5, qa_pixel, metadata FROM v ORDER BY y DESC, x").fetchall()
    # TOA = (M * DN + A) / sin(30°) ; (1,1) DN 0 écarté, (0,1) nuage écarté, eau gardée
    assert [(round(a, 6), round(b, 6), q) for a, b, q, _ in rows] == [
        (0.2, 0.6, 0), (0.2, 0.6, 128)
    ]  # fmt: skip
    assert json.loads(rows[0][3]) == {
        "spacecraft": "LANDSAT_8", "date_acquired": "2024-06-01", "cloud_cover": 3.25,
        "scene_center_time": "10:30:00.0Z", "processing_level": "L1TP", "collection": "02",
    }  # fmt: skip
    conn.execute("DROP TABLE v")
    _read(r2.read_landsat8, conn, path=root, bands=[4], maskQa=["cloud", "water"])
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 1
    with pytest.raises(PipelineRuntimeError, match="thermique"):
        _read(r2.read_landsat8, conn, path=root, bands=[10], reflectance=True)
    with pytest.raises(ValidationError):
        _read(r2.read_landsat8, conn, path=root, maskQa=["bogus"])


def test_landsat8_reflectance_without_mtl_and_qa_missing(tmp_path, conn):
    from app.pipelines.ops import readers2 as r2

    root = _l8_product(tmp_path, mtl=False)
    with pytest.raises(PipelineRuntimeError, match="MTL absent"):
        _read(r2.read_landsat8, conn, path=root, bands=[4], reflectance=True)
    os.remove(os.path.join(root, "LC08_L1TP_199029_QA_PIXEL.TIF"))
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_landsat8, conn, path=root, bands=[4], maskQa=["cloud"])


def test_sentinel2_raster_item_multiband(renv, tmp_path):
    import rasterio

    from app.pipelines.ops import readers2 as r2
    from app.raster.models import RasterAsset

    root = _s2_product(tmp_path)
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    kw = {"session": renv.s, "tenant_id": renv.tid, "node_id": "n", "view_name": "v",
          "base_uri": ""}  # fmt: skip
    params = {"path": root, "bands": ["B02", "B04", "B8A"], "reflectance": True,
              "maskScl": [9], "output": "rasterItem", "title": "S2"}  # fmt: skip
    r2.read_sentinel2(conn, user=renv.alice, params=params, **kw)
    item_id, w, h, n, srid, meta = conn.execute("SELECT * FROM v").fetchone()
    assert (w, h, n, srid) == (4, 4, 3, 32631) and json.loads(meta)["cloud_cover"] == 12.5
    asset = renv.s.get(RasterAsset, item_id)
    assert asset is not None
    with rasterio.open(renv.paths[asset.source_key]) as ds:
        assert ds.count == 3 and ds.dtypes[0] == "float32"
        b04 = ds.read(2)
    assert b04[1, 0] == pytest.approx(0.1) and b04[0, 0] != b04[0, 0]  # NaN = nodata
    assert b04[0, 3] != b04[0, 3]  # masqué par SCL
    from app.users.repository import set_user_role

    set_user_role(renv.s, tenant_id=renv.tid, user_id=renv.bob.id,
                  role_id=renv.roles["reader"].id, role_slug="reader")  # fmt: skip
    conn.execute("DROP TABLE v")
    with pytest.raises(PipelineRuntimeError, match="catalog.manage"):
        r2.read_sentinel2(conn, user=renv.bob, params=params, **kw)
