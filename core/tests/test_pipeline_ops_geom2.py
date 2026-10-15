# SPDX-License-Identifier: Apache-2.0
"""Voie C (FME) : 15 transformers géométrie. Parité contre Shapely direct sur des géométries
pièges + entrées dégénérées (vide, NULL, multi, anneau inversé) + bornes."""

import duckdb
import pytest
import shapely
import shapely.affinity
import shapely.wkt

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import geom2
from app.pipelines.ops.contracts import OPERATIONS
from app.pipelines.ops.operation_contract import OperationContract

OPS = {
    "transform.triangulatePolygon",
    "transform.removeVertices",
    "transform.removeSpikes",
    "transform.cleanAreaGapsOverlaps",
    "transform.amalgamateAreas",
    "transform.buildAreas",
    "transform.intersector",
    "transform.lineOnAreaOverlayer",
    "transform.combineLines",
    "transform.extractDonutHoles",
    "transform.chop",
    "transform.coerceGeometry",
    "transform.affineWarp",
    "transform.rubberSheet",
    "transform.convertCrsDescription",
}

# Pièges : trou, multi, anneau inversé (CW), polygone vide, avec Z, bow-tie invalide, ...
SQUARE = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"
DONUT = (
    "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 2 4, 4 4, 4 2, 2 2), (6 6, 6 8, 8 8, 8 6, 6 6))"
)
CW_SQUARE = "POLYGON ((0 0, 0 10, 10 10, 10 0, 0 0))"
MULTI = "MULTIPOLYGON (((0 0, 4 0, 4 4, 0 4, 0 0)), ((6 6, 9 6, 9 9, 6 9, 6 6)))"
CONCAVE = "POLYGON ((0 0, 10 0, 10 10, 5 2, 0 10, 0 0))"
POLYGONS = [SQUARE, DONUT, CW_SQUARE, MULTI, CONCAVE]


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial; SET memory_limit='768MB'; SET threads=2")
    return c


def table(conn, wkts, name="src"):
    conn.execute(f"CREATE OR REPLACE TABLE {name} (id INTEGER, geometry GEOMETRY)")
    for i, w in enumerate(wkts):
        g = "NULL" if w is None else f"ST_GeomFromText('{w}')"
        conn.execute(f"INSERT INTO {name} VALUES ({i}, {g})")


def run(conn, op, params, wkts, name="src"):
    table(conn, wkts, name)
    conn.execute("DROP TABLE IF EXISTS out")
    OPERATIONS[op].execute(conn, input_view=name, view_name="out", params=params)
    return conn.execute("SELECT * EXCLUDE geometry, ST_AsText(geometry) FROM out").fetchall()


def geoms(rows):
    return [shapely.wkt.loads(r[-1]) for r in rows]


def test_contracts_declared_and_shapely_licence():
    assert {c.op for c in geom2.CONTRACTS} == OPS
    for c in geom2.CONTRACTS:
        assert isinstance(c, OperationContract) and c.execute is not None
        assert c.op in OPERATIONS
        if c.engine == "shapely":
            assert c.engine_license == "BSD-3-Clause (Shapely)"


def test_catalog_exposes_ops():
    from app.pipelines.ops.contracts import ops_catalog

    assert OPS <= set(ops_catalog())


# ---- parité vs Shapely direct -----------------------------------------------------


@pytest.mark.parametrize("wkt", POLYGONS)
def test_triangulate_polygon_parity(conn, wkt):
    ref = shapely.wkt.loads(wkt)
    out = geoms(run(conn, "transform.triangulatePolygon", {}, [wkt]))
    assert all(t.geom_type == "Polygon" and len(t.exterior.coords) == 4 for t in out)
    assert sum(t.area for t in out) == pytest.approx(ref.area)
    assert shapely.union_all(out).symmetric_difference(ref).area == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("wkt", POLYGONS)
def test_extract_donut_holes_parity(conn, wkt):
    ref = [Polygon_(r) for p in shapely.get_parts(shapely.wkt.loads(wkt)) for r in p.interiors]
    out = geoms(run(conn, "transform.extractDonutHoles", {}, [wkt]))
    assert sorted(g.wkt for g in out) == sorted(g.wkt for g in ref)


