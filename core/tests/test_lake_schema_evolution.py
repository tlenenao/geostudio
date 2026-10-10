# SPDX-License-Identifier: Apache-2.0
"""REV-308 (entier nullable -> Int64) et REV-311 (colonne ajoutée après
l'écriture des partitions du lac : NULL, jamais un Binder Error). Sans PostGIS."""

from io import BytesIO

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import AggregateRequestBody, run_collection_aggregate
from app.cdc.compaction import merge_geoparquet
from app.cdc.parquet_writer import ChangeRow, build_geodataframe, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo
from app.pipelines.runtime import _materialize_reader


def _cr(pk, montant, op="insert"):
    return ChangeRow(
        op=op,
        lsn=pk,
        ts=1.0,
        pk_column="id",
        pk_value=pk,
        columns={"id": pk, "montant": montant, "taux": 1.5},
        geometry_column=None,
        geometry_wkb_hex=None,
    )


def test_rev308_nullable_int_column_stays_integer(tmp_path):
    rows = [_cr(1, 10), _cr(2, None)]
    gdf = build_geodataframe(rows, srid=4326)
    assert str(gdf["montant"].dtype) == "Int64"
    assert str(gdf["taux"].dtype) == "float64"  # un vrai flottant reste flottant
    path = str(tmp_path / "a.parquet")
    write_geoparquet(rows, srid=4326, path=path)
    back = gpd.read_parquet(path)
    assert str(back["montant"].dtype) == "Int64"
    assert back["montant"].tolist()[0] == 10


def test_rev308_compaction_merge_keeps_int64():
    blobs = []
    for rows in ([_cr(1, 10)], [_cr(2, None)]):
        buf = BytesIO()
        build_geodataframe(rows, srid=4326).to_parquet(buf)
        blobs.append(buf.getvalue())
    merged = gpd.read_parquet(BytesIO(merge_geoparquet(blobs)))
    assert str(merged["montant"].dtype) == "Int64"


INFO = TableInfo(
    table_name="villes",
    pk_column="fid",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=False),  # ajoutée en gén. 2
        ColumnInfo(name="rang", type="integer", required=False),  # ajoutée en gén. 3
        ColumnInfo(name="note", type="string", required=False),  # jamais écrite
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _write(root, dt, fid, extra):
    part = root / "tenant_id=t1" / "collection_id=villes" / f"dt={dt}"
    part.mkdir(parents=True, exist_ok=True)
    row = {
        "fid": fid,
        "region": "R",
        "_op": "insert",
        "_lsn": fid,
        "_seq": 0,
        "_ts": float(fid),
        "geometry": Point(fid, 48.5),
        **extra,
    }
    gpd.GeoDataFrame([row], geometry="geometry", crs="EPSG:4326").to_parquet(part / "p.parquet")


@pytest.fixture()
def lake(tmp_path):
    _write(tmp_path, "2026-01-01", 1, {})
    _write(tmp_path, "2026-02-01", 2, {"pop": 5})
    _write(tmp_path, "2026-03-01", 3, {"pop": 7, "rang": 1})
    return str(tmp_path)


def test_rev311_pipeline_reader_three_generations(conn, lake):
    _materialize_reader(
        conn,
        view_name="v",
        base_uri=lake,
        tenant_id="t1",
        collection_id="villes",
        table_info=INFO,
    )
    rows = conn.execute('SELECT fid, pop, rang, note FROM "v" ORDER BY fid').fetchall()
    assert rows == [(1, None, None, None), (2, 5, None, None), (3, 7, 1, None)]


def test_rev311_aggregate_on_never_written_column(conn, lake):
    _, rows = run_collection_aggregate(
        conn,
        base_uri=lake,
        tenant_id="t1",
        collection_id="villes",
        table_info=INFO,
        request=AggregateRequestBody(groupBy="region", agg="sum", field="pop"),
    )
    assert rows[0]["value"] == 12
