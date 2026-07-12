import warnings
import zipfile

import numpy as np
import pytest
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point

from app.ingestion.parsers import (
    IngestionParseError, LayerInfo, detect_lat_lon_fields, list_layers,
    parse_csv_latlon, parse_geojson, parse_gpkg, parse_shapefile_zip,
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


def _gpkg_bytes(tmp_path, *, layer="entites", crs="EPSG:4326", points=None, fields=None):
    points = points or [(1.0, 2.0), (3.0, 4.0)]
    fields = fields or {"nom": np.array(["A", "B"][: len(points)], dtype=object)}
    path = tmp_path / f"{layer}.gpkg"
    geometry = shapely.to_wkb(np.array([Point(x, y) for x, y in points], dtype=object))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyogrio avertit si crs=None (cas volontaire d'un test)
        pyogrio_write(
            str(path), geometry=geometry, field_data=list(fields.values()),
            fields=list(fields.keys()), layer=layer, geometry_type="Point", crs=crs,
        )
    return path.read_bytes()


def _shapefile_zip_bytes(tmp_path) -> bytes:
    shp_path = tmp_path / "villes.shp"
    geometry = shapely.to_wkb(np.array([Point(1.0, 45.0), Point(2.0, 46.0)], dtype=object))
    pyogrio_write(
        str(shp_path), geometry=geometry, field_data=[np.array(["A", "B"], dtype=object)],
        fields=["nom"], geometry_type="Point", crs="EPSG:4326",
    )
    zip_path = tmp_path / "villes.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):
            p = tmp_path / f"villes.{ext}"
            if p.exists():
                z.write(p, arcname=p.name)
    return zip_path.read_bytes()


def test_list_layers_single_layer_gpkg(tmp_path):
    content = _gpkg_bytes(tmp_path)
    layers = list_layers(content, "villes.gpkg")
    assert layers == [LayerInfo(name="entites", feature_count=2, geometry_type="Point")]


def test_list_layers_multi_layer_gpkg(tmp_path):
    path = tmp_path / "multi.gpkg"
    geom = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["A"], dtype=object)],
                  fields=["nom"], layer="a", geometry_type="Point", crs="EPSG:4326")
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["B"], dtype=object)],
                  fields=["nom"], layer="b", geometry_type="Point", crs="EPSG:4326")
    layers = list_layers(path.read_bytes(), "multi.gpkg")
    assert {l.name for l in layers} == {"a", "b"}
    assert all(l.feature_count == 1 for l in layers)


def test_list_layers_shapefile_zip_names_layer_from_shp(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    layers = list_layers(content, "villes.zip")
    assert layers == [LayerInfo(name="villes", feature_count=2, geometry_type="Point")]


def test_list_layers_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="non concerné"):
        list_layers(b"nom,lat,lon\n", "villes.csv")


def test_list_layers_corrupted_file_raises_parse_error():
    with pytest.raises(IngestionParseError, match="illisible"):
        list_layers(b"not a real gpkg", "villes.gpkg")


def test_parse_gpkg_yields_geometry_and_properties(tmp_path):
    content = _gpkg_bytes(tmp_path)
    rows = list(parse_gpkg(content, "entites"))
    assert len(rows) == 2
    geom0, props0 = rows[0]
    assert geom0.geom_type == "Point"
    assert (geom0.x, geom0.y) == (1.0, 2.0)
    assert props0 == {"nom": "A"}


def test_parse_gpkg_auto_selects_layer_when_only_one(tmp_path):
    content = _gpkg_bytes(tmp_path)
    rows = list(parse_gpkg(content, layer_name=None))
    assert len(rows) == 2


def test_parse_gpkg_requires_explicit_layer_when_multiple(tmp_path):
    path = tmp_path / "multi.gpkg"
    geom = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["A"], dtype=object)],
                  fields=["nom"], layer="a", geometry_type="Point", crs="EPSG:4326")
    pyogrio_write(str(path), geometry=geom, field_data=[np.array(["B"], dtype=object)],
                  fields=["nom"], layer="b", geometry_type="Point", crs="EPSG:4326")
    with pytest.raises(IngestionParseError, match="plusieurs couches"):
        list(parse_gpkg(path.read_bytes(), layer_name=None))


def test_parse_gpkg_rejects_unknown_layer_name(tmp_path):
    content = _gpkg_bytes(tmp_path)
    with pytest.raises(IngestionParseError, match="introuvable"):
        list(parse_gpkg(content, "n-existe-pas"))


def test_parse_gpkg_normalizes_numpy_scalars_and_nan(tmp_path):
    content = _gpkg_bytes(tmp_path, fields={
        "nom": np.array(["A", "B"], dtype=object),
        "population": np.array([10, 20], dtype="int64"),
        "score": np.array([1.5, np.nan], dtype="float64"),
    })
    rows = list(parse_gpkg(content, "entites"))
    _, props0 = rows[0]
    assert props0 == {"nom": "A", "population": 10, "score": 1.5}
    assert isinstance(props0["population"], int)
    _, props1 = rows[1]
    assert props1["score"] is None


def test_parse_gpkg_reprojects_non_wgs84_crs(tmp_path):
    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
    x, y = transformer.transform(2.35, 48.85)
    content = _gpkg_bytes(
        tmp_path, crs="EPSG:2154", points=[(x, y)],
        fields={"nom": np.array(["Paris"], dtype=object)},
    )
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert geom.x == pytest.approx(2.35, abs=1e-6)
    assert geom.y == pytest.approx(48.85, abs=1e-6)


def test_parse_gpkg_skips_transform_when_already_wgs84(tmp_path):
    content = _gpkg_bytes(tmp_path, crs="EPSG:4326", points=[(2.35, 48.85)],
                           fields={"nom": np.array(["Paris"], dtype=object)})
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_gpkg_missing_crs_fails_fast(tmp_path):
    content = _gpkg_bytes(tmp_path, crs=None)
    with pytest.raises(IngestionParseError, match="CRS"):
        list(parse_gpkg(content, "entites"))


def test_parse_shapefile_zip_yields_geometry_and_properties(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    rows = list(parse_shapefile_zip(content, "villes"))
    assert len(rows) == 2
    geom0, props0 = rows[0]
    assert geom0.geom_type == "Point"
    assert props0 == {"nom": "A"}


def test_parse_shapefile_zip_auto_selects_single_layer(tmp_path):
    content = _shapefile_zip_bytes(tmp_path)
    rows = list(parse_shapefile_zip(content, layer_name=None))
    assert len(rows) == 2