def Polygon_(r):
    return shapely.Polygon(r)


@pytest.mark.parametrize("wkt", POLYGONS)
def test_coerce_polygon_to_line_is_boundary(conn, wkt):
    out = geoms(run(conn, "transform.coerceGeometry", {"target": "line"}, [wkt]))
    ref = shapely.boundary(shapely.wkt.loads(wkt))
    assert shapely.union_all(out).equals(shapely.union_all(shapely.get_parts(ref)))


def test_coerce_closed_line_to_area_and_multi_and_failures(conn):
    out = run(
        conn, "transform.coerceGeometry", {"target": "area"}, ["LINESTRING (0 0, 4 0, 4 4, 0 0)"]
    )
    assert out[0][-1].startswith("POLYGON")
    out = run(
        conn,
        "transform.coerceGeometry",
        {"target": "multi"},
        ["GEOMETRYCOLLECTION (POLYGON ((0 0, 1 0, 1 1, 0 0)), POLYGON ((5 5, 6 5, 6 6, 5 5)))"],
    )
    assert out[0][-1].startswith("MULTIPOLYGON")
    with pytest.raises(PipelineRuntimeError, match="non fermée"):
        run(conn, "transform.coerceGeometry", {"target": "area"}, ["LINESTRING (0 0, 4 0)"])
    out = run(
        conn,
        "transform.coerceGeometry",
        {"target": "area", "onUnconvertible": "null"},
        ["LINESTRING (0 0, 4 0)", "POINT EMPTY"],
    )
    assert [r[-1] for r in out] == [None, None]


def test_combine_lines_parity(conn):
    wkts = [
        "LINESTRING (0 0, 1 0)",
        "LINESTRING (1 0, 2 0)",
        "LINESTRING (2 0, 2 5)",
        "LINESTRING (9 9, 8 8)",
    ]
    out = geoms(run(conn, "transform.combineLines", {}, wkts))
    ref = shapely.line_merge(shapely.union_all([shapely.wkt.loads(w) for w in wkts]))
    assert sorted(g.wkt for g in out) == sorted(g.wkt for g in shapely.get_parts(ref))
    assert len(out) == 2


def test_build_areas_parity_with_island(conn):
    wkts = [
        "LINESTRING (0 0, 10 0, 10 10, 0 10, 0 0)",
        "LINESTRING (3 3, 6 3, 6 6, 3 6, 3 3)",
        "LINESTRING (20 20, 25 25)",  # pendante
    ]
    out = geoms(run(conn, "transform.buildAreas", {}, wkts))
    ref = shapely.get_parts(
        shapely.polygonize([shapely.union_all([shapely.wkt.loads(w) for w in wkts])])
    )
    assert (
        sorted(round(g.area, 6) for g in out)
        == sorted(round(g.area, 6) for g in ref)
        == [9.0, 91.0]
    )


def test_build_areas_crossing_lines_are_noded(conn):
    wkts = [
        "LINESTRING (0 5, 10 5)",
        "LINESTRING (5 0, 5 10)",
        "LINESTRING (0 0, 10 0, 10 10, 0 10, 0 0)",
    ]
    out = geoms(run(conn, "transform.buildAreas", {}, wkts))
    assert len(out) == 4


@pytest.mark.parametrize("mode", ["remove", "keep"])
def test_remove_vertices_parity(conn, mode):
    line = "LINESTRING (0 0, 1 1, 2 0, 3 1, 4 0)"
    out = geoms(run(conn, "transform.removeVertices", {"indices": [1, -2], "mode": mode}, [line]))
    c = list(shapely.wkt.loads(line).coords)
    keepers = [c[i] for i in range(5) if (i not in (1, 3)) == (mode == "remove")]
    assert list(out[0].coords) == keepers


def test_remove_vertices_ring_and_degenerate(conn):
    out = geoms(
        run(
            conn,
            "transform.removeVertices",
            {"indices": [0]},
            [SQUARE, "LINESTRING (0 0, 1 1)", "POINT EMPTY"],
        )
    )
    assert out[0].wkt == "POLYGON ((10 0, 10 10, 0 10, 10 0))"
    assert out[1].is_empty and out[2].is_empty
    out = geoms(run(conn, "transform.removeVertices", {"indices": [0, 1]}, [SQUARE]))
    assert out[0].is_empty


