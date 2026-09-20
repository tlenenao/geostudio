# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines import compiler
from app.pipelines.compiler import compile_transform_sql, predecessor_id, topological_order


def _node(id_, kind, op, **params) -> PipelineNode:
    return PipelineNode(id=id_, kind=kind, op=op, params=params)


def _edge(id_, from_, to) -> PipelineEdge:
    return PipelineEdge(id=id_, **{"from": from_}, to=to)


def test_topological_order_linear_chain():
    nodes = [
        _node("w1", "writer", "writer.collection", collectionId="out"),
        _node("r1", "reader", "reader.collection", collectionId="in"),
        _node("t1", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "r1", "t1"), _edge("e2", "t1", "w1")]
    ordered_ids = [n.id for n in topological_order(nodes, edges)]
    assert ordered_ids == ["r1", "t1", "w1"]


def test_topological_order_raises_on_cycle():
    nodes = [
        _node("a", "transform", "transform.filter", expr="1=1"),
        _node("b", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "a")]
    with pytest.raises(ValueError, match="acyclic"):
        topological_order(nodes, edges)


def test_predecessor_id_returns_single_upstream():
    edges = [_edge("e1", "r1", "t1")]
    assert predecessor_id("t1", edges) == "r1"


def test_predecessor_id_returns_none_when_no_incoming_edge():
    assert predecessor_id("r1", []) is None


def test_predecessor_id_raises_on_multiple_incoming_edges():
    edges = [_edge("e1", "r1", "w1"), _edge("e2", "r2", "w1")]
    with pytest.raises(ValueError, match="one incoming edge"):
        predecessor_id("w1", edges)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE base (id INTEGER, region VARCHAR, pop INTEGER)")
    c.execute("INSERT INTO base VALUES (1, 'Nord', 10), (2, 'Sud', 5), (3, 'Nord', 20)")
    return c


def test_compile_filter(conn):
    sql = compile_transform_sql("transform.filter", {"expr": "pop > 8"}, input_view="base")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id FROM out ORDER BY id").fetchall()
    assert rows == [(1,), (3,)]


