# SPDX-License-Identifier: Apache-2.0
import contextlib
import datetime
import io
import json
import warnings
import zipfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
import shapely
from openpyxl import Workbook
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point

from app.ingestion.parsers import (
    GeometryMode,
    IngestionParseError,
    LayerInfo,
    _is_geoparquet,
    _is_geoparquet_from_bytes,
    detect_lat_lon_fields,
    extract_geometry,
    list_layers,
    list_xlsx_sheets,
    parse_csv_latlon,
    parse_geojson,
    parse_geoparquet,
    parse_gml,
    parse_gpkg,
    parse_jsonlines,
    parse_kml,
    parse_parquet_tabular,
    parse_shapefile_zip,
    parse_xlsx_sheet,
    parse_xml_generic,
    read_jsonlines_header_fields,
    read_parquet_header_fields,
    read_xlsx_header_fields,
    read_xml_header_fields,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


def test_extract_geometry_latlon_mode():
    geom, props = extract_geometry(
        {"lat": "48.85", "lon": "2.35", "name": "Paris"},
        GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"),
    )
    assert geom.equals(Point(2.35, 48.85))
    assert props == {"name": "Paris"}


def test_extract_geometry_latlon_mode_invalid_value_fails_fast():
    with pytest.raises(IngestionParseError, match="lat/lon invalide"):
        extract_geometry(
            {"lat": "not-a-number", "lon": "2.35"},
            GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"),
        )


def test_extract_geometry_wkt_mode():
    geom, props = extract_geometry(
        {"wkt": "POINT (2.35 48.85)", "name": "Paris"},
        GeometryMode(kind="wkt", wkt_field="wkt"),
    )
    assert geom.equals(Point(2.35, 48.85))
    assert props == {"name": "Paris"}


def test_extract_geometry_wkt_mode_invalid_value_fails_fast():
    with pytest.raises(IngestionParseError, match="WKT invalide"):
        extract_geometry({"wkt": "NOT WKT"}, GeometryMode(kind="wkt", wkt_field="wkt"))


def test_extract_geometry_wkt_mode_none_value_fails_fast():
    with pytest.raises(IngestionParseError, match="WKT invalide"):
        extract_geometry(
            {"wkt": None, "name": "Paris"},
            GeometryMode(kind="wkt", wkt_field="wkt"),
        )


def test_extract_geometry_wkt_mode_missing_column_fails_fast():
    with pytest.raises(IngestionParseError, match="WKT invalide"):
        extract_geometry(
            {"name": "Paris"},
            GeometryMode(kind="wkt", wkt_field="wkt"),
        )


def test_extract_geometry_none_mode_keeps_all_properties():
    geom, props = extract_geometry(
        {"name": "Paris", "population": 2148000},
        GeometryMode(kind="none"),
    )
    assert geom is None
    assert props == {"name": "Paris", "population": 2148000}


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
    rows = list(
        parse_csv_latlon(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)
    assert props == {"nom": "Paris"}


def test_parse_csv_latlon_uses_explicit_field_names():
    content = b"nom,y_coord,x_coord\nParis,48.85,2.35\n"
    rows = list(
        parse_csv_latlon(
            content, GeometryMode(kind="latlon", lat_field="y_coord", lon_field="x_coord")
        )
    )
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_csv_latlon_fails_fast_on_invalid_row():
    content = b"nom,lat,lon\nParis,48.85,2.35\nCasse,abc,2.35\n"
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_csv_latlon(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None)))


def test_parse_csv_latlon_raises_when_columns_cannot_be_detected():
    content = b"nom,valeur\nA,1\n"
    with pytest.raises(IngestionParseError, match="introuvables"):
        list(parse_csv_latlon(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None)))


def test_parse_csv_latlon_wkt_mode_yields_geometry():
    content = b"name,wkt\nA,POINT (1 2)\nB,POINT (3 4)\n"
    rows = list(parse_csv_latlon(content, GeometryMode(kind="wkt", wkt_field="wkt")))
    assert len(rows) == 2
    assert rows[0][0].equals(Point(1, 2))
    assert rows[0][1] == {"name": "A"}