def test_remove_spikes(conn):
    out = geoms(
        run(
            conn,
            "transform.removeSpikes",
            {"angleThreshold": 10},
            ["LINESTRING (0 0, 5 0, 5 0, 10 0.01, 5 0.0001, 11 0)"],
        )
    )
    assert list(out[0].coords) == [(0, 0), (5, 0), (11, 0)]
    # un carré n'a pas de pic ; anneau inversé idem
    for w in (SQUARE, CW_SQUARE):
        assert geoms(run(conn, "transform.removeSpikes", {}, [w]))[0].equals(shapely.wkt.loads(w))
    # pic de polygone
    spiky = "POLYGON ((0 0, 10 0, 10 5, 20 5, 10 5.001, 10 10, 0 10, 0 0))"
    res = geoms(run(conn, "transform.removeSpikes", {"angleThreshold": 5}, [spiky]))[0]
    assert res.bounds[2] == 10 and res.is_valid


def test_chop_lines_and_areas(conn):
    line = shapely.wkt.loads("LINESTRING (0 0, 1 0, 2 0, 3 0, 4 0, 5 0, 6 0)")
    out = geoms(run(conn, "transform.chop", {"maxVertices": 4}, [line.wkt]))
    assert all(len(g.coords) <= 4 for g in out)
    assert shapely.line_merge(shapely.union_all(out)).equals(line)
    out = geoms(run(conn, "transform.chop", {"maxLength": 2.5}, [line.wkt]))
    assert all(g.length <= 2.5 + 1e-9 for g in out) and sum(g.length for g in out) == pytest.approx(
        6
    )
    for w in (SQUARE, MULTI, CONCAVE, CW_SQUARE):
        ref = shapely.wkt.loads(w)
        out = geoms(run(conn, "transform.chop", {"maxVertices": 6}, [w]))
        assert all(shapely.get_num_coordinates(g) <= 6 for g in out)
        assert sum(g.area for g in out) == pytest.approx(ref.area)
    ref = shapely.wkt.loads(DONUT)
    out = geoms(run(conn, "transform.chop", {"maxVertices": 10}, [DONUT]))
    assert all(shapely.get_num_coordinates(g) <= 10 for g in out)
    assert sum(g.area for g in out) == pytest.approx(ref.area)
    with pytest.raises(PipelineRuntimeError, match="impossible de descendre"):
        run(conn, "transform.chop", {"maxVertices": 4}, [DONUT])
    with pytest.raises(PipelineRuntimeError, match="maxLength"):
        run(conn, "transform.chop", {"maxLength": 1}, [SQUARE])


def test_clean_overlaps_and_gaps(conn):
    a = "POLYGON ((0 0, 5 0, 5 5, 0 5, 0 0))"
    b = "POLYGON ((4 0, 10 0, 10 5, 4 5, 4 0))"  # chevauche a de 1
    c = "POLYGON ((0 5, 10 5, 10 6, 6 6, 6 5.5, 4 5.5, 4 6, 0 6, 0 5))"
    rows = run(conn, "transform.cleanAreaGapsOverlaps", {"maxGapArea": 100}, [a, b, c])
    out = geoms(rows)
    assert shapely.coverage_is_valid(out).all()
    assert sum(g.area for g in out) == pytest.approx(
        shapely.union_all([shapely.wkt.loads(w) for w in (a, b, c)]).area
    )
    # interstice enclos : trou comblé
    ring = [
        "POLYGON ((0 0, 10 0, 10 3, 0 3, 0 0))",
        "POLYGON ((0 7, 10 7, 10 10, 0 10, 0 7))",
        "POLYGON ((0 3, 4 3, 4 7, 0 7, 0 3))",
        "POLYGON ((6 3, 10 3, 10 7, 6 7, 6 3))",
    ]
    out = geoms(run(conn, "transform.cleanAreaGapsOverlaps", {"maxGapArea": 100}, ring))
    assert sum(g.area for g in out) == pytest.approx(100)
    out = geoms(run(conn, "transform.cleanAreaGapsOverlaps", {"maxGapArea": 1}, ring))
    assert sum(g.area for g in out) == pytest.approx(92)  # trou 2x4 > maxGapArea
    # gap ouvert fermé par gapTolerance
    left = "POLYGON ((0 0, 4.9 0, 4.9 5, 0 5, 0 0))"
    right = "POLYGON ((5.1 0, 10 0, 10 5, 5.1 5, 5.1 0))"
    out = geoms(
        run(
            conn,
            "transform.cleanAreaGapsOverlaps",
            {"maxGapArea": 5, "gapTolerance": 0.5},
            [left, right],
        )
    )
    assert sum(g.area for g in out) == pytest.approx(50)


