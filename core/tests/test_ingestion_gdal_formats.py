# ruff: noqa: E501
"""ARC-23 : FileGDB, DXF, MapInfo TAB/MIF, DGN via GDAL (pyogrio) ; VRT refusé (REV-333)."""

import io
import os
import warnings
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from app.ingestion.importer import _pick_format
from app.ingestion.parsers import (
    IngestionParseError,
    list_layers,
    parse_dgn,
    parse_dxf,
    parse_filegdb_zip,
    parse_gpkg,
    parse_shapefile_zip,
)

warnings.simplefilter("ignore")


def _zip_tree(root: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for r, _dirs, files in os.walk(root):
            for f in files:
                p = os.path.join(r, f)
                z.write(p, os.path.relpath(p, os.path.dirname(root)))
    return buf.getvalue()


@pytest.fixture
def gdb_zip(tmp_path) -> bytes:
    g = str(tmp_path / "parcelles.gdb")
    pts = gpd.GeoDataFrame({"nom": ["a", "b"]}, geometry=[Point(2, 48), Point(3, 49)], crs=4326)
    pol = gpd.GeoDataFrame(
        {"nom": ["p"]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])],
        crs=4326,
    )
    lin = gpd.GeoDataFrame({"nom": ["l"]}, geometry=[LineString([(0, 0), (1, 1)])], crs=4326)
    pts.to_file(g, driver="OpenFileGDB", layer="points")
    pol.to_file(g, driver="OpenFileGDB", layer="polygones")
    lin.to_file(g, driver="OpenFileGDB", layer="lignes")
    return _zip_tree(g)


def test_filegdb_three_layers_listed_and_valid(gdb_zip):
    layers = list_layers(gdb_zip, "parcelles.gdb.zip")
    assert {layer.name for layer in layers} == {"points", "polygones", "lignes"}
    rows = list(parse_filegdb_zip(gdb_zip, "polygones"))
    assert len(rows) == 1
    geom, props = rows[0]
    assert geom.is_valid and geom.geom_type == "MultiPolygon"  # FileGDB type les surfaces en multi
    assert props["nom"] == "p"


def test_filegdb_requires_layer_choice_when_several(gdb_zip):
    with pytest.raises(IngestionParseError, match="plusieurs couches"):
        list(parse_filegdb_zip(gdb_zip, None))


def test_filegdb_zip_without_gdb_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "x")
    with pytest.raises(IngestionParseError):
        list(parse_filegdb_zip(buf.getvalue(), None))


def test_mapinfo_tab_zip_is_imported(tmp_path):
    gdf = gpd.GeoDataFrame({"nom": ["a", "b"]}, geometry=[Point(2, 48), Point(3, 49)], crs=4326)
    gdf.to_file(str(tmp_path / "m.tab"), driver="MapInfo File")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in os.listdir(tmp_path):
            z.write(tmp_path / f, f)
    rows = list(parse_shapefile_zip(buf.getvalue(), None))
    assert [p["nom"] for _g, p in rows] == ["a", "b"]
    assert rows[0][0].x == pytest.approx(2)


def test_mapinfo_mif_mid_zip_is_imported(tmp_path):
    gdf = gpd.GeoDataFrame({"nom": ["a"]}, geometry=[Point(2, 48)], crs=4326)
    gdf.to_file(str(tmp_path / "m.mif"), driver="MapInfo File", FORMAT="MIF")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in os.listdir(tmp_path):
            z.write(tmp_path / f, f)
    rows = list(parse_shapefile_zip(buf.getvalue(), None))
    assert rows[0][1]["nom"] == "a"


def test_dgn_v7_is_imported(tmp_path):
    p = tmp_path / "d.dgn"
    gpd.GeoDataFrame(geometry=[LineString([(2, 48), (3, 49)])], crs=4326).to_file(
        str(p), driver="DGN"
    )
    rows = list(parse_dgn(p.read_bytes()))
    assert rows and rows[0][0].geom_type == "LineString"


def test_dxf_without_crs_in_wgs84_range_is_imported(tmp_path):
    p = tmp_path / "d.dxf"
    gpd.GeoDataFrame(geometry=[LineString([(2, 48), (3, 49)])], crs=4326).to_file(
        str(p), driver="DXF"
    )
    rows = list(parse_dxf(p.read_bytes()))
    assert len(rows) == 1 and rows[0][0].geom_type == "LineString"


