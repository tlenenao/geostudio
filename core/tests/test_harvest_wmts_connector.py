# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors import get_connector
from app.harvest.connectors.wmts import WmtsConnector

CAPS = "https://ows.example.com/wmts?service=WMTS&request=GetCapabilities"
BASE = "https://ows.example.com/wmts"

# Deux TileMatrixSet : un WebMercator à identifiants entiers, un non-mercator.
WMTS = b"""<?xml version="1.0"?>
<Capabilities version="1.0.0"
    xmlns="http://www.opengis.net/wmts/1.0"
    xmlns:ows="http://www.opengis.net/ows/1.1"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <Contents>
    <Layer>
      <ows:Identifier>orthophoto</ows:Identifier>
      <ows:Title>Orthophoto</ows:Title>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>-5.0 41.0</ows:LowerCorner>
        <ows:UpperCorner>10.0 52.0</ows:UpperCorner>
      </ows:WGS84BoundingBox>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <TileMatrixSetLink><TileMatrixSet>PM</TileMatrixSet></TileMatrixSetLink>
      <ResourceURL format="image/png" resourceType="tile"
        template="https://ows.example.com/wmts/orthophoto/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"/>
    </Layer>
    <Layer>
      <ows:Identifier>plan_lambert</ows:Identifier>
      <ows:Title>Plan Lambert</ows:Title>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>-5.0 41.0</ows:LowerCorner>
        <ows:UpperCorner>10.0 52.0</ows:UpperCorner>
      </ows:WGS84BoundingBox>
      <TileMatrixSetLink><TileMatrixSet>LAMB93</TileMatrixSet></TileMatrixSetLink>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>PM</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>
      <TileMatrix><ows:Identifier>0</ows:Identifier></TileMatrix>
      <TileMatrix><ows:Identifier>1</ows:Identifier></TileMatrix>
    </TileMatrixSet>
    <TileMatrixSet>
      <ows:Identifier>LAMB93</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::2154</ows:SupportedCRS>
      <TileMatrix><ows:Identifier>0</ows:Identifier></TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""

# Variante sans ResourceURL (→ gabarit KVP GetTile).
WMTS_KVP = WMTS.replace(
    b'<ResourceURL format="image/png" resourceType="tile"\n'
    b'        template="https://ows.example.com/wmts/orthophoto/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"/>',
    b"",
)


def _connector(body: bytes) -> WmtsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)
    return WmtsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_resource_url_template_becomes_zyx():
    records = list(_connector(WMTS).fetch(CAPS))
    ortho = next(r for r in records if r.title == "Orthophoto")
    assert ortho.raster_tiles_url == (
        "https://ows.example.com/wmts/orthophoto/default/PM/{z}/{y}/{x}.png"
    )
    assert ortho.bbox == [-5.0, 41.0, 10.0, 52.0]
    assert ortho.external_url == CAPS
    assert ortho.items_url is None


def test_non_mercator_layer_is_reference_only():
    records = list(_connector(WMTS).fetch(CAPS))
    lamb = next(r for r in records if r.title == "Plan Lambert")
    assert lamb.raster_tiles_url is None


def test_kvp_gettile_template_when_no_resource_url():
    records = list(_connector(WMTS_KVP).fetch(CAPS))
    ortho = next(r for r in records if r.title == "Orthophoto")
    assert ortho.raster_tiles_url is not None
    url = ortho.raster_tiles_url
    assert url.startswith(f"{BASE}?service=WMTS")
    assert "request=GetTile" in url and "layer=orthophoto" in url
    assert "tilematrixset=PM" in url
    assert "tilematrix={z}" in url and "tilerow={y}" in url and "tilecol={x}" in url


def test_fetch_copy_geojson_is_none():
    assert _connector(WMTS).fetch_copy_geojson(
        list(_connector(WMTS).fetch(CAPS))[0], http_get=lambda u: None
    ) is None


def test_malformed_returns_empty():
    assert list(_connector(b"<nope").fetch(CAPS)) == []


def test_get_connector_returns_wmts():
    c = get_connector("wmts")
    assert c.type == "wmts"
    assert c.supports_copy is False
