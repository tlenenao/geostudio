# SPDX-License-Identifier: Apache-2.0
"""AUD-062 : SQL Lab ne matérialise que les colonnes que la requête lit."""

import duckdb
import geopandas as gpd
from shapely.geometry import Point

from app.analytics.sql_sandbox import collect_column_refs, parse_ast, run_analyst_sql
from app.collections.introspection import ColumnInfo, TableInfo

INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
        ColumnInfo(name="salary", type="integer", required=False),
    ],
)


def _refs(sql):
    c = duckdb.connect(":memory:")
    try:
        return collect_column_refs(parse_ast(c, sql))
    finally:
        c.close()


def _lake(tmp_path):
    part = tmp_path / "tenant_id=default" / "collection_id=villes" / "dt=2026-09-06"
    part.mkdir(parents=True)
    gpd.GeoDataFrame(
        [
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "salary": 45000,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
        geometry="geometry",
        crs="EPSG:4326",
    ).to_parquet(part / "part-1.parquet")


def _run(tmp_path, sql, masked=frozenset()):
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    try:
        _cols, rows, _ = run_analyst_sql(
            conn,
            sql=sql,
            allowed={"villes": INFO},
            base_uri=str(tmp_path),
            tenant_id="default",
            masked_fields_by_collection={"villes": masked},
        )
        return rows, sorted(r[0] for r in conn.execute("DESCRIBE villes").fetchall())
    finally:
        conn.close()


def test_collect_column_refs_names_and_whole_table_forms():
    assert _refs('SELECT region, "POP" FROM villes WHERE id > 1') == {"region", "pop", "id"}
    assert _refs("SELECT v.region FROM villes v") == {"region"}
    assert _refs("SELECT count(*) FROM villes") == set()
    for sql in [
        "SELECT * FROM villes",
        "SELECT v.* EXCLUDE (pop) FROM villes v",
        "SELECT COLUMNS('r.*') FROM villes",
        "SELECT villes FROM villes",  # la ligne entière comme struct
    ]:
        assert _refs(sql) is None, sql


def test_only_referenced_columns_are_materialized(tmp_path):
    _lake(tmp_path)
    rows, temp_columns = _run(tmp_path, "SELECT region FROM villes WHERE pop > 1")
    assert rows == [["Nord"]]
    assert temp_columns == ["id", "pop", "region"]  # ni salary ni geometry


def test_count_star_still_works_with_only_the_pk(tmp_path):
    _lake(tmp_path)
    rows, temp_columns = _run(tmp_path, "SELECT count(*) FROM villes")
    assert rows == [[1]]
    assert temp_columns == ["id"]


def test_select_star_keeps_every_unmasked_column(tmp_path):
    _lake(tmp_path)
    _rows, temp_columns = _run(tmp_path, "SELECT * FROM villes", masked=frozenset({"salary"}))
    assert temp_columns == ["geometry", "id", "pop", "region"]