def test_dxf_local_coordinates_without_crs_are_refused(tmp_path):
    p = tmp_path / "d.dxf"
    gpd.GeoDataFrame(
        geometry=[LineString([(652000, 6862000), (652100, 6862100)])], crs=2154
    ).to_file(str(p), driver="DXF")
    with pytest.raises(IngestionParseError, match="CRS"):
        list(parse_dxf(p.read_bytes()))


def test_pick_format_new_extensions():
    assert _pick_format("a.dxf") == "dxf"
    assert _pick_format("a.dgn") == "dgn"
    assert _pick_format("a.gdb.zip") == "filegdb"
    assert _pick_format("a.zip") == "shapefile"


VRT = (
    b'<OGRVRTDataSource><OGRVRTLayer name="x"><SrcDataSource>/etc/passwd</SrcDataSource>'
    b"<SrcLayer>s</SrcLayer></OGRVRTLayer></OGRVRTDataSource>"
)


@pytest.mark.parametrize("fn", [parse_gpkg, parse_dxf])
def test_vrt_disguised_is_refused(fn):
    with pytest.raises(IngestionParseError, match="VRT"):
        list(fn(VRT))


def test_vrt_inside_zip_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.vrt", VRT)
    with pytest.raises(IngestionParseError, match="VRT"):
        list(parse_shapefile_zip(buf.getvalue(), None))
    with pytest.raises(IngestionParseError, match="VRT"):
        list_layers(buf.getvalue(), "x.zip")


def test_vrt_extension_is_not_a_supported_format():
    with pytest.raises(IngestionParseError):
        _pick_format("x.vrt")


GML_COMPLEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs" xmlns:gml="http://www.opengis.net/gml" xmlns:ad="urn:ad">
 <gml:featureMember><ad:Address gml:id="a1"><ad:name>Rue A</ad:name>
   <ad:tags>x</ad:tags><ad:tags>y</ad:tags>
   <ad:owner><ad:nom>Dupont</ad:nom></ad:owner>
   <ad:geom><gml:Point srsName="EPSG:4326"><gml:pos>2 48</gml:pos></gml:Point></ad:geom>
 </ad:Address></gml:featureMember>
 <gml:featureMember><ad:Road gml:id="r1"><ad:name>R</ad:name>
   <ad:geom><gml:LineString srsName="EPSG:4326"><gml:posList>2 48 3 49</gml:posList></gml:LineString></ad:geom>
 </ad:Road></gml:featureMember>
</wfs:FeatureCollection>"""


def test_gml_complex_multilayer_nested_and_list_attributes():
    from app.ingestion.parsers import parse_gml

    assert {layer.name for layer in list_layers(GML_COMPLEX, "a.gml")} == {"Address", "Road"}
    ((geom, props),) = parse_gml(GML_COMPLEX, "Address")
    assert props["nom"] == "Dupont"  # élément imbriqué aplati
    assert props["tags"] == '["x", "y"]'  # liste -> texte JSON insérable
    assert geom.geom_type == "Point"


def test_gpkg_invalid_polygon_is_repaired(tmp_path):
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    path = tmp_path / "bad.gpkg"
    gpd.GeoDataFrame({"n": [1]}, geometry=[bowtie], crs="EPSG:4326").to_file(path, driver="GPKG")
    rows = list(parse_gpkg(path.read_bytes()))
    assert len(rows) == 1 and rows[0][0].is_valid


def test_flatgeobuf_is_imported_and_signature_checked(tmp_path):
    from app.ingestion.parsers import parse_flatgeobuf

    p = tmp_path / "x.fgb"
    gdf = gpd.GeoDataFrame({"nom": ["a", "b"]}, geometry=[Point(2, 48), Point(3, 49)], crs=4326)
    gdf.to_file(p, driver="FlatGeobuf")
    assert _pick_format("x.fgb") == "flatgeobuf"
    rows = list(parse_flatgeobuf(p.read_bytes()))
    assert sorted(r[1]["nom"] for r in rows) == ["a", "b"]  # l'index spatial réordonne
    with pytest.raises(IngestionParseError):
        list(parse_flatgeobuf(b"not a flatgeobuf"))
