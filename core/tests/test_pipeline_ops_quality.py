# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 3 : validateGeometry, measure, spatialJoin (AUD-079, AUD-021)."""

import duckdb
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import quality
from app.pipelines.ops.contracts import OPERATIONS

BOWTIE = "POLYGON((0 0,2 2,2 0,0 2,0 0))"


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def _cols(conn, view):
    return [d[0] for d in conn.execute(f'DESCRIBE "{view}"').fetchall()]


def test_ops_are_registered():
    for op in ("transform.validateGeometry", "transform.measure", "transform.spatialJoin"):
        assert op in OPERATIONS


def test_validate_geometry_flags_with_reason(conn):
    conn.execute(
        f"CREATE TABLE src AS SELECT 1 AS id, ST_GeomFromText('{BOWTIE}') AS geometry "
        "UNION ALL SELECT 2, ST_GeomFromText('POINT(0 0)')"
    )
    quality.execute_validate_geometry(
        conn,
        input_view="src",
        view_name="out",
        params={"mode": "flag", "validColumn": "ok", "reasonColumn": "why"},
    )
    rows = conn.execute("SELECT id, ok, why FROM out ORDER BY id").fetchall()
    assert rows[0][1] is False and "Self-intersection" in rows[0][2]
    assert rows[1][1] is True and rows[1][2] is None


def test_validate_geometry_repairs(conn):
    conn.execute(f"CREATE TABLE src AS SELECT ST_GeomFromText('{BOWTIE}') AS geometry")
    quality.execute_validate_geometry(
        conn, input_view="src", view_name="out", params={"mode": "repair", "validColumn": "ok"}
    )
    assert conn.execute("SELECT ST_IsValid(geometry), ok FROM out").fetchone() == (True, False)


def test_measure_geodesic_area_in_square_meters(conn):
    conn.execute(
        "CREATE TABLE src AS SELECT ST_GeomFromText("
        "'POLYGON((2 49,2.01 49,2.01 49.01,2 49.01,2 49))') AS geometry"
    )
    quality.execute_measure(
        conn,
        input_view="src",
        view_name="out",
        params={"measure": "area", "method": "geodesic", "column": "m2"},
        input_srid=4326,
    )
    (area,) = conn.execute("SELECT m2 FROM out").fetchone()
    assert 800_000 < area < 830_000


def test_measure_planar_uses_native_units(conn):
    conn.execute("CREATE TABLE src AS SELECT ST_GeomFromText('LINESTRING(0 0, 3 4)') AS geometry")
    quality.execute_measure(
        conn,
        input_view="src",
        view_name="out",
        params={"measure": "length", "method": "planar", "column": "len"},
        input_srid=2154,
    )
    assert conn.execute("SELECT len FROM out").fetchone()[0] == 5


def test_spatial_join_reports_prefixed_attributes(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'p1' AS ref, ST_GeomFromText("
        "'POLYGON((0 0,1 0,1 1,0 1,0 0))') AS geometry "
        "UNION ALL SELECT 'p2', ST_GeomFromText('POLYGON((5 5,6 5,6 6,5 6,5 5))')"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 'UA' AS zone, ST_GeomFromText("
        "'POLYGON((0 0,0.7 0,0.7 1,0 1,0 0))') AS geometry "
        "UNION ALL SELECT 'N', ST_GeomFromText('POLYGON((0.7 0,1 0,1 1,0.7 1,0.7 0))')"
    )
    sql = quality.compile_spatial_join(
        {"how": "left", "match": "largestOverlap"},
        input_view="a",
        join_view="b",
        input_srid=4326,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b"),
    )
    rows = conn.execute(f"SELECT ref, join_zone FROM ({sql}) ORDER BY ref").fetchall()
    assert rows == [("p1", "UA"), ("p2", None)]


def test_spatial_join_all_matches_duplicates_rows(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'p1' AS ref, ST_GeomFromText("
        "'POLYGON((0 0,1 0,1 1,0 1,0 0))') AS geometry"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 'x' AS zone, ST_Point(0.2,0.2) AS geometry "
        "UNION ALL SELECT 'y', ST_Point(0.8,0.8)"
    )
    sql = quality.compile_spatial_join(
        {"how": "inner", "match": "all"},
        input_view="a",
        join_view="b",
        input_srid=4326,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b"),
    )
    assert conn.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0] == 2


def test_spatial_join_refuses_column_clash(conn):
    with pytest.raises(PipelineRuntimeError, match="join_zone"):
        quality.compile_spatial_join(
            {},
            input_view="a",
            join_view="b",
            input_srid=4326,
            input_columns=["join_zone", "geometry"],
            join_columns=["zone", "geometry"],
        )