def test_parse_csv_latlon_wkt_mode_invalid_wkt_fails_fast():
    content = b"name,wkt\nA,NOT WKT\n"
    with pytest.raises(IngestionParseError, match="ligne 1"):
        list(parse_csv_latlon(content, GeometryMode(kind="wkt", wkt_field="wkt")))


def test_parse_csv_latlon_none_mode_yields_no_geometry():
    content = b"name,value\nA,1\nB,2\n"
    rows = list(parse_csv_latlon(content, GeometryMode(kind="none")))
    assert len(rows) == 2
    assert rows[0][0] is None
    assert rows[0][1] == {"name": "A", "value": "1"}


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
        list(parse_csv_latlon(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None)))


def test_parse_geojson_rejects_non_iterable_features():
    content = b'{"type":"FeatureCollection","features":5}'
    with pytest.raises(IngestionParseError, match="FeatureCollection"):
        list(parse_geojson(content))


def test_parse_csv_latlon_wraps_oversized_field_error():
    content = ('nom,lat,lon\n"' + "x" * 200000 + "\n1,2\n").encode("utf-8")
    with pytest.raises(IngestionParseError, match="champ CSV trop volumineux ou mal formé"):
        list(parse_csv_latlon(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None)))


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


def test_parse_xlsx_sheet_auto_detects_columns():
    content = _xlsx_bytes([["Paris", 48.85, 2.35]], ["nom", "lat", "lon"])
    rows = list(
        parse_xlsx_sheet(content, None, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    assert len(rows) == 1
    geom, props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)
    assert props == {"nom": "Paris"}


def test_parse_xlsx_sheet_uses_explicit_field_names():
    content = _xlsx_bytes([["Paris", 48.85, 2.35]], ["nom", "y_coord", "x_coord"])
    rows = list(
        parse_xlsx_sheet(
            content, None, GeometryMode(kind="latlon", lat_field="y_coord", lon_field="x_coord")
        )
    )
    geom, _props = rows[0]
    assert (geom.x, geom.y) == (2.35, 48.85)


def test_parse_xlsx_sheet_raises_when_columns_cannot_be_detected():
    content = _xlsx_bytes([["A", 1]], ["nom", "valeur"])
    with pytest.raises(IngestionParseError, match="introuvables"):
        list(
            parse_xlsx_sheet(
                content, None, GeometryMode(kind="latlon", lat_field=None, lon_field=None)
            )
        )


def test_parse_xlsx_sheet_fails_fast_on_invalid_row():
    content = _xlsx_bytes([["Paris", 48.85, 2.35], ["Casse", "abc", 2.35]], ["nom", "lat", "lon"])
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(
            parse_xlsx_sheet(
                content, None, GeometryMode(kind="latlon", lat_field=None, lon_field=None)
            )
        )


def test_parse_xlsx_sheet_serializes_datetime_property_to_iso_string():
    when = datetime.datetime(2026, 9, 5, 10, 30)
    content = _xlsx_bytes([["Paris", 48.85, 2.35, when]], ["nom", "lat", "lon", "maj"])
    rows = list(
        parse_xlsx_sheet(content, None, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    _geom, props = rows[0]
    assert props["maj"] == when.isoformat()
    assert isinstance(props["maj"], str)


def test_parse_xlsx_sheet_empty_cell_becomes_none_property():
    content = _xlsx_bytes([["Paris", 48.85, 2.35, None]], ["nom", "lat", "lon", "notes"])
    rows = list(
        parse_xlsx_sheet(content, None, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    _geom, props = rows[0]
    assert props["notes"] is None


def test_parse_xlsx_sheet_corrupted_file_raises_parse_error():
    with pytest.raises(IngestionParseError, match="illisible"):
        list(
            parse_xlsx_sheet(
                b"not a real xlsx",
                None,
                GeometryMode(kind="latlon", lat_field=None, lon_field=None),
            )
        )


def test_list_xlsx_sheets_multi_sheet_workbook():
    content = (_FIXTURES / "TwoSheetsNoneHidden.xlsx").read_bytes()
    sheets = list_xlsx_sheets(content)
    assert len(sheets) >= 2
    assert all(s.geometry_type == "Tabular" for s in sheets)
    assert all(s.feature_count >= 0 for s in sheets)


def test_list_xlsx_sheets_single_sheet_workbook_returns_one_entry(tmp_path):
    wb = Workbook()
    wb.active.append(["name", "value"])
    wb.active.append(["A", 1])
    path = tmp_path / "single.xlsx"
    wb.save(path)
    sheets = list_xlsx_sheets(path.read_bytes())
    assert len(sheets) == 1


def test_list_xlsx_sheets_corrupted_file_raises_parse_error():
    with pytest.raises(IngestionParseError, match="illisible"):
        list_xlsx_sheets(b"not a real xlsx")


def test_read_xlsx_header_fields_rejects_unknown_sheet_name():
    # Trouvaille de la revue finale de Task 5 (GAP-29) : depuis que
    # POST /uploads/inspect relaie InspectRequest.layerName tel quel à
    # read_xlsx_header_fields (routes.py), un sheet_name inconnu levait un
    # KeyError d'openpyxl non catché — 500 côté HTTP au lieu d'un 422
    # propre, seule fonction xlsx du module à ne pas déjà convertir ses
    # erreurs GDAL/openpyxl en IngestionParseError.
    content = (_FIXTURES / "TwoSheetsNoneHidden.xlsx").read_bytes()
    with pytest.raises(IngestionParseError, match="introuvable"):
        read_xlsx_header_fields(content, sheet_name="NoSuchSheet")


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


def test_parse_kml_renames_reserved_id_property():
    # Le driver KML de GDAL impose un champ "id" sur tout Placemark (son
    # attribut XML id="...", vide sinon), y compris sur un KML minimal sans
    # schéma personnalisé — vérifié par exécution réelle. Ce nom collide
    # avec la colonne "id" (PK serial) posée par run_import sur toute table
    # importée : sans renommage, tout import KML échouerait à la création
    # de table (voir aussi le test d'intégration bout en bout, Tâche 4).
    rows = list(parse_kml(_kml_bytes()))
    _geom, props = rows[0]
    assert "id" not in props
    assert "kml_id" in props


def test_rename_reserved_property_keys_applies_given_prefix():
    from app.ingestion.parsers import _rename_reserved_property_keys

    result = _rename_reserved_property_keys(
        {"id": "1", "tenant_id": "x", "geom": "y", "name": "ok"}, "jsonl"
    )
    assert result == {"jsonl_id": "1", "jsonl_tenant_id": "x", "jsonl_geom": "y", "name": "ok"}


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


def test_parse_gml_yields_geometry_and_properties_reprojected():
    content = (_FIXTURES / "archsites.gml").read_bytes()
    rows = list(parse_gml(content))
    assert len(rows) > 0
    geom, props = rows[0]
    # archsites.gml est en EPSG:26713 (non-WGS84) — vérifier que la
    # reprojection de _read_features s'est bien appliquée : les
    # coordonnées ne doivent plus être de l'ordre de 10^5-10^6 (UTM-like)
    # mais de l'ordre de longitudes/latitudes WGS84 plausibles pour
    # l'Ouest américain (le jeu de données archsites est du Colorado).
    assert -110 < geom.x < -100
    assert 35 < geom.y < 45
    # Les propriétés du fixture réel (§5 de la spec) : à vérifier au nom
    # local exact renvoyé par pyogrio (peut être "cat"/"str1" sans le
    # préfixe de namespace "og:" — à confirmer empiriquement ici).
    assert "cat" in props or "og:cat" in props


def test_list_layers_gml_single_layer():
    content = (_FIXTURES / "archsites.gml").read_bytes()
    layers = list_layers(content, "archsites.gml")
    assert len(layers) == 1
    assert layers[0].geometry_type == "Point"


def test_parse_gml_reserved_property_collision_check():
    """Vérifie empiriquement (piège CLAUDE.md n°3) si le driver GML de GDAL
    impose, comme KML, un champ 'id' — si oui, il doit être renommé
    'gml_id' (comme kml_id pour KML) plutôt que provoquer une collision
    SQL en aval (run_import, Task 11)."""
    content = (_FIXTURES / "archsites.gml").read_bytes()
    _geom, props = next(iter(parse_gml(content)))
    assert "id" not in props  # soit jamais présent, soit déjà renommé gml_id


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


def _write_tabular_parquet(path, rows: list[dict]):
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)  # aucune métadonnée "geo" — non-géo par construction


def test_is_geoparquet_false_for_plain_parquet(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}])
    assert _is_geoparquet(str(path)) is False


def test_is_geoparquet_true_for_existing_geoparquet_fixture(tmp_path):
    import geopandas as gpd

    gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[Point(1, 2)], crs="EPSG:4326")
    path = tmp_path / "geo.parquet"
    gdf.to_parquet(path)
    assert _is_geoparquet(str(path)) is True


def test_is_geoparquet_from_bytes_true_for_existing_geoparquet_fixture(tmp_path):
    import geopandas as gpd

    gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[Point(1, 2)], crs="EPSG:4326")
    path = tmp_path / "geo.parquet"
    gdf.to_parquet(path)
    assert _is_geoparquet_from_bytes(path.read_bytes()) is True


