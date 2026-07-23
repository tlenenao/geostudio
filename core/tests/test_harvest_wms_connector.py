# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors import get_connector
from app.harvest.connectors.wms import WmsConnector

CAPS = "https://ows.example.com/geoserver/wms?service=WMS&request=GetCapabilities"
BASE = "https://ows.example.com/geoserver/wms"

WMS_130 = b"""<?xml version="1.0"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <CRS>EPSG:3857</CRS>
      <Layer>
        <Name>topp:states</Name>
        <Title>USA States</Title>
        <Abstract>Population par etat</Abstract>
        <KeywordList><Keyword>census</Keyword><Keyword>usa</Keyword></KeywordList>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-124.7</westBoundLongitude>
          <eastBoundLongitude>-66.9</eastBoundLongitude>
          <southBoundLatitude>24.9</southBoundLatitude>
          <northBoundLatitude>49.4</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer>
        <Name>topp:nomerc</Name>
        <Title>Sans WebMercator</Title>
        <CRS>EPSG:4326</CRS>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

WMS_111 = b"""<?xml version="1.0"?>
<WMT_MS_Capabilities version="1.1.1">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <SRS>EPSG:3857</SRS>
      <Layer>
        <Name>roads</Name>
        <Title>Routes</Title>
        <LatLonBoundingBox minx="2.0" miny="48.0" maxx="3.0" maxy="49.0"/>
      </Layer>
    </Layer>
  </Capability>
</WMT_MS_Capabilities>"""


def _connector(body: bytes) -> WmsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)
    return WmsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_named_layer_1_3_0_becomes_raster_record():
    records = list(_connector(WMS_130).fetch(CAPS))
    by_name = {r.title: r for r in records}
    # La couche-groupe racine (sans <Name>) n'est pas émise.
    assert "Racine" not in by_name
    states = by_name["USA States"]
    assert states.abstract == "Population par etat"
    assert states.keywords == ["census", "usa"]
    assert states.external_url == CAPS
    assert states.items_url is None
    assert states.raster_tiles_url is not None
    assert states.raster_tiles_url.startswith(
        f"{BASE}?service=WMS&version=1.3.0&request=GetMap&layers=topp:states"
    )
    assert "crs=EPSG:3857" in states.raster_tiles_url
    assert "{bbox-epsg-3857}" in states.raster_tiles_url
    assert -125 < states.bbox[0] < -124 and 24 < states.bbox[1] < 25


def test_layer_without_web_mercator_is_reference_only():
    records = list(_connector(WMS_130).fetch(CAPS))
    nomerc = next(r for r in records if r.title == "Sans WebMercator")
    assert nomerc.raster_tiles_url is None  # cataloguée mais non ajoutable


def test_wms_1_1_1_latlonbbox_and_srs():
    records = list(_connector(WMS_111).fetch(CAPS))
    roads = next(r for r in records if r.title == "Routes")
    assert roads.raster_tiles_url is not None  # EPSG:3857 hérité de la racine
    assert roads.bbox == [2.0, 48.0, 3.0, 49.0]


def test_fetch_copy_geojson_is_none():
    records = list(_connector(WMS_130).fetch(CAPS))
    assert records[0].raster_tiles_url is not None
    assert _connector(WMS_130).fetch_copy_geojson(records[0], http_get=lambda u: None) is None


def test_malformed_capabilities_returns_empty():
    assert list(_connector(b"<broken").fetch(CAPS)) == []


def test_get_connector_returns_wms():
    c = get_connector("wms")
    assert c.type == "wms"
    assert c.supports_copy is False
