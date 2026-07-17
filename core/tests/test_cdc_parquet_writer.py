# SPDX-License-Identifier: Apache-2.0
import geopandas as gpd
import pandas as pd
import shapely.wkb
from shapely.geometry import Point

from app.cdc.parquet_writer import ChangeRow, build_geodataframe, write_geoparquet


def _hex(geom) -> str:
    return shapely.wkb.dumps(geom, hex=True)


def test_build_geodataframe_insert_and_update():
    rows = [
        ChangeRow(op="insert", lsn=100, ts=1721212121.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "a"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(2.3, 48.8))),
        ChangeRow(op="update", lsn=105, ts=1721212125.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "b"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(2.4, 48.9))),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert list(gdf["_op"]) == ["insert", "update"]
    assert list(gdf["_lsn"]) == [100, 105]
    assert list(gdf["_ts"]) == [1721212121.0, 1721212125.0]
    assert list(gdf["titre"]) == ["a", "b"]
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.iloc[1].equals(Point(2.4, 48.9))


def test_build_geodataframe_delete_is_tombstone_only():
    rows = [
        ChangeRow(op="insert", lsn=1, ts=1.0, pk_column="id", pk_value=1,
                  columns={"id": 1, "titre": "a"}, geometry_column="geom",
                  geometry_wkb_hex=_hex(Point(0, 0))),
        ChangeRow(op="delete", lsn=2, ts=2.0, pk_column="id", pk_value=1,
                  columns={"id": 1}, geometry_column="geom", geometry_wkb_hex=None),
    ]
    gdf = build_geodataframe(rows, srid=4326)
    assert gdf["_op"].iloc[1] == "delete"
    assert pd.isna(gdf["titre"].iloc[1])  # tombstone : pas de colonnes métier hors PK
    assert gdf.geometry.iloc[1] is None


def test_write_geoparquet_roundtrip_preserves_crs_and_columns(tmp_path):
    rows = [ChangeRow(op="insert", lsn=1, ts=1.0, pk_column="id", pk_value=1,
                       columns={"id": 1, "titre": "a"}, geometry_column="geom",
                       geometry_wkb_hex=_hex(Point(0, 0)))]
    path = str(tmp_path / "part.parquet")
    write_geoparquet(rows, srid=2154, path=path)
    gdf = gpd.read_parquet(path)
    assert gdf.crs.to_epsg() == 2154
    assert len(gdf) == 1
    assert gdf["_op"].iloc[0] == "insert"
