import pytest

from app.ingestion.parsers import (
    IngestionParseError, detect_lat_lon_fields, parse_csv_latlon, parse_geojson,
)


def test_parse_geojson_yields_geometry_and_properties():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,2.0]}}]}'
    )
    rows = list(parse_geojson(content))
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.geom_type == "Point"
    assert (geom.x, geom.y) == (1.0, 2.0)
    assert props == {"nom": "A"}


def test_parse_geojson_defaults_missing_properties_to_empty_dict():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"geometry":{"type":"Point","coordinates":[1.0,2.0]}}]}'
    )
    rows = list(parse_geojson(content))
    assert rows[0][1] == {}


def test_parse_geojson_rejects_malformed_json():
    with pytest.raises(IngestionParseError, match="JSON invalide"):
        list(parse_geojson(b"{not json"))


def test_parse_geojson_rejects_non_feature_collection():
    with pytest.raises(IngestionParseError, match="FeatureCollection"):
        list(parse_geojson(b'{"type":"Feature","properties":{},"geometry":null}'))


def test_parse_geojson_rejects_missing_geometry():
    content = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{}}]}'
    with pytest.raises(IngestionParseError, match="feature 0"):
        list(parse_geojson(content))


def test_detect_lat_lon_fields_case_insensitive():
    assert detect_lat_lon_fields(["Lat", "Lon"]) == ("Lat", "Lon")
    assert detect_lat_lon_fields(["latitude", "longitude"]) == ("latitude", "longitude")
    assert detect_lat_lon_fields(["nom", "valeur"]) is None


def test_parse_csv_latlon_auto_detects_columns():
    content = b"nom,lat,lon\nParis,48.85,2.35\n"
    rows = list(parse_csv_latlon(content, None, None))
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)
    assert props == {"nom": "Paris"}


def test_parse_csv_latlon_uses_explicit_field_names():
    content = b"nom,y_coord,x_coord\nParis,48.85,2.35\n"
    rows = list(parse_csv_latlon(content, "y_coord", "x_coord"))
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_csv_latlon_fails_fast_on_invalid_row():
    content = b"nom,lat,lon\nParis,48.85,2.35\nCasse,abc,2.35\n"
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_csv_latlon(content, None, None))


def test_parse_csv_latlon_raises_when_columns_cannot_be_detected():
    content = b"nom,valeur\nA,1\n"
    with pytest.raises(IngestionParseError, match="introuvables"):
        list(parse_csv_latlon(content, None, None))


def test_parse_geojson_rejects_unrecognized_geometry_type():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{},"geometry":{"type":"Unknown","coordinates":[1,2]}}]}'
    )
    with pytest.raises(IngestionParseError, match="feature 0"):
        list(parse_geojson(content))


def test_parse_geojson_rejects_non_dict_feature():
    content = b'{"type":"FeatureCollection","features":[1,2,3]}'
    with pytest.raises(IngestionParseError, match="feature 0 : entrée invalide"):
        list(parse_geojson(content))


def test_parse_geojson_rejects_invalid_utf8_content():
    content = b'{"type":"FeatureCollection","nom":"Cass\xe9", "features":[]}'
    with pytest.raises(IngestionParseError, match="encodage invalide"):
        list(parse_geojson(content))


def test_parse_csv_latlon_rejects_non_utf8_content():
    content = "nom,lat,lon\nCassé,48.85,2.35\n".encode("latin-1")
    with pytest.raises(IngestionParseError, match="encodage invalide"):
        list(parse_csv_latlon(content, None, None))


def test_parse_geojson_rejects_non_iterable_features():
    content = b'{"type":"FeatureCollection","features":5}'
    with pytest.raises(IngestionParseError, match="FeatureCollection"):
        list(parse_geojson(content))


def test_parse_csv_latlon_wraps_oversized_field_error():
    content = ("nom,lat,lon\n\"" + "x" * 200000 + "\n1,2\n").encode("utf-8")
    with pytest.raises(IngestionParseError, match="champ CSV trop volumineux ou mal formé"):
        list(parse_csv_latlon(content, None, None))


def test_parse_geojson_rejects_invalid_properties():
    content = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":[1,2],"geometry":{"type":"Point","coordinates":[1.0,2.0]}}]}'
    )
    with pytest.raises(IngestionParseError, match="feature 0 : properties invalide"):
        list(parse_geojson(content))