def test_is_geoparquet_from_bytes_false_for_plain_parquet(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}])
    assert _is_geoparquet_from_bytes(path.read_bytes()) is False


def test_parse_parquet_tabular_none_mode(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}, {"name": "B", "value": 2}])
    rows = list(parse_parquet_tabular(path.read_bytes(), GeometryMode(kind="none")))
    assert len(rows) == 2
    assert rows[0][0] is None
    assert rows[0][1] == {"name": "A", "value": 1}


def test_parse_parquet_tabular_serializes_nested_struct(tmp_path):
    path = tmp_path / "nested.parquet"
    _write_tabular_parquet(path, [{"name": "A", "tags": ["x", "y"]}])
    rows = list(parse_parquet_tabular(path.read_bytes(), GeometryMode(kind="none")))
    assert isinstance(rows[0][1]["tags"], str)
    assert json.loads(rows[0][1]["tags"]) == ["x", "y"]


def test_parse_parquet_tabular_latlon_auto_detected_from_field_names(tmp_path):
    """Revue finale GAP-29, C1 : même correctif que parse_jsonlines/
    parse_xml_generic — parse_parquet_tabular n'avait aucune étape de
    résolution de l'auto-détection lat/lon avant ce correctif."""
    path = tmp_path / "latlon.parquet"
    _write_tabular_parquet(path, [{"lat": 48.85, "lon": 2.35, "name": "Paris"}])
    rows = list(
        parse_parquet_tabular(
            path.read_bytes(), GeometryMode(kind="latlon", lat_field=None, lon_field=None)
        )
    )
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.equals(Point(2.35, 48.85))
    assert props["name"] == "Paris"


