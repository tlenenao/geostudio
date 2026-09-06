# SPDX-License-Identifier: Apache-2.0
import datetime
import io
import warnings
import zipfile

import numpy as np
import pytest
import shapely
from openpyxl import Workbook
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point

from app.ingestion.parsers import (
    IngestionParseError,
    LayerInfo,
    detect_lat_lon_fields,
    list_layers,
    parse_csv_latlon,
    parse_geojson,
    parse_geoparquet,
    parse_gpkg,
    parse_kml,
    parse_shapefile_zip,
    parse_xlsx_latlon,
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
    content = ('nom,lat,lon\n"' + "x" * 200000 + "\n1,2\n").encode("utf-8")
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
            str(path),
            geometry=geometry,
            field_data=list(fields.values()),
            fields=list(fields.keys()),
            layer=layer,
            geometry_type="Point",
            crs=crs,
        )
    return path.read_bytes()


def _shapefile_zip_bytes(tmp_path) -> bytes:
    shp_path = tmp_path / "villes.shp"
    geometry = shapely.to_wkb(np.array([Point(1.0, 45.0), Point(2.0, 46.0)], dtype=object))
    pyogrio_write(
        str(shp_path),
        geometry=geometry,
        field_data=[np.array(["A", "B"], dtype=object)],
        fields=["nom"],
        geometry_type="Point",
        crs="EPSG:4326",
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
    pyogrio_write(
        str(path),
        geometry=geom,
        field_data=[np.array(["A"], dtype=object)],
        fields=["nom"],
        layer="a",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    pyogrio_write(
        str(path),
        geometry=geom,
        field_data=[np.array(["B"], dtype=object)],
        fields=["nom"],
        layer="b",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    layers = list_layers(path.read_bytes(), "multi.gpkg")
    assert {layer.name for layer in layers} == {"a", "b"}
    assert all(layer.feature_count == 1 for layer in layers)


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
    pyogrio_write(
        str(path),
        geometry=geom,
        field_data=[np.array(["A"], dtype=object)],
        fields=["nom"],
        layer="a",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    pyogrio_write(
        str(path),
        geometry=geom,
        field_data=[np.array(["B"], dtype=object)],
        fields=["nom"],
        layer="b",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    with pytest.raises(IngestionParseError, match="plusieurs couches"):
        list(parse_gpkg(path.read_bytes(), layer_name=None))


def test_parse_gpkg_rejects_unknown_layer_name(tmp_path):
    content = _gpkg_bytes(tmp_path)
    with pytest.raises(IngestionParseError, match="introuvable"):
        list(parse_gpkg(content, "n-existe-pas"))


def test_parse_gpkg_normalizes_numpy_scalars_and_nan(tmp_path):
    content = _gpkg_bytes(
        tmp_path,
        fields={
            "nom": np.array(["A", "B"], dtype=object),
            "population": np.array([10, 20], dtype="int64"),
            "score": np.array([1.5, np.nan], dtype="float64"),
        },
    )
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
        tmp_path,
        crs="EPSG:2154",
        points=[(x, y)],
        fields={"nom": np.array(["Paris"], dtype=object)},
    )
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert geom.x == pytest.approx(2.35, abs=1e-6)
    assert geom.y == pytest.approx(48.85, abs=1e-6)


def test_parse_gpkg_skips_transform_when_already_wgs84(tmp_path):
    content = _gpkg_bytes(
        tmp_path,
        crs="EPSG:4326",
        points=[(2.35, 48.85)],
        fields={"nom": np.array(["Paris"], dtype=object)},
    )
    rows = list(parse_gpkg(content, "entites"))
    geom, _props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_gpkg_missing_crs_fails_fast(tmp_path):
    content = _gpkg_bytes(tmp_path, crs=None)
    with pytest.raises(IngestionParseError, match="CRS"):
        list(parse_gpkg(content, "entites"))


def test_parse_gpkg_untransformable_crs_fails_fast(tmp_path):
    # ENGCRS (engineering/site-local CRS) : accepté par pyproj.CRS.from_user_input
    # mais sans chemin de transformation vers WGS84 — pyproj.Transformer.from_crs
    # lève ProjError, distinct de CRSError levé plus tôt pour un CRS non reconnu.
    eng_wkt = (
        'ENGCRS["Site Local CRS",'
        'EDATUM["Site Datum"],'
        "CS[Cartesian,2],"
        'AXIS["easting (X)",east,ORDER[1],LENGTHUNIT["metre",1]],'
        'AXIS["northing (Y)",north,ORDER[2],LENGTHUNIT["metre",1]]]'
    )
    content = _gpkg_bytes(tmp_path, crs=eng_wkt)
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


def _xlsx_bytes(rows: list[list], headers: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_xlsx_latlon_auto_detects_columns():
    content = _xlsx_bytes([["Paris", 48.85, 2.35]], ["nom", "lat", "lon"])
    rows = list(parse_xlsx_latlon(content, None, None))
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)
    assert props == {"nom": "Paris"}


def test_parse_xlsx_latlon_uses_explicit_field_names():
    content = _xlsx_bytes([["Paris", 48.85, 2.35]], ["nom", "y_coord", "x_coord"])
    rows = list(parse_xlsx_latlon(content, "y_coord", "x_coord"))
    geom, _props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_xlsx_latlon_raises_when_columns_cannot_be_detected():
    content = _xlsx_bytes([["A", 1]], ["nom", "valeur"])
    with pytest.raises(IngestionParseError, match="introuvables"):
        list(parse_xlsx_latlon(content, None, None))


def test_parse_xlsx_latlon_fails_fast_on_invalid_row():
    content = _xlsx_bytes([["Paris", 48.85, 2.35], ["Casse", "abc", 2.35]], ["nom", "lat", "lon"])
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_xlsx_latlon(content, None, None))


def test_parse_xlsx_latlon_serializes_datetime_property_to_iso_string():
    when = datetime.datetime(2026, 9, 5, 10, 30)
    content = _xlsx_bytes([["Paris", 48.85, 2.35, when]], ["nom", "lat", "lon", "maj"])
    rows = list(parse_xlsx_latlon(content, None, None))
    _geom, props = rows[0]
    assert props["maj"] == when.isoformat()
    assert isinstance(props["maj"], str)


def test_parse_xlsx_latlon_empty_cell_becomes_none_property():
    content = _xlsx_bytes([["Paris", 48.85, 2.35, None]], ["nom", "lat", "lon", "notes"])
    rows = list(parse_xlsx_latlon(content, None, None))
    _geom, props = rows[0]
    assert props["notes"] is None


def _kml_bytes(name: str = "Paris", lon: float = 2.35, lat: float = 48.85) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<Placemark><name>{name}</name>"
        f"<Point><coordinates>{lon},{lat},0</coordinates></Point>"
        "</Placemark></Document></kml>"
    ).encode()


def _kmz_bytes(name: str = "Paris", lon: float = 2.35, lat: float = 48.85) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", _kml_bytes(name, lon, lat))
    return buf.getvalue()


def test_parse_kml_yields_geometry_and_properties():
    rows = list(parse_kml(_kml_bytes()))
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.geom_type == "Point"
    assert (geom.x, geom.y) == pytest.approx((2.35, 48.85))
    assert props["Name"] == "Paris"


def test_parse_kmz_yields_same_result_as_kml_without_vsizip():
    # Un .kmz est un zip contenant un doc.kml, mais se lit DIRECTEMENT par
    # pyogrio (driver LIBKML détecté sur l'extension .kmz elle-même) —
    # contrairement à .zip (Shapefile) qui exige le préfixe /vsizip/. Si le
    # code préfixait /vsizip/ sur ce chemin par erreur, GDAL lèverait "n'est
    # pas un fichier kmz valide" et ce test échouerait (cf. Step 3 du plan).
    rows = list(parse_kml(_kmz_bytes()))
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == pytest.approx((2.35, 48.85))
    assert props["Name"] == "Paris"


def test_parse_kml_corrupted_file_raises_parse_error():
    with pytest.raises(IngestionParseError, match="illisible"):
        list(parse_kml(b"not a real kml"))


def test_list_layers_kml_single_layer():
    layers = list_layers(_kml_bytes(), "villes.kml")
    assert len(layers) == 1
    assert layers[0].feature_count == 1


def test_list_layers_kmz_single_layer():
    layers = list_layers(_kmz_bytes(), "villes.kmz")
    assert len(layers) == 1
    assert layers[0].feature_count == 1


def test_parse_geoparquet_yields_geometry_and_attributes(tmp_path):
    import geopandas as gpd

    gdf = gpd.GeoDataFrame(
        {"nom": ["Paris", "Lyon"]},
        geometry=[Point(2.35, 48.85), Point(4.83, 45.76)],
        crs="EPSG:4326",
    )
    path = tmp_path / "villes.parquet"
    gdf.to_parquet(path)
    rows = list(parse_geoparquet(path.read_bytes()))
    assert len(rows) == 2
    geom0, props0 = rows[0]
    assert geom0.geom_type == "Point"
    assert (geom0.x, geom0.y) == pytest.approx((2.35, 48.85))
    assert props0 == {"nom": "Paris"}


def test_parse_geoparquet_reprojects_non_4326_crs(tmp_path):
    import geopandas as gpd
    import pyproj

    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
    x, y = transformer.transform(2.35, 48.85)
    gdf = gpd.GeoDataFrame({"nom": ["Paris"]}, geometry=[Point(x, y)], crs="EPSG:2154")
    path = tmp_path / "villes.parquet"
    gdf.to_parquet(path)
    rows = list(parse_geoparquet(path.read_bytes()))
    geom, _props = rows[0]
    assert geom.x == pytest.approx(2.35, abs=1e-6)
    assert geom.y == pytest.approx(48.85, abs=1e-6)


def test_parse_geoparquet_rejects_null_geometry(tmp_path):
    import geopandas as gpd

    gdf = gpd.GeoDataFrame(
        {"nom": ["Paris", "Sans géométrie"]},
        geometry=[Point(2.35, 48.85), None],
        crs="EPSG:4326",
    )
    path = tmp_path / "villes.parquet"
    gdf.to_parquet(path)
    with pytest.raises(IngestionParseError, match="géométrie"):
        list(parse_geoparquet(path.read_bytes()))


def test_parse_geoparquet_round_trips_write_geoparquet_output(tmp_path):
    from app.cdc.parquet_writer import ChangeRow, write_geoparquet

    rows = [
        ChangeRow(
            op="insert",
            lsn=1,
            ts=1721212121.0,
            pk_column="id",
            pk_value=1,
            columns={"id": 1, "titre": "a"},
            geometry_column="geom",
            geometry_wkb_hex=shapely.to_wkb(Point(2.3, 48.8), hex=True),
        ),
    ]
    path = tmp_path / "batch.parquet"
    write_geoparquet(rows, srid=4326, path=str(path))
    parsed = list(parse_geoparquet(path.read_bytes()))
    assert len(parsed) == 1
    geom, props = parsed[0]
    assert (geom.x, geom.y) == pytest.approx((2.3, 48.8))
    assert props["titre"] == "a"
    assert props["_op"] == "insert"
    assert props["id"] == 1
