# SPDX-License-Identifier: Apache-2.0
import json

import openpyxl
import pytest

from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    features_to_format,
    rows_to_format,
)


def test_rows_to_format_csv_has_header_and_data_rows():
    content = rows_to_format([{"region": "Nord", "pop": 10}, {"region": "Sud", "pop": 5}], format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "region,pop"
    assert "Nord,10" in text


def test_rows_to_format_csv_empty_rows_is_empty_bytes():
    assert rows_to_format([], format="csv") == b""


def test_rows_to_format_xlsx_round_trips_through_openpyxl():
    content = rows_to_format([{"region": "Nord", "pop": 10}], format="xlsx")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows == [("region", "pop"), ("Nord", 10)]


def test_rows_to_format_rejects_geojson():
    with pytest.raises(ValueError):
        rows_to_format([{"a": 1}], format="geojson")


def test_features_to_format_geojson_wraps_a_feature_collection():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="geojson")
    body = json.loads(content)
    assert body == {"type": "FeatureCollection", "features": features}


def test_features_to_format_csv_flattens_properties_and_drops_geometry():
    features = [{"type": "Feature", "properties": {"nom": "X", "pop": 3}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "nom,pop"
    assert "geometry" not in text


def test_features_to_format_gpkg_requires_a_connection():
    with pytest.raises(AssertionError):
        features_to_format([{"type": "Feature", "properties": {}, "geometry": None}], format="gpkg")


def test_features_to_format_gpkg_round_trips_a_point():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}]
    conn = open_spatial_connection()
    try:
        content = features_to_format(features, format="gpkg", conn=conn)
        assert content[:16] == b"SQLite format 3\x00"
        read_back = open_spatial_connection()
        try:
            with open("/tmp/sp16a_test.gpkg", "wb") as f:
                f.write(content)
            row = read_back.execute("SELECT nom FROM ST_Read('/tmp/sp16a_test.gpkg')").fetchone()
            assert row[0] == "X"
        finally:
            read_back.close()
    finally:
        conn.close()


def test_export_filename_slugifies_the_title_and_appends_the_format():
    name = export_filename("Bâtiments (2026)", format="csv")
    assert name.startswith("batiments-2026")
    assert name.endswith(".csv")


def test_export_filename_falls_back_to_export_for_an_empty_title():
    assert export_filename("", format="xlsx").startswith("export")


def test_export_media_types_cover_all_four_formats():
    assert set(EXPORT_MEDIA_TYPES) == {"csv", "xlsx", "geojson", "gpkg"}
