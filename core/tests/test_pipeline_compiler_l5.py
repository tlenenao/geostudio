# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 1 (AUD-077) : join sans colonnes dupliquées, comptages sans fusion de lignes
identiques, reproject strict. Exécuté contre un DuckDB réel (compilation + exécution)."""

import duckdb
import pytest

from app.pipelines import compiler
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.schemas import TransformReprojectParams


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def _cols(conn, view):
    return [d[0] for d in conn.execute(f'DESCRIBE "{view}"').fetchall()]


def _run(conn, op, params, *, input_view="a", join_view="b"):
    input_columns = _cols(conn, input_view)
    join_columns = _cols(conn, join_view) if join_view else None
    sql = compiler.compile_transform_sql(
        op,
        params,
        input_view=input_view,
        join_view=join_view,
        input_srid=4326,
        input_columns=input_columns,
        join_columns=join_columns,
    )
    return conn.execute(sql)


def test_join_keeps_one_geometry_and_prefixes_clashing_columns(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 1 AS id, 'A' AS name, ST_Point(0,0) AS geometry "
        "UNION ALL SELECT 2, 'B', ST_Point(1,1)"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 1 AS id, 'zone1' AS name, 10 AS pop, ST_Point(5,5) AS geometry"
    )
    rel = _run(conn, "transform.join", {"on": "id", "how": "left"})
    cols = [d[0] for d in rel.description]
    assert cols == ["id", "name", "geometry", "right_name", "pop"]
    rows = sorted(rel.fetchall(), key=lambda r: r[0])
    assert rows[0][3] == "zone1" and rows[0][4] == 10
    assert rows[1][3] is None


def test_join_refuses_a_missing_key(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS id, ST_Point(0,0) AS geometry")
    conn.execute("CREATE TABLE b AS SELECT 1 AS other, ST_Point(0,0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="id"):
        _run(conn, "transform.join", {"on": "id"})


def test_count_within_does_not_merge_identical_input_rows(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'x' AS name, ST_GeomFromText("
        "'POLYGON((0 0,2 0,2 2,0 2,0 0))') AS geometry FROM range(2)"
    )
    conn.execute("CREATE TABLE b AS SELECT ST_Point(1,1) AS geometry")
    rows = _run(conn, "transform.countWithin", {"countColumn": "n"}).fetchall()
    assert len(rows) == 2
    assert [r[-1] for r in rows] == [1, 1]


def test_count_within_refuses_an_existing_output_column(conn):
    conn.execute("CREATE TABLE a AS SELECT 3 AS n, ST_Point(0,0) AS geometry")
    conn.execute("CREATE TABLE b AS SELECT ST_Point(0,0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="n"):
        _run(conn, "transform.countWithin", {"countColumn": "n"})


def test_merge_children_does_not_merge_identical_parents(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS pid, ST_Point(0,0) AS geometry FROM range(2)")
    conn.execute("CREATE TABLE b AS SELECT 1 AS parent, 'c' AS label")
    rows = _run(
        conn,
        "transform.mergeChildren",
        {"parentOn": "pid", "childOn": "parent", "childrenColumn": "kids"},
    ).fetchall()
    assert len(rows) == 2


def test_reproject_accepts_only_epsg_codes():
    TransformReprojectParams.model_validate({"targetCrs": "EPSG:2154"})
    with pytest.raises(ValueError):
        TransformReprojectParams.model_validate({"targetCrs": "ESRI:102110"})


def test_reproject_refuses_an_unknown_input_srid():
    with pytest.raises(PipelineRuntimeError, match="setSrid"):
        compiler.compile_transform_sql(
            "transform.reproject",
            {"targetCrs": "EPSG:2154"},
            input_view="a",
            join_view=None,
            input_srid=0,
        )