def test_read_parquet_header_fields(tmp_path):
    path = tmp_path / "plain.parquet"
    _write_tabular_parquet(path, [{"name": "A", "value": 1}])
    fields = read_parquet_header_fields(path.read_bytes())
    assert set(fields) == {"name", "value"}


# --- Suffixe de fichier temporaire : aucune donnée utilisateur ne doit
# atteindre un chemin du système de fichiers (alerte CodeQL py/path-injection
# sur app/ingestion/parsers.py, `_temp_file(content, suffix)`).


def test_list_layers_never_derives_its_temp_suffix_from_the_filename():
    """`list_layers` recevait le nom de fichier fourni par l'appelant
    (POST /uploads/inspect → body.filename) et en dérivait le suffixe du
    fichier temporaire par `lower[lower.rfind("."):]`. Le résultat était en
    pratique toujours ".kml" ou ".kmz" — le dernier point est forcément
    celui de l'extension puisque la branche est gardée par endswith() —
    donc non exploitable, mais un flux « entrée utilisateur → chemin » que
    rien dans le code ne bornait explicitement. Ce test fixe le contrat :
    le suffixe est choisi parmi deux littéraux, jamais découpé dans
    l'entrée."""
    from app.ingestion import parsers

    seen: list[str] = []
    real_temp_file = parsers._temp_file

    @contextmanager
    def _spy(content: bytes, suffix: str):
        seen.append(suffix)
        with real_temp_file(content, suffix) as path:
            yield path

    parsers._temp_file = _spy  # type: ignore[assignment]
    try:
        for filename in (
            "a.kml",
            "A.KMZ",
            "../../etc/passwd.kml",
            "x/../../tmp/evil.kmz",
            "un.nom.avec.des.points.kml",
        ):
            with contextlib.suppress(IngestionParseError):
                list_layers(b"pas un vrai kml", filename)
    finally:
        parsers._temp_file = real_temp_file  # type: ignore[assignment]

    assert seen, "list_layers n'a jamais appelé _temp_file"
    assert set(seen) <= {".kml", ".kmz"}, seen