def test_amalgamate(conn):
    wkts = [
        "POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))",
        "POLYGON ((4.5 0, 8 0, 8 4, 4.5 4, 4.5 0))",
        "POLYGON ((50 50, 51 50, 51 51, 50 51, 50 50))",
    ]
    assert len(geoms(run(conn, "transform.amalgamateAreas", {}, wkts))) == 3
    out = geoms(run(conn, "transform.amalgamateAreas", {"distance": 1}, wkts))
    assert len(out) == 2 and max(g.area for g in out) >= 32 - 1e-6
    out = geoms(run(conn, "transform.amalgamateAreas", {"fillHolesBelowArea": 5}, [DONUT]))
    assert len(out[0].interiors) == 0


def test_intersector_lines_and_areas(conn):
    rows = run(
        conn,
        "transform.intersector",
        {},
        ["LINESTRING (0 5, 10 5)", "LINESTRING (5 0, 5 10)", "LINESTRING (20 0, 21 0)"],
    )
    assert (
        [r[0] for r in rows].count(0) == 2
        and [r[0] for r in rows].count(1) == 2
        and [r[0] for r in rows].count(2) == 1
    )
    rows = run(
        conn,
        "transform.intersector",
        {},
        ["POLYGON ((0 0, 6 0, 6 6, 0 6, 0 0))", "POLYGON ((3 3, 9 3, 9 9, 3 9, 3 3))"],
    )
    areas = sorted((r[0], round(shapely.wkt.loads(r[-1]).area, 6)) for r in rows)
    assert areas == [(0, 9.0), (0, 27.0), (1, 9.0), (1, 27.0)]
    with pytest.raises(PipelineRuntimeError, match="ne se mélangent pas"):
        run(conn, "transform.intersector", {}, ["LINESTRING (0 0, 1 1)", SQUARE])


def test_line_on_area_overlayer(conn):
    rows = run(conn, "transform.lineOnAreaOverlayer", {}, [SQUARE, "LINESTRING (-5 5, 15 5)"])
    parts = sorted((r[1], round(shapely.wkt.loads(r[-1]).length, 6)) for r in rows)
    assert parts == [(False, 5.0), (False, 5.0), (True, 10.0)]
    rows = run(
        conn,
        "transform.lineOnAreaOverlayer",
        {"mode": "splitAreas"},
        [SQUARE, "LINESTRING (-5 5, 15 5)", "POLYGON ((50 50, 51 50, 51 51, 50 50))"],
    )
    assert sorted(round(shapely.wkt.loads(r[-1]).area, 6) for r in rows) == [0.5, 50.0, 50.0]


def test_affine_warp_parity_and_degenerate(conn):
    ref = shapely.affinity.affine_transform(shapely.wkt.loads(SQUARE), [2, -0.5, 0.5, 3, 10, -4])
    ctl = [
        {"source": [x, y], "target": [2 * x - 0.5 * y + 10, 0.5 * x + 3 * y - 4]}
        for x, y in [(0, 0), (10, 0), (0, 10), (7, 3)]
    ]
    out = geoms(
        run(
            conn,
            "transform.affineWarp",
            {"controlVectors": ctl},
            [SQUARE, "POINT EMPTY", "POINT Z (1 1 7)"],
        )
    )
    assert out[0].equals_exact(ref, 1e-9)
    assert out[1].is_empty and out[2].z == 7
    flat = [{"source": [i, i], "target": [i, i]} for i in range(3)]
    with pytest.raises(PipelineRuntimeError, match="alignés"):
        run(conn, "transform.affineWarp", {"controlVectors": flat}, [SQUARE])


