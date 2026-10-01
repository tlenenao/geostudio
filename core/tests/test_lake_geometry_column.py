# SPDX-License-Identifier: Apache-2.0
"""RC-5 : le GeoParquet du lac porte `geometry`, une collection importée a
`geom` comme geometry_column. Tous les lecteurs doivent fonctionner dessus
(SQL Lab, agrégats, reader.collection) — et le typage temporel de SQL Lab
(j05-012). Sans PostGIS : DuckDB lit des chemins locaux."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import AggregateRequestBody, run_collection_aggregate
from app.analytics.sql_sandbox import run_analyst_sql
from app.collections.introspection import ColumnInfo, TableInfo
from app.pipelines.runtime import _materialize_reader

INFO = TableInfo(
    table_name="villes",
    pk_column="fid",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
        ColumnInfo(name="d", type="datetime", required=False),
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


@pytest.fixture()
def lake(tmp_path):
    part = tmp_path / "tenant_id=t1" / "collection_id=villes" / "dt=2026-07-18"
    part.mkdir(parents=True)
    rows = [
        {
            "fid": i,
            "region": r,
            "pop": p,
            "d": "2026-01-02T03:04:05+00:00",
            "_op": "insert",
            "_lsn": 1,
            "_seq": 0,
            "_ts": 1.0,
            "geometry": Point(x, 48.5),
        }
        for i, (r, p, x) in enumerate([("Nord", 10, 2.5), ("Sud", 5, 100.0)], start=1)
    ]
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(part / "p.parquet")
    return str(tmp_path)


def test_sql_lab_on_imported_collection(conn, lake):
    _, rows, _ = run_analyst_sql(
        conn,
        sql="SELECT ST_AsText(geom) AS g, typeof(d) AS t FROM villes ORDER BY fid",
        allowed={"villes": INFO},
        base_uri=lake,
        tenant_id="t1",
    )
    assert rows[0][0] == "POINT (2.5 48.5)"
    assert "TIMESTAMP" in rows[0][1]  # j05-012


def test_aggregate_bbox_on_imported_collection(conn, lake):
    _, rows = run_collection_aggregate(
        conn,
        base_uri=lake,
        tenant_id="t1",
        collection_id="villes",
        table_info=INFO,
        request=AggregateRequestBody(
            groupBy="region", agg="sum", field="pop", bbox=(2.0, 48.0, 3.0, 49.0)
        ),
    )
    assert rows == [{"region": "Nord", "value": 10}]


def test_reader_collection_on_imported_collection(conn, lake):
    _materialize_reader(
        conn, view_name="v", base_uri=lake, tenant_id="t1", collection_id="villes", table_info=INFO
    )
    assert conn.execute("SELECT count(*) FROM v WHERE geometry IS NOT NULL").fetchone() == (2,)
