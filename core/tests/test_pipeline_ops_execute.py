# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.execute import _read_geometry_rows, _write_geometry_rows


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE base (id INTEGER, geometry GEOMETRY)")
    c.execute("INSERT INTO base VALUES (1, ST_Point(3.0, 45.0)), (2, ST_Point(3.001, 45.0))")
    return c


def test_read_write_geometry_rows_round_trips(conn):
    df = _read_geometry_rows(conn, "base")
    assert list(df.columns) == ["id", "geometry"]
    import shapely.wkb

    geom = shapely.wkb.loads(bytes(df["geometry"][0]))
    assert geom.wkt == "POINT (3 45)"

    _write_geometry_rows(conn, df, view_name="roundtrip")
    row = conn.execute("SELECT id, ST_AsText(geometry) FROM roundtrip WHERE id = 1").fetchone()
    assert row == (1, "POINT (3 45)")


def test_execute_triangulate_produces_one_row_per_triangle(conn):
    conn.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts VALUES "
        "(1, ST_Point(0, 0)), (2, ST_Point(4, 0)), (3, ST_Point(2, 4)), (4, ST_Point(1, 1))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts", view_name="out", params={})
    count = conn.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count >= 2  # au moins 2 triangles pour 4 points non colinéaires
    geom_types = conn.execute("SELECT DISTINCT ST_GeometryType(geometry) FROM out").fetchall()
    assert geom_types == [("POLYGON",)]


def test_execute_densify_adds_vertices_every_max_segment_length(conn):
    conn.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO line VALUES (1, ST_GeomFromText('LINESTRING (0 0, 10 0)'))")
    from app.pipelines.ops.execute import _execute_densify

    _execute_densify(conn, input_view="line", view_name="out", params={"maxSegmentLength": 2})
    row = conn.execute("SELECT ST_NPoints(geometry) FROM out WHERE id = 1").fetchone()
    assert row == (6,)


def test_execute_minimum_bounding_circle(conn):
    conn.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts VALUES (1, ST_Point(0, 0)), (2, ST_Point(4, 0)), (3, ST_Point(2, 3))"
    )
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    _execute_minimum_bounding_circle(conn, input_view="pts", view_name="out", params={})
    row = conn.execute("SELECT ST_GeometryType(geometry) FROM out").fetchone()
    assert row == ("POLYGON",)

    # Agrégation géométrie-seule (comme resolveOverlaps/triangulate) : les 3 lignes en
    # entrée produisent EXACTEMENT une ligne en sortie (le cercle englobant unique), pas
    # une ligne par point d'entrée.
    count = conn.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count == 1


def test_triangulate_on_polygon_raises_pipeline_runtime_error(conn):
    conn.execute("CREATE TABLE poly (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO poly VALUES (1, ST_GeomFromText('POLYGON ((0 0, 1 0, 1 1, 0 0))'))")
    from app.pipelines.ops.execute import _execute_triangulate

    with pytest.raises(PipelineRuntimeError, match="Point"):
        _execute_triangulate(conn, input_view="poly", view_name="out", params={})


@pytest.mark.parametrize(
    ("fn_name", "params"),
    [
        ("_execute_triangulate", {}),
        ("_execute_densify", {"maxSegmentLength": 1}),
        ("_execute_minimum_bounding_circle", {}),
    ],
)
def test_empty_input_yields_empty_output(conn, fn_name, params):
    from app.pipelines.ops import execute

    conn.execute("CREATE TABLE empty_in (id INTEGER, geometry GEOMETRY)")
    getattr(execute, fn_name)(conn, input_view="empty_in", view_name="out", params=params)
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (0,)


@pytest.mark.parametrize(
    ("fn_name", "params"),
    [
        ("_execute_densify", {"maxSegmentLength": 2}),
        ("_execute_minimum_bounding_circle", {}),
        ("_execute_triangulate", {}),
    ],
)
def test_null_geometry_rows_are_dropped(conn, fn_name, params):
    from app.pipelines.ops import execute

    conn.execute("CREATE TABLE with_null (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO with_null VALUES (1, NULL), (2, ST_Point(0, 0)), "
        "(3, ST_Point(4, 0)), (4, ST_Point(2, 3))"
    )
    getattr(execute, fn_name)(conn, input_view="with_null", view_name="out", params=params)
    assert conn.execute("SELECT count(*) FROM out WHERE geometry IS NULL").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] >= 1