def test_rubber_sheet_exact_at_controls_and_fades(conn):
    ctl = [{"source": [0, 0], "target": [1, 1]}, {"source": [100, 0], "target": [100, 0]}]
    out = geoms(
        run(
            conn,
            "transform.rubberSheet",
            {"controlVectors": ctl},
            ["POINT (0 0)", "POINT (100 0)", "POINT (50 0)", "LINESTRING EMPTY"],
        )
    )
    assert (out[0].x, out[0].y) == (1, 1) and (out[1].x, out[1].y) == (100, 0)
    assert out[2].x == pytest.approx(50.5) and out[2].y == pytest.approx(0.5)
    assert out[3].is_empty


def test_convert_crs_description(conn):
    conn.execute("CREATE TABLE c (id INTEGER, geometry GEOMETRY, d VARCHAR)")
    conn.execute(
        "INSERT INTO c VALUES (1, ST_Point(0,0), 'EPSG:4326'), (2, NULL, '2154'), "
        "(3, NULL, 'n importe quoi'), (4, NULL, NULL)"
    )
    OPERATIONS["transform.convertCrsDescription"].execute(
        conn,
        input_view="c",
        view_name="o",
        params={"sourceColumn": "d", "targetFormat": "epsg", "outputColumn": "e"},
    )
    assert conn.execute("SELECT e FROM o ORDER BY id").fetchall() == [
        ("EPSG:4326",),
        ("EPSG:2154",),
        (None,),
        (None,),
    ]
    OPERATIONS["transform.convertCrsDescription"].execute(
        conn,
        input_view="c",
        view_name="o2",
        params={"sourceColumn": "d", "targetFormat": "wkt", "outputColumn": "d"},
    )
    assert "Lambert" in conn.execute("SELECT d FROM o2 WHERE id = 2").fetchone()[0]
    assert conn.execute("SELECT ST_AsText(geometry) FROM o2 WHERE id = 1").fetchone() == (
        "POINT (0 0)",
    )
    with pytest.raises(PipelineRuntimeError, match="introuvable"):
        OPERATIONS["transform.convertCrsDescription"].execute(
            conn, input_view="c", view_name="o3", params={"sourceColumn": "x"}
        )


# ---- entrées dégénérées communes, bornes -------------------------------------------

GEOM_OPS = {
    "transform.triangulatePolygon": {},
    "transform.removeVertices": {"indices": [0]},
    "transform.removeSpikes": {},
    "transform.cleanAreaGapsOverlaps": {"maxGapArea": 1},
    "transform.amalgamateAreas": {},
    "transform.buildAreas": {},
    "transform.intersector": {},
    "transform.lineOnAreaOverlayer": {},
    "transform.combineLines": {},
    "transform.extractDonutHoles": {},
    "transform.chop": {"maxVertices": 4},
    "transform.coerceGeometry": {"target": "multi"},
    "transform.affineWarp": {
        "controlVectors": [
            {"source": [0, 0], "target": [0, 0]},
            {"source": [1, 0], "target": [1, 0]},
            {"source": [0, 1], "target": [0, 1]},
        ]
    },
    "transform.rubberSheet": {"controlVectors": [{"source": [0, 0], "target": [0, 0]}]},
}


@pytest.mark.parametrize("op", sorted(GEOM_OPS))
def test_empty_and_all_null_input_yield_zero_rows_without_crash(conn, op):
    for wkts in ([], [None, None]):
        table(conn, wkts)
        conn.execute("DROP TABLE IF EXISTS o")
        OPERATIONS[op].execute(conn, input_view="src", view_name="o", params=GEOM_OPS[op])
        assert conn.execute("SELECT count(*) FROM o").fetchone() == (0,)


def test_missing_geometry_column_is_an_error(conn):
    conn.execute("CREATE TABLE ng (id INTEGER)")
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        OPERATIONS["transform.chop"].execute(
            conn, input_view="ng", view_name="o", params={"maxVertices": 4}
        )


def test_wrong_geometry_family_is_a_clear_error(conn):
    with pytest.raises(PipelineRuntimeError, match="types de géométrie attendus"):
        run(conn, "transform.triangulatePolygon", {}, ["POINT (1 1)"])