@pytest.mark.parametrize(
    "suffix",
    [
        "/../../etc/passwd",
        "x/y.kml",
        ".kml/../../evil",
        "..",
    ],
)
def test_temp_file_refuses_a_suffix_that_is_not_a_bare_extension(suffix):
    """Défense en profondeur au point de passage unique : `_temp_file` est le
    seul endroit du domaine où un suffixe devient un chemin réel, et
    `tempfile.NamedTemporaryFile` ne filtre RIEN (un suffixe contenant « / »
    écrit hors du répertoire temporaire). Aucun appelant actuel ne peut y
    faire entrer une telle valeur ; ce garde existe pour que le prochain ne
    le puisse pas non plus en silence."""
    from app.ingestion.parsers import _temp_file

    with pytest.raises(ValueError, match="suffixe"):
        with _temp_file(b"x", suffix):
            pass


# --- JSON Lines (Task 8) --------------------------------------------------


def test_parse_jsonlines_scalar_and_nested_values():
    content = (_FIXTURES / "scifact_claims_sample.jsonl").read_bytes()
    rows = list(parse_jsonlines(content, GeometryMode(kind="none")))
    assert len(rows) == 10
    geom, props = rows[0]
    assert geom is None
    # collision réservée : la clé "id" du fixture doit être renommée
    assert "id" not in props
    assert "jsonl_id" in props
    # valeur imbriquée (dict/list) sérialisée en JSON compact, pas un objet
    # Python
    assert isinstance(props["evidence"], str)
    json.loads(props["evidence"])  # doit rester du JSON valide


def test_parse_jsonlines_rejects_malformed_line():
    content = b'{"a": 1}\nnot json\n'
    with pytest.raises(IngestionParseError, match="ligne 2"):
        list(parse_jsonlines(content, GeometryMode(kind="none")))


def test_parse_jsonlines_rejects_non_object_line():
    content = b'{"a": 1}\n[1, 2, 3]\n'
    with pytest.raises(IngestionParseError, match="objet JSON"):
        list(parse_jsonlines(content, GeometryMode(kind="none")))


