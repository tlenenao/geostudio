# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.compiler import compile_transform_sql, predecessor_id, topological_order
from app.pipelines import compiler


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
        "transform.select", {"columns": {"region": "zone", "pop": None}}, input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["zone", "pop"]


def test_compile_derive(conn):
    sql = compile_transform_sql(
        "transform.derive", {"column": "pop_double", "expr": "pop * 2"}, input_view="base",
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
        "transform.join", {"withCollectionId": "x", "on": "id", "how": "inner"},
        input_view="base", join_view="other",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, label FROM out ORDER BY id").fetchall()
    assert rows == [(1, "A"), (2, "B")]


def test_compile_join_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql(
            "transform.join", {"withCollectionId": "x", "on": "id"}, input_view="base",
        )


def test_compile_unknown_transform_op_raises():
    with pytest.raises(ValueError, match="not a transform op"):
        compile_transform_sql("reader.collection", {"collectionId": "x"}, input_view="base")


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
        "transform.buffer", {"distance": 1, "unit": "native"}, input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute(
        "SELECT ST_GeometryType(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert row == ("POLYGON",)


def test_compile_buffer_meters_unit_uses_correct_axis_order(conn_spatial):
    # Régression : sans always_xy=true dans les deux ST_Transform internes,
    # DuckDB spatial applique l'ordre d'axe EPSG (lat,lng) et le buffer sort
    # décalé de plusieurs milliers de km — vérifié empiriquement (cf. plan
    # Global Constraints). Un point à ~333 m au nord doit être DANS un buffer
    # de 500 m ; un point à ~111 km doit être EN DEHORS.
    sql = compile_transform_sql(
        "transform.buffer", {"distance": 500, "unit": "meters"},
        input_view="base", input_srid=4326,
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
        "transform.reproject", {"targetCrs": "EPSG:3857"},
        input_view="base", input_srid=4326,
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
        "transform.intersection", {"withCollectionId": "x"},
        input_view="base", join_view="other",
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
        input_view="base", join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    types = conn_spatial.execute("SELECT ST_GeometryType(geometry) FROM out").fetchall()
    assert all(t == ("POINT",) for t in types)  # point ∩ polygon == point


def test_compile_count_within_intersects_default(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.countWithin", {"withCollectionId": "x"},
        input_view="base", join_view="other",
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
        input_view="base", join_view="other",
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
        "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT h3Cell FROM out").fetchall()
    assert len(rows) == 1


def test_transform_output_srid_passthrough_for_unaffected_ops():
    assert compiler.transform_output_srid("transform.filter", {}, input_srid=4326) == 4326
    assert compiler.transform_output_srid(
        "transform.buffer", {"distance": 1}, input_srid=2154,
    ) == 2154


def test_transform_output_srid_reproject_parses_target():
    srid = compiler.transform_output_srid(
        "transform.reproject", {"targetCrs": "EPSG:2154"}, input_srid=4326,
    )
    assert srid == 2154


def test_transform_output_srid_intersection_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.intersection", {"withCollectionId": "x"},
            input_srid=4326, join_srid=3857,
        )


def test_transform_output_srid_intersection_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.intersection", {"withCollectionId": "x"},
        input_srid=4326, join_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_count_within_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.countWithin", {"withCollectionId": "x"},
            input_srid=4326, join_srid=2154,
        )


def test_transform_output_srid_h3_aggregate_requires_4326():
    with pytest.raises(ValueError, match="EPSG:4326"):
        compiler.transform_output_srid(
            "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_srid=3857,
        )
    assert compiler.transform_output_srid(
        "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_srid=4326,
    ) == 4326


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
            "params": {"TARGET_CRS": "EPSG:2154", "DATA_TYPE": 0,
                       "MULTITHREADING": False, "RESAMPLING": 0},
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
            "transform.merge", {}, input_srid=4326, join_srid=3857,
        )


def test_transform_output_srid_merge_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.merge", {}, input_srid=4326, join_srid=4326,
    )
    assert srid == 4326