def test_bounds_features_vertices_and_timeout(conn, monkeypatch):
    monkeypatch.setattr(geom2, "MAX_FEATURES", 2)
    with pytest.raises(PipelineRuntimeError, match="trop d'entités"):
        run(conn, "transform.buildAreas", {}, ["LINESTRING (0 0, 1 1)"] * 3)
    monkeypatch.setattr(geom2, "MAX_VERTICES", 3)
    with pytest.raises(PipelineRuntimeError, match="trop de sommets"):
        run(conn, "transform.removeSpikes", {}, ["LINESTRING (0 0, 1 1, 2 0, 3 1)"])
    monkeypatch.setattr(geom2, "MAX_VERTICES", 10**6)
    monkeypatch.setattr(geom2, "TIMEOUT_S", -1.0)
    with pytest.raises(PipelineRuntimeError, match="délai dépassé"):
        run(conn, "transform.intersector", {}, ["LINESTRING (0 0, 1 1)", "LINESTRING (0 1, 1 0)"])


def test_group_by(conn):
    conn.execute("CREATE TABLE g (id INTEGER, k VARCHAR, geometry GEOMETRY)")
    for i, k, w in [(1, "a", "0 0, 1 0"), (2, "a", "1 0, 2 0"), (3, "b", "2 0, 3 0")]:
        conn.execute(f"INSERT INTO g VALUES ({i}, '{k}', ST_GeomFromText('LINESTRING ({w})'))")
    OPERATIONS["transform.combineLines"].execute(
        conn, input_view="g", view_name="o", params={"groupBy": ["k"]}
    )
    assert conn.execute("SELECT k, ST_NPoints(geometry) FROM o ORDER BY k").fetchall() == [
        ("a", 3),
        ("b", 2),
    ]
    with pytest.raises(PipelineRuntimeError, match="not found"):
        OPERATIONS["transform.combineLines"].execute(
            conn, input_view="g", view_name="o2", params={"groupBy": ["zz"]}
        )


def test_params_are_strict():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OPERATIONS["transform.chop"].params_schema.model_validate({})
    with pytest.raises(ValidationError):
        OPERATIONS["transform.removeVertices"].params_schema.model_validate(
            {"indices": [1], "x": 1}
        )


# ---- revue : bornes de sortie, mémoire, validité, CRS ------------------------------


def test_chop_max_length_piece_cap(conn):
    with pytest.raises(PipelineRuntimeError, match="morceaux"):
        run(conn, "transform.chop", {"maxLength": 1e-9}, ["LINESTRING (0 0, 1000 0)"])


def test_rubber_sheet_is_chunked_and_identical(conn, monkeypatch):
    ctl = [{"source": [0, 0], "target": [1, 2]}, {"source": [9, 9], "target": [9, 10]}]
    w = ["LINESTRING (0 0, 3 4, 5 5, 9 9, 20 1)"]
    ref = run(conn, "transform.rubberSheet", {"controlVectors": ctl}, w)
    monkeypatch.setattr(geom2, "RUBBER_CHUNK", 2)  # 1 sommet par bloc
    assert run(conn, "transform.rubberSheet", {"controlVectors": ctl}, w) == ref


def test_output_cap_and_intersector_polygon_bound(conn, monkeypatch):
    monkeypatch.setattr(geom2, "MAX_OUTPUT_ROWS", 3)
    grid = [f"LINESTRING ({i} -1, {i} 10)" for i in range(4)] + [
        f"LINESTRING (-1 {i}, 10 {i})" for i in range(4)
    ]
    with pytest.raises(PipelineRuntimeError, match="sortie trop volumineuse"):
        run(conn, "transform.intersector", {}, grid)
    monkeypatch.setattr(geom2, "MAX_OUTPUT_ROWS", 2)
    with pytest.raises(PipelineRuntimeError, match="sortie trop volumineuse"):
        run(conn, "transform.triangulatePolygon", {}, [CONCAVE])
    monkeypatch.setattr(geom2, "MAX_OUTPUT_ROWS", 1_000_000)
    monkeypatch.setattr(geom2, "MAX_AREA_FEATURES", 1)
    with pytest.raises(PipelineRuntimeError, match="trop de polygones"):
        run(conn, "transform.intersector", {}, [SQUARE, CONCAVE])