def test_compile_select_with_rename(conn):
    sql = compile_transform_sql(
        "transform.select",
        {"columns": {"region": "zone", "pop": None}},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["zone", "pop"]


def test_compile_derive(conn):
    sql = compile_transform_sql(
        "transform.derive",
        {"column": "pop_double", "expr": "pop * 2"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn.execute("SELECT pop_double FROM out WHERE id = 1").fetchone()
    assert row == (20,)


def test_compile_aggregate(conn):
    sql = compile_transform_sql(
        "transform.aggregate",
        {"groupBy": ["region"], "metrics": {"total_pop": "SUM(pop)"}},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn.execute("SELECT region, total_pop FROM out").fetchall())
    assert rows == {"Nord": 30, "Sud": 5}


def test_compile_join(conn):
    conn.execute("CREATE TABLE other (id INTEGER, label VARCHAR)")
    conn.execute("INSERT INTO other VALUES (1, 'A'), (2, 'B')")
    sql = compile_transform_sql(
        "transform.join",
        {"withCollectionId": "x", "on": "id", "how": "inner"},
        input_view="base",
        join_view="other",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, label FROM out ORDER BY id").fetchall()
    assert rows == [(1, "A"), (2, "B")]


def test_compile_join_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql(
            "transform.join",
            {"withCollectionId": "x", "on": "id"},
            input_view="base",
        )


def test_compile_unknown_transform_op_raises():
    with pytest.raises(ValueError, match="not a transform op"):
        compile_transform_sql("reader.collection", {"collectionId": "x"}, input_view="base")


def test_compile_bulk_remove_attributes(conn):
    sql = compile_transform_sql(
        "transform.bulkRemoveAttributes",
        {"pattern": "^pop$"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["id", "region"]


def test_compile_bulk_rename_attributes(conn):
    sql = compile_transform_sql(
        "transform.bulkRenameAttributes",
        {"pattern": "^(pop)$", "replacement": r"\1_count"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert sorted(cols) == ["id", "pop_count", "region"]


def test_compile_bulk_rename_attributes_escapes_single_quotes(conn):
    sql = compile_transform_sql(
        "transform.bulkRenameAttributes",
        {"pattern": "^(pop)$", "replacement": "it's_\\1"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert "it's_pop" in cols


@pytest.fixture()
def conn_spatial():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("INSTALL h3 FROM community; LOAD h3;")
    c.execute("CREATE TABLE base (id INTEGER, geometry GEOMETRY)")
    c.execute("INSERT INTO base VALUES (1, ST_Point(3.0, 45.0)), (2, ST_Point(3.001, 45.0))")
    return c


def test_compile_buffer_native_unit(conn_spatial):
    sql = compile_transform_sql(
        "transform.buffer",
        {"distance": 1, "unit": "native"},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_GeometryType(geometry) FROM out WHERE id = 1").fetchone()
    assert row == ("POLYGON",)


def test_compile_buffer_meters_unit_uses_correct_axis_order(conn_spatial):
    # Régression : sans always_xy=true dans les deux ST_Transform internes,
    # DuckDB spatial applique l'ordre d'axe EPSG (lat,lng) et le buffer sort
    # décalé de plusieurs milliers de km — vérifié empiriquement (cf. plan
    # Global Constraints). Un point à ~333 m au nord doit être DANS un buffer
    # de 500 m ; un point à ~111 km doit être EN DEHORS.
    sql = compile_transform_sql(
        "transform.buffer",
        {"distance": 500, "unit": "meters"},
        input_view="base",
        input_srid=4326,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    near, far = conn_spatial.execute(
        "SELECT ST_Contains(geometry, ST_Point(3.0, 45.003)), "
        "ST_Contains(geometry, ST_Point(3.0, 46.0)) FROM out WHERE id = 1"
    ).fetchone()
    assert near is True
    assert far is False


def test_compile_reproject_uses_correct_axis_order(conn_spatial):
    sql = compile_transform_sql(
        "transform.reproject",
        {"targetCrs": "EPSG:3857"},
        input_view="base",
        input_srid=4326,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert x == pytest.approx(333958.47, abs=1)
    assert y == pytest.approx(5621521.49, abs=1)


def test_compile_intersection_default_keeps_left_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.intersection",
        {"withCollectionId": "x"},
        input_view="base",
        join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT id FROM out ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]  # both points fall inside the 1-unit buffer


def test_compile_intersection_output_geometry_intersection(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.intersection",
        {"withCollectionId": "x", "outputGeometry": "intersection"},
        input_view="base",
        join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    types = conn_spatial.execute("SELECT ST_GeometryType(geometry) FROM out").fetchall()
    assert all(t == ("POINT",) for t in types)  # point ∩ polygon == point


def test_compile_count_within_intersects_default(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.countWithin",
        {"withCollectionId": "x"},
        input_view="base",
        join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn_spatial.execute("SELECT id, count FROM out").fetchall())
    assert rows == {1: 1, 2: 1}


def test_compile_count_within_custom_column_and_contains_predicate(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 0.0001))")
    sql = compile_transform_sql(
        "transform.countWithin",
        {"withCollectionId": "x", "countColumn": "n", "predicate": "contains"},
        input_view="base",
        join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn_spatial.execute("SELECT id, n FROM out").fetchall())
    assert rows[1] == 1  # id=1 is exactly the buffer's center, contained
    assert rows[2] == 0  # id=2 is ~111m away, outside a ~11m buffer


def test_compile_h3_aggregate_groups_nearby_points(conn_spatial):
    sql = compile_transform_sql(
        "transform.h3Aggregate",
        {"resolution": 9, "metrics": {"n": "COUNT(*)"}},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT h3Cell, n FROM out").fetchall()
    assert len(rows) == 1  # both points fall in the same res-9 cell
    assert rows[0][1] == 2


def test_compile_h3_aggregate_with_no_metrics_has_no_trailing_comma(conn_spatial):
    sql = compile_transform_sql(
        "transform.h3Aggregate",
        {"resolution": 9, "metrics": {}},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT h3Cell FROM out").fetchall()
    assert len(rows) == 1


def test_transform_output_srid_passthrough_for_unaffected_ops():
    assert compiler.transform_output_srid("transform.filter", {}, input_srid=4326) == 4326
    assert (
        compiler.transform_output_srid(
            "transform.buffer",
            {"distance": 1},
            input_srid=2154,
        )
        == 2154
    )


def test_transform_output_srid_reproject_parses_target():
    srid = compiler.transform_output_srid(
        "transform.reproject",
        {"targetCrs": "EPSG:2154"},
        input_srid=4326,
    )
    assert srid == 2154


def test_transform_output_srid_intersection_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.intersection",
            {"withCollectionId": "x"},
            input_srid=4326,
            join_srid=3857,
        )


def test_transform_output_srid_intersection_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.intersection",
        {"withCollectionId": "x"},
        input_srid=4326,
        join_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_count_within_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.countWithin",
            {"withCollectionId": "x"},
            input_srid=4326,
            join_srid=2154,
        )


def test_transform_output_srid_h3_aggregate_requires_4326():
    with pytest.raises(ValueError, match="EPSG:4326"):
        compiler.transform_output_srid(
            "transform.h3Aggregate",
            {"resolution": 9, "metrics": {}},
            input_srid=3857,
        )
    assert (
        compiler.transform_output_srid(
            "transform.h3Aggregate",
            {"resolution": 9, "metrics": {}},
            input_srid=4326,
        )
        == 4326
    )


def test_transform_output_srid_qgis_passes_through_by_default():
    srid = compiler.transform_output_srid(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
        input_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_qgis_uses_explicit_output_srid():
    # gdal:warpreproject's real schema (Task 1) requires DATA_TYPE/
    # MULTITHREADING/RESAMPLING too — TARGET_CRS itself is optional, but
    # included here for realism (this IS the reprojection param).
    srid = compiler.transform_output_srid(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {
                "TARGET_CRS": "EPSG:2154",
                "DATA_TYPE": 0,
                "MULTITHREADING": False,
                "RESAMPLING": 0,
            },
            "outputSrid": "EPSG:2154",
        },
        input_srid=4326,
    )
    assert srid == 2154


def test_secondary_predecessor_id_returns_none_without_secondary_edge():
    edges = [_edge("e1", "r1", "t1")]
    assert compiler.secondary_predecessor_id("t1", edges) is None


def test_secondary_predecessor_id_returns_the_secondary_source():
    edges = [
        _edge("e1", "r1", "t1"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    assert compiler.secondary_predecessor_id("t1", edges) == "r2"


def test_secondary_predecessor_id_raises_on_multiple_secondary_edges():
    edges = [
        PipelineEdge(id="e1", **{"from": "r1"}, to="t1", role="secondary"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    with pytest.raises(ValueError, match="secondary incoming edge"):
        compiler.secondary_predecessor_id("t1", edges)


def test_predecessor_id_ignores_secondary_edges():
    # Un nœud binaire avec 1 arête primaire + 1 arête secondaire n'est PAS "2
    # arêtes entrantes" pour predecessor_id — seule secondary_predecessor_id
    # voit la seconde. predecessor_id doit continuer à ne compter que la
    # primaire, exactement comme si l'arête secondaire n'existait pas.
    edges = [
        _edge("e1", "r1", "t1"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    assert predecessor_id("t1", edges) == "r1"


def test_compile_merge(conn):
    conn.execute("CREATE TABLE other (id INTEGER, pop INTEGER)")
    conn.execute("INSERT INTO other VALUES (10, 99)")
    sql = compile_transform_sql("transform.merge", {}, input_view="base", join_view="other")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, region, pop FROM out ORDER BY id").fetchall()
    assert rows == [(1, "Nord", 10), (2, "Sud", 5), (3, "Nord", 20), (10, None, 99)]


def test_compile_merge_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql("transform.merge", {}, input_view="base")


def test_transform_output_srid_merge_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.merge",
            {},
            input_srid=4326,
            join_srid=3857,
        )


def test_transform_output_srid_merge_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.merge",
        {},
        input_srid=4326,
        join_srid=4326,
    )
    assert srid == 4326


def test_compile_swap_coordinates(conn_spatial):
    sql = compile_transform_sql("transform.swapCoordinates", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == (45.0, 3.0)


def test_compile_translate_geometry(conn_spatial):
    sql = compile_transform_sql(
        "transform.translateGeometry", {"dx": 1.0, "dy": 2.0}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == pytest.approx((4.0, 47.0))


def test_compile_translate_geometry_rejects_3d_geometry(conn_spatial):
    # Régression : ST_Translate corrompt silencieusement les géométries 3D
    # dans cette version de DuckDB spatial (§0 du plan) — ce nœud doit
    # échouer bruyamment plutôt que produire des coordonnées fausses.
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql(
        "transform.translateGeometry", {"dx": 1.0, "dy": 2.0}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    with pytest.raises(duckdb.InvalidInputException, match="3D geometry not supported"):
        conn_spatial.execute("SELECT * FROM out3d").fetchall()


def test_compile_scale_geometry(conn_spatial):
    sql = compile_transform_sql(
        "transform.scaleGeometry", {"xs": 2.0, "ys": 3.0}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == pytest.approx((6.0, 135.0))


def test_compile_scale_geometry_keeps_z_untouched(conn_spatial):
    # Contrôle négatif du garde 3D : Scale, contrairement à Translate/Rotate,
    # est vérifié correct sur une géométrie avec Z (§0) — pas de garde ici.
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (2 3 4)'))")
    sql = compile_transform_sql(
        "transform.scaleGeometry", {"xs": 2.0, "ys": 2.0}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    x, y, z = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry), ST_Z(geometry) FROM out3d"
    ).fetchone()
    assert (x, y, z) == pytest.approx((4.0, 6.0, 4.0))


def test_compile_rotate_geometry_around_own_centroid(conn_spatial):
    # Un carré loin de l'origine tourné de 90° autour de SON PROPRE centre
    # (pas de l'origine (0,0) — ST_Rotate seul tourne autour de l'origine,
    # ce nœud recentre avant/après, design §4.1).
    conn_spatial.execute("CREATE TABLE square (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO square VALUES "
        "(1, ST_GeomFromText('POLYGON((10 10, 12 10, 12 12, 10 12, 10 10))'))"
    )
    import math

    sql = compile_transform_sql(
        "transform.rotateGeometry", {"radians": math.pi / 2}, input_view="square"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0]
    assert wkt == "POLYGON ((12 10, 12 12, 10 12, 10 10, 12 10))"


def test_compile_rotate_geometry_rejects_3d_geometry(conn_spatial):
    # rotateGeometry compose ST_Translate en interne (recentrage) — même
    # garde 3D que translateGeometry, même cause (§0).
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql("transform.rotateGeometry", {"radians": 1.0}, input_view="base3d")
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    with pytest.raises(duckdb.InvalidInputException, match="3D geometry not supported"):
        conn_spatial.execute("SELECT * FROM out3d").fetchall()


def test_compile_create_geometry_replaces_geometry_with_literal_wkt(conn_spatial):
    sql = compile_transform_sql(
        "transform.createGeometry", {"wkt": "POINT(2.35 48.85)"}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out ORDER BY id").fetchall()
    assert rows == [("POINT (2.35 48.85)",), ("POINT (2.35 48.85)",)]


def test_compile_create_geometry_escapes_single_quotes(conn_spatial):
    # wkt vient d'un champ texte libre côté config — jamais interpolé sans
    # échappement dans le SQL généré (une géométrie littérale ne devrait
    # jamais contenir de guillemet simple, mais le compilateur ne doit pas
    # produire de SQL invalide/injectable si un jour c'est le cas).
    sql = compile_transform_sql(
        "transform.createGeometry", {"wkt": "POINT(1 2)'; DROP TABLE base; --"}, input_view="base"
    )
    assert "''" in sql


def test_compile_create_geometry_works_without_a_geometry_column(conn_spatial):
    conn_spatial.execute("CREATE TABLE attrs_no_geom (id INTEGER, name VARCHAR)")
    conn_spatial.execute("INSERT INTO attrs_no_geom VALUES (1, 'a')")
    sql = compile_transform_sql(
        "transform.createGeometry", {"wkt": "POINT(2.35 48.85)"}, input_view="attrs_no_geom"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out_no_geom AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out_no_geom").fetchone()[0]
    assert wkt == "POINT (2.35 48.85)"


def test_compile_round_coordinates(conn_spatial):
    sql = compile_transform_sql("transform.roundCoordinates", {"gridSize": 0.01}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out ORDER BY id").fetchall()
    assert rows == [("POINT (3 45)",), ("POINT (3 45)",)]


def test_compile_concat_coordinates_builds_a_point_from_attribute_columns(conn_spatial):
    conn_spatial.execute("CREATE TABLE xy (id INTEGER, lon DOUBLE, lat DOUBLE, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO xy VALUES (1, 3.0, 45.0, NULL)")
    sql = compile_transform_sql(
        "transform.concatCoordinates", {"xColumn": "lon", "yColumn": "lat"}, input_view="xy"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0]
    assert wkt == "POINT (3 45)"


def test_compile_concat_coordinates_works_without_a_geometry_column(conn_spatial):
    conn_spatial.execute("CREATE TABLE xy_no_geom (id INTEGER, lon DOUBLE, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO xy_no_geom VALUES (1, 3.0, 45.0)")
    sql = compile_transform_sql(
        "transform.concatCoordinates", {"xColumn": "lon", "yColumn": "lat"}, input_view="xy_no_geom"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out_no_geom AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out_no_geom").fetchone()[0]
    assert wkt == "POINT (3 45)"


def test_compile_extract_coordinates_default_column_names(conn_spatial):
    sql = compile_transform_sql("transform.extractCoordinates", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT x, y FROM out WHERE id = 1").fetchone()
    assert row == (3.0, 45.0)


def test_compile_extract_coordinates_custom_column_names(conn_spatial):
    sql = compile_transform_sql(
        "transform.extractCoordinates",
        {"xColumn": "longitude", "yColumn": "latitude"},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT longitude, latitude FROM out WHERE id = 1").fetchone()
    assert row == (3.0, 45.0)


def test_compile_extract_elevation_is_null_for_2d_geometry(conn_spatial):
    sql = compile_transform_sql("transform.extractElevation", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT elevation FROM out WHERE id = 1").fetchone()
    assert row == (None,)


def test_compile_extract_elevation_reads_z_for_3d_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql("transform.extractElevation", {"column": "z"}, input_view="base3d")
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    row = conn_spatial.execute("SELECT z FROM out3d").fetchone()
    assert row == (3.0,)


def test_compile_extract_dimension_is_2_for_2d_geometry(conn_spatial):
    sql = compile_transform_sql("transform.extractDimension", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT dimension FROM out WHERE id = 1").fetchone()
    assert row == (2,)


def test_compile_extract_dimension_is_3_for_3d_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql("transform.extractDimension", {}, input_view="base3d")
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    row = conn_spatial.execute("SELECT dimension FROM out3d").fetchone()
    assert row == (3,)


def test_compile_count_vertices(conn_spatial):
    conn_spatial.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO line VALUES (1, ST_GeomFromText('LINESTRING(0 0, 1 1, 2 2)'))"
    )
    sql = compile_transform_sql("transform.countVertices", {"column": "n"}, input_view="line")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT n FROM out").fetchone()
    assert row == (3,)


def test_compile_extract_srid_returns_the_pipeline_srid(conn_spatial):
    sql = compile_transform_sql("transform.extractSrid", {}, input_view="base", input_srid=4326)
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT srid FROM out WHERE id = 1").fetchone()
    assert row == (4326,)


def test_compile_set_srid_does_not_change_the_geometry(conn_spatial):
    sql = compile_transform_sql("transform.setSrid", {"targetSrid": 2154}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out WHERE id = 1").fetchone()
    assert row == ("POINT (3 45)",)


def test_set_srid_overrides_the_output_srid():
    from app.pipelines.compiler import transform_output_srid

    srid = transform_output_srid("transform.setSrid", {"targetSrid": 2154}, input_srid=4326)
    assert srid == 2154


def test_compile_reproject_attribute_uses_correct_axis_order(conn_spatial):
    conn_spatial.execute(
        "CREATE TABLE attr_xy (id INTEGER, lon DOUBLE, lat DOUBLE, geometry GEOMETRY)"
    )
    conn_spatial.execute("INSERT INTO attr_xy VALUES (1, 3.0, 45.0, ST_Point(0, 0))")
    sql = compile_transform_sql(
        "transform.reprojectAttribute",
        {"xColumn": "lon", "yColumn": "lat", "sourceCrs": "EPSG:4326", "targetCrs": "EPSG:3857"},
        input_view="attr_xy",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    lon, lat = conn_spatial.execute("SELECT lon, lat FROM out WHERE id = 1").fetchone()
    assert lon == pytest.approx(333958.47, abs=1)
    assert lat == pytest.approx(5621521.49, abs=1)


def test_compile_format_coordinates_decimal_degrees(conn_spatial):
    conn_spatial.execute("CREATE TABLE lat_table (id INTEGER, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO lat_table VALUES (1, 48.858093)")
    sql = compile_transform_sql(
        "transform.formatCoordinates",
        {
            "sourceColumn": "lat",
            "targetColumn": "latText",
            "format": "decimalDegrees",
            "precision": 2,
        },
        input_view="lat_table",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT latText FROM out").fetchone()
    assert row == (48.86,)


def test_compile_format_coordinates_dms(conn_spatial):
    conn_spatial.execute("CREATE TABLE lat_table (id INTEGER, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO lat_table VALUES (1, 48.858093), (2, -48.858093)")
    sql = compile_transform_sql(
        "transform.formatCoordinates",
        {"sourceColumn": "lat", "targetColumn": "latText", "format": "dms", "precision": 2},
        input_view="lat_table",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT latText FROM out ORDER BY id").fetchall()
    assert rows == [("48°51'29.13\"",), ("-48°51'29.13\"",)]


def test_compile_format_coordinates_dms_carries_seconds_rounding_into_minutes(conn_spatial):
    conn_spatial.execute("CREATE TABLE lat_table2 (id INTEGER, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO lat_table2 VALUES (1, 48.99999999)")
    sql = compile_transform_sql(
        "transform.formatCoordinates",
        {"sourceColumn": "lat", "targetColumn": "latText", "format": "dms", "precision": 2},
        input_view="lat_table2",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out2 AS {sql}")
    row = conn_spatial.execute("SELECT latText FROM out2").fetchone()
    assert row == ("49°0'0.00\"",)
