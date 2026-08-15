# SPDX-License-Identifier: Apache-2.0
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.miniserver.items import get_feature, select_features
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _write_fixture(tmp_path, *, tenant_id="t1", collection_id="col1"):
    rows = [
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=1,
                  columns={"name": "Alpha"}, geometry_column=None, geometry_wkb_hex=None),
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=2,
                  columns={"name": "Beta"}, geometry_column=None, geometry_wkb_hex=None),
    ]
    parquet_dir = tmp_path / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(rows, srid=4326, path=str(parquet_dir / "data.parquet"))
    return TableInfo(
        table_name="t_x", pk_column="id", geometry_column=None, geometry_type=None, srid=4326,
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
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=10, offset=0,
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
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=1, offset=1,
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
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="ghost",
            table_info=table_info, limit=10, offset=0,
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
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="2",
        )
    finally:
        conn.close()
    assert feature["properties"]["name"] == "Beta"


def test_get_feature_missing_returns_none(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="999",
        )
    finally:
        conn.close()
    assert feature is None