def test_parse_jsonlines_latlon_mode():
    content = b'{"lat": 48.85, "lon": 2.35, "name": "Paris"}\n'
    rows = list(
        parse_jsonlines(content, GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"))
    )
    assert rows[0][0].equals(Point(2.35, 48.85))


def test_read_jsonlines_header_fields_samples_first_lines():
    content = (_FIXTURES / "scifact_claims_sample.jsonl").read_bytes()
    fields = read_jsonlines_header_fields(content, sample_lines=3)
    assert "id" in fields and "claim" in fields


def test_parse_jsonlines_latlon_auto_detected_from_field_names():
    """Revue finale GAP-29, C1 : le shell envoie lat_field=None/lon_field=None
    dès qu'il détecte lui-même des colonnes lat/lon-like et saute l'étape
    manuelle selecting-geometry (ImportFileButton.tsx::detectLatLon) —
    exactement le cas le plus courant en pratique. Avant le correctif,
    parse_jsonlines passait ce mode brut tel quel à extract_geometry, qui
    levait IngestionParseError("lat/lon invalide ('None', 'None')") sur
    toute ligne."""
    content = b'{"lat": 48.85, "lon": 2.35, "name": "Paris"}\n'
    rows = list(
        parse_jsonlines(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.equals(Point(2.35, 48.85))
    assert props["name"] == "Paris"


# --- XML générique (Task 10) -----------------------------------------------


def test_parse_xml_generic_detects_repeated_book_element():
    content = (_FIXTURES / "books.xml").read_bytes()
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert len(rows) > 1
    geom, props = rows[0]
    assert geom is None
    assert props["author"] == "Gambardella, Matthew"
    assert props["title"] == "XML Developer's Guide"
    # collision réservée : l'attribut id="bk101" doit être renommé xml_id
    assert "id" not in props
    assert props["xml_id"] == "bk101"
    # enfant texte multi-lignes : doit être strippé, pas laissé avec
    # l'indentation XML brute
    assert not props["description"].startswith("\n")


def test_parse_xml_generic_no_repeated_element_fails_fast():
    content = b"<root><a>1</a><b>2</b></root>"
    with pytest.raises(IngestionParseError, match="aucun élément répété"):
        list(parse_xml_generic(content, GeometryMode(kind="none")))


def test_parse_xml_generic_ignores_structured_children():
    content = b"""<catalog>
      <item><name>A</name><nested><x>1</x></nested></item>
      <item><name>B</name><nested><x>2</x></nested></item>
    </catalog>"""
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert len(rows) == 2
    assert "nested" not in rows[0][1]
    assert rows[0][1]["name"] == "A"


def test_local_name_strips_namespace_uri():
    content = b"""<ns:catalog xmlns:ns="http://example.org">
      <ns:item><ns:name>A</ns:name></ns:item>
      <ns:item><ns:name>B</ns:name></ns:item>
    </ns:catalog>"""
    rows = list(parse_xml_generic(content, GeometryMode(kind="none")))
    assert rows[0][1] == {"name": "A"}


def test_parse_xml_generic_latlon_mode():
    content = b"""<rows>
      <row><lat>48.85</lat><lon>2.35</lon></row>
      <row><lat>45.75</lat><lon>4.85</lon></row>
    </rows>"""
    rows = list(
        parse_xml_generic(content, GeometryMode(kind="latlon", lat_field="lat", lon_field="lon"))
    )
    assert rows[0][0].equals(Point(2.35, 48.85))


def test_parse_xml_generic_latlon_auto_detected_from_field_names():
    """Revue finale GAP-29, C1 : même correctif que parse_jsonlines — le
    shell envoie lat_field=None/lon_field=None dès qu'il auto-détecte des
    colonnes lat/lon-like, et parse_xml_generic n'avait aucune étape de
    résolution avant ce correctif."""
    content = b"""<rows>
      <row><lat>48.85</lat><lon>2.35</lon></row>
      <row><lat>45.75</lat><lon>4.85</lon></row>
    </rows>"""
    rows = list(
        parse_xml_generic(content, GeometryMode(kind="latlon", lat_field=None, lon_field=None))
    )
    assert len(rows) == 2
    assert rows[0][0].equals(Point(2.35, 48.85))


def test_parse_xml_generic_rejects_malformed_xml():
    content = b"<not valid xml"
    with pytest.raises(IngestionParseError, match="XML invalide"):
        list(parse_xml_generic(content, GeometryMode(kind="none")))


def test_parse_xml_generic_rejects_xxe_payload_without_crashing():
    """defusedxml lève defusedxml.common.EntitiesForbidden pour une entité
    externe (XXE) — PAS defusedxml.ElementTree.ParseError (vérifié par
    exécution réelle : EntitiesForbidden hérite de ValueError, pas de
    ParseError). Sans un except dédié, cette exception traverserait
    parse_xml_generic sans jamais devenir un IngestionParseError propre —
    piège CLAUDE.md n°3, à ne pas supposer sur la seule foi du nom de
    l'exception attendue par les tests de malformation."""
    content = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<foo>&xxe;</foo>"
    )
    with pytest.raises(IngestionParseError, match="XML invalide"):
        list(parse_xml_generic(content, GeometryMode(kind="none")))


def test_read_xml_header_fields():
    content = (_FIXTURES / "books.xml").read_bytes()
    fields = read_xml_header_fields(content)
    assert "author" in fields and "title" in fields and "xml_id" in fields