def test_densify_with_empty_linestring_does_not_crash(conn):
    # Jumelle de _write_geometry_rows : segmentize d'une géométrie vide reste écrivable.
    conn.execute("CREATE TABLE empty_line (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO empty_line VALUES (1, ST_GeomFromText('LINESTRING EMPTY'))")
    from app.pipelines.ops.execute import _execute_densify

    _execute_densify(conn, input_view="empty_line", view_name="out", params={"maxSegmentLength": 1})
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (1,)


def test_write_geometry_rows_tolerates_null_geometry(conn):
    import pandas as pd
    import shapely
    import shapely.wkb

    df = pd.DataFrame({"id": [1, 2], "geometry": [None, shapely.wkb.dumps(shapely.Point(1, 1))]})
    _write_geometry_rows(conn, df, view_name="out")
    assert conn.execute("SELECT id, ST_AsText(geometry) FROM out ORDER BY id").fetchall() == [
        (1, None),
        (2, "POINT (1 1)"),
    ]


def test_read_geometry_rows_without_geometry_column_raises(conn):
    conn.execute("CREATE TABLE no_geom (id INTEGER)")
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _read_geometry_rows(conn, "no_geom")


def test_execute_triangulate_without_group_by_stays_one_global_cloud(conn):
    # Sans groupBy (défaut), l'ancien comportement global est conservé : deux nuages distincts
    # sont fusionnés en une seule triangulation (un triangle « pont » traverse le vide).
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(1, 0)), (1, ST_Point(0, 1)), "
        "(2, ST_Point(100, 100)), (2, ST_Point(101, 100)), (2, ST_Point(100, 101))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts_grouped", view_name="out_grouped", params={})
    assert conn.execute("SELECT DISTINCT id FROM out_grouped").fetchall() == [(1,)]
    bounds = conn.execute(
        "SELECT min(ST_XMin(geometry)), max(ST_XMax(geometry)) FROM out_grouped"
    ).fetchone()
    assert bounds[0] < 50 and bounds[1] > 50


def test_triangulate_group_by_triangulates_each_group_without_bridging(conn):
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(1, 0)), (1, ST_Point(0, 1)), "
        "(2, ST_Point(100, 100)), (2, ST_Point(101, 100)), (2, ST_Point(100, 101))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(
        conn, input_view="pts_grouped", view_name="out", params={"groupBy": ["id"]}
    )
    assert conn.execute("SELECT id, count(*) FROM out GROUP BY id ORDER BY id").fetchall() == [
        (1, 1),
        (2, 1),
    ]
    spans = conn.execute(
        "SELECT id, ST_XMax(geometry) - ST_XMin(geometry) FROM out ORDER BY id"
    ).fetchall()
    assert all(span <= 1.0 for _, span in spans)  # aucun triangle ne relie les deux nuages


def test_triangulate_group_with_fewer_than_three_points_yields_no_row(conn):
    conn.execute("CREATE TABLE two (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO two VALUES (1, ST_Point(0, 0)), (1, ST_Point(1, 0))")
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="two", view_name="out", params={"groupBy": ["id"]})
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (0,)


def test_minimum_bounding_circle_group_by_gives_one_circle_per_group(conn):
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(4, 0)), (2, ST_Point(100, 100)), (2, ST_Point(100, 102))"
    )
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    _execute_minimum_bounding_circle(
        conn, input_view="pts_grouped", view_name="out", params={"groupBy": ["id"]}
    )
    rows = conn.execute(
        "SELECT id, ST_GeometryType(geometry), ST_XMin(geometry) FROM out ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(1, "POLYGON"), (2, "POLYGON")]  # id conservé
    assert rows[0][2] < 1 and rows[1][2] > 90  # chaque cercle autour de son groupe


def test_group_by_unknown_column_raises_pipeline_runtime_error(conn):
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    with pytest.raises(PipelineRuntimeError, match="nope"):
        _execute_minimum_bounding_circle(
            conn, input_view="base", view_name="out", params={"groupBy": ["nope"]}
        )


def test_group_by_geometry_column_is_rejected(conn):
    from app.pipelines.ops.execute import _execute_triangulate

    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _execute_triangulate(
            conn, input_view="base", view_name="out", params={"groupBy": ["geometry"]}
        )
