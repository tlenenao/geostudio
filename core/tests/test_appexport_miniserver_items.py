# SPDX-License-Identifier: Apache-2.0
import pytest
from shapely import wkb as shapely_wkb
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_local_connection
from app.appexport.miniserver.items import MissingGeometryColumn, get_feature, select_features
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _write_fixture(tmp_path, *, tenant_id="t1", collection_id="col1"):
    rows = [
        ChangeRow(
            op="insert",
            lsn=0,
            ts=0.0,
            pk_column="id",
            pk_value=1,
            columns={"name": "Alpha"},
            geometry_column=None,
            geometry_wkb_hex=None,
        ),
        ChangeRow(
            op="insert",
            lsn=0,
            ts=0.0,
            pk_column="id",
            pk_value=2,
            columns={"name": "Beta"},
            geometry_column=None,
            geometry_wkb_hex=None,
        ),
    ]
    parquet_dir = (
        tmp_path / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=snapshot"
    )
    parquet_dir.mkdir(parents=True)
    write_geoparquet(rows, srid=4326, path=str(parquet_dir / "data.parquet"))
    return TableInfo(
        table_name="t_x",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )


def test_select_features_reads_snapshot(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="col1",
            table_info=table_info,
            limit=10,
            offset=0,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert sorted(f["properties"]["name"] for f in page.features) == ["Alpha", "Beta"]
    assert all(f["type"] == "Feature" for f in page.features)


def test_select_features_paginates(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="col1",
            table_info=table_info,
            limit=1,
            offset=1,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert page.number_returned == 1


def test_select_features_missing_collection_returns_empty_page(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="ghost",
            table_info=table_info,
            limit=10,
            offset=0,
        )
    finally:
        conn.close()
    assert page.features == []
    assert page.number_matched == 0


def test_get_feature_returns_single_row(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="col1",
            table_info=table_info,
            fid="2",
        )
    finally:
        conn.close()
    assert feature["properties"]["name"] == "Beta"


def test_select_features_reads_geometry_of_an_imported_collection(tmp_path):
    # RC-5, lecteur jumeau d'analytics.aggregate : le snapshot écrit la colonne
    # `geometry`, une collection importée a geometry_column="geom".
    row = ChangeRow(
        op="insert",
        lsn=0,
        ts=0.0,
        pk_column="id",
        pk_value=1,
        columns={"name": "Alpha"},
        geometry_column="geom",
        geometry_wkb_hex=shapely_wkb.dumps(Point(2.5, 48.5), hex=True),
    )
    part = tmp_path / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    part.mkdir(parents=True)
    write_geoparquet([row], srid=4326, path=str(part / "data.parquet"))
    info = TableInfo(
        table_name="t_x",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )
    conn = open_local_connection()
    try:
        page = select_features(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="col1",
            table_info=info,
            limit=10,
            offset=0,
            bbox=(2.0, 48.0, 3.0, 49.0),
        )
    finally:
        conn.close()
    assert page.number_matched == 1
    assert page.features[0]["geometry"]["coordinates"] == [2.5, 48.5]


def test_select_features_reprojects_a_non_4326_snapshot_to_lon_lat(tmp_path):
    """Reliquat SP-L0 : le lac est en SRID natif ; le mini-serveur sert du GeoJSON 4326 et
    filtre le bbox (4326) dans le même repère."""
    # Paris en Lambert-93 (EPSG:2154) : ~ (652469, 6862035).
    row = ChangeRow(
        op="insert",
        lsn=0,
        ts=0.0,
        pk_column="id",
        pk_value=1,
        columns={"name": "Paris"},
        geometry_column="geom",
        geometry_wkb_hex=shapely_wkb.dumps(Point(652469, 6862035), hex=True),
    )
    part = tmp_path / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    part.mkdir(parents=True)
    write_geoparquet([row], srid=2154, path=str(part / "data.parquet"))
    info = TableInfo(
        table_name="t_x",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=2154,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )
    conn = open_local_connection()
    try:
        common = dict(base_uri=str(tmp_path), tenant_id="t1", collection_id="col1", table_info=info)
        page = select_features(conn, **common, limit=10, offset=0, bbox=(2.0, 48.0, 3.0, 49.0))
        single = get_feature(conn, **common, fid="1")
    finally:
        conn.close()
    assert page.number_matched == 1
    lon, lat = page.features[0]["geometry"]["coordinates"]
    assert (round(lon, 2), round(lat, 2)) == (2.35, 48.86)
    assert single["geometry"]["coordinates"] == page.features[0]["geometry"]["coordinates"]


def test_get_feature_missing_returns_none(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn,
            base_uri=str(tmp_path),
            tenant_id="t1",
            collection_id="col1",
            table_info=table_info,
            fid="999",
        )
    finally:
        conn.close()
    assert feature is None


def test_select_features_bbox_on_non_spatial_raises_error(tmp_path):
    """Verify that spatial filters (bbox) on non-spatial collections raise MissingGeometryColumn."""
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        with pytest.raises(MissingGeometryColumn, match="collection has no geometry column"):
            select_features(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="col1",
                table_info=table_info,
                limit=10,
                offset=0,
                bbox=(0, 0, 1, 1),
            )
    finally:
        conn.close()


def test_select_features_geom_intersects_on_non_spatial_raises_error(tmp_path):
    """Verify that spatial filters (geom_intersects) on non-spatial collections
    raise MissingGeometryColumn."""
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        with pytest.raises(MissingGeometryColumn, match="collection has no geometry column"):
            select_features(
                conn,
                base_uri=str(tmp_path),
                tenant_id="t1",
                collection_id="col1",
                table_info=table_info,
                limit=10,
                offset=0,
                geom_intersects={"type": "Point", "coordinates": [0.5, 0.5]},
            )
    finally:
        conn.close()