def test_vertex_removal_repairs_invalid_polygon(conn):
    # retirer le sommet 2 d'un hexagone en "papillon" : résultat valide exigé
    w = "POLYGON ((0 0, 4 0, 4 4, 2 1, 0 4, 0 0))"
    out = geoms(run(conn, "transform.removeVertices", {"indices": [1, 4]}, [w]))
    assert out[0].is_valid
    bow = "POLYGON ((0 0, 4 4, 4 0, 0 4, 0 0))"
    out = geoms(run(conn, "transform.removeSpikes", {"angleThreshold": 1}, [bow]))
    assert out[0].is_valid


def test_convert_crs_rejects_geometry_column_and_init(conn):
    from pydantic import ValidationError

    schema = OPERATIONS["transform.convertCrsDescription"].params_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"sourceColumn": "d", "outputColumn": "geometry"})
    conn.execute("CREATE TABLE ci (d VARCHAR)")
    conn.execute("INSERT INTO ci VALUES ('+init=epsg:4326'), ('EPSG:4326')")
    OPERATIONS["transform.convertCrsDescription"].execute(
        conn, input_view="ci", view_name="co", params={"sourceColumn": "d", "targetFormat": "epsg"}
    )
    assert conn.execute("SELECT crs_converted FROM co ORDER BY d").fetchall() == [
        (None,),
        ("EPSG:4326",),
    ]
    # la table temporaire de mapping est désenregistrée même en cas d'échec
    with pytest.raises(duckdb.Error):
        OPERATIONS["transform.convertCrsDescription"].execute(
            conn, input_view="ci", view_name="co", params={"sourceColumn": "d"}
        )
    OPERATIONS["transform.convertCrsDescription"].execute(
        conn, input_view="ci", view_name="co2", params={"sourceColumn": "d"}
    )


# --- Revue finale FME, I5 : géométries 3D (voie S) face aux ops 2D ------------------------

CUBE_Z = (
    "MULTIPOLYGON Z (((0 0 0, 1 0 0, 1 1 0, 0 1 0, 0 0 0)), ((0 0 1, 1 0 1, 1 1 1, 0 1 1, 0 0 1)),"
    " ((0 0 0, 1 0 0, 1 0 1, 0 0 1, 0 0 0)), ((1 0 0, 1 1 0, 1 1 1, 1 0 1, 1 0 0)),"
    " ((1 1 0, 0 1 0, 0 1 1, 1 1 1, 1 1 0)), ((0 1 0, 0 0 0, 0 0 1, 0 1 1, 0 1 0)))"
)


@pytest.mark.parametrize(
    "op, params",
    [
        ("transform.removeSpikes", {}),
        ("transform.removeVertices", {"indices": [99]}),
        ("transform.chop", {"maxVertices": 4}),
        ("transform.cleanAreaGapsOverlaps", {"maxGapArea": 1}),
        ("transform.amalgamateAreas", {}),
    ],
)
def test_3d_solid_is_refused_never_silently_flattened(conn, op, params):
    with pytest.raises(PipelineRuntimeError, match="3D"):
        run(conn, op, params, [CUBE_Z])


def test_remove_spikes_keeps_vertical_edges_of_a_3d_line(conn):
    w = "LINESTRING Z (0 0 0, 0 0 5, 5 0 5, 10 0.01 5, 5 0.0001 5, 11 0 5)"
    out = geoms(run(conn, "transform.removeSpikes", {"angleThreshold": 5}, [w]))[0]
    assert out.has_z
    assert list(out.coords) == [(0, 0, 0), (0, 0, 5), (5, 0, 5), (11, 0, 5)]


def test_planar_3d_polygon_still_processed_with_z(conn):
    w = "POLYGON Z ((0 0 7, 4 0 7, 4 4 7, 0 4 7, 0 0 7))"
    out = geoms(run(conn, "transform.removeVertices", {"indices": [99]}, [w]))[0]
    assert out.has_z and {c[2] for c in out.exterior.coords} == {7}
