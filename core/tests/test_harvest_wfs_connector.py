# SPDX-License-Identifier: Apache-2.0
import json

import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestedRecord, HarvestFetchError
from app.harvest.connectors.wfs import WfsConnector

CAPS = "https://ows.example.com/geoserver/wfs?service=WFS&request=GetCapabilities"
BASE = "https://ows.example.com/geoserver/wfs"

WFS_200 = b"""<?xml version="1.0"?>
<WFS_Capabilities version="2.0.0"
    xmlns="http://www.opengis.net/wfs/2.0"
    xmlns:ows="http://www.opengis.net/ows/1.1">
  <FeatureTypeList>
    <FeatureType>
      <Name>topp:tasmania_roads</Name>
      <Title>Routes Tasmanie</Title>
      <Abstract>Routes</Abstract>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>145.0 -43.6</ows:LowerCorner>
        <ows:UpperCorner>148.5 -40.5</ows:UpperCorner>
      </ows:WGS84BoundingBox>
    </FeatureType>
  </FeatureTypeList>
</WFS_Capabilities>"""


def _connector(body: bytes) -> WfsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return WfsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_feature_type_becomes_vector_record():
    r = list(_connector(WFS_200).fetch(CAPS))[0]
    assert r.title == "Routes Tasmanie"
    assert r.abstract == "Routes"
    assert r.raster_tiles_url is None
    assert r.external_url == CAPS
    assert r.items_url == (
        f"{BASE}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeNames=topp:tasmania_roads&outputFormat=application/json&srsName=EPSG:4326"
    )
    assert r.bbox == [145.0, -43.6, 148.5, -40.5]


def test_raises_when_capabilities_unreachable():
    # GAP-59.2 (SP-50) : le seul appel racine (GetCapabilities) est
    # injoignable — doit être signalé, jamais rapporté comme un
    # moissonnage réussi à zéro enregistrement.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    connector = WfsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(HarvestFetchError):
        list(connector.fetch(CAPS))


def _feature(i):
    return {
        "type": "Feature",
        "properties": {"n": i},
        "geometry": {"type": "Point", "coordinates": [float(i), 0.0]},
    }


def test_copy_geojson_paginates_via_startindex_count():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{BASE}?service=WFS&request=GetFeature&typeNames=t&outputFormat=application/json",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        if "startIndex=0" in url:
            return httpx.Response(
                200, json={"type": "FeatureCollection", "features": [_feature(0), _feature(1)]}
            )
        if "startIndex=2" in url:
            return httpx.Response(
                200, json={"type": "FeatureCollection", "features": [_feature(2)]}
            )
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    content = WfsConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert [f["properties"]["n"] for f in fc["features"]] == [0, 1, 2]
    assert all("startIndex=" in c and "count=" in c for c in calls)


def test_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=None,
    )
    assert WfsConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_copy_geojson_stops_cleanly_on_malformed_page():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{BASE}?request=GetFeature",
    )

    def http_get(url: str) -> httpx.Response:
        if "startIndex=0" in url:
            return httpx.Response(
                200, json={"type": "FeatureCollection", "features": [_feature(0)]}
            )
        return httpx.Response(200, json={"features": "not-a-list"})

    fc = json.loads(WfsConnector().fetch_copy_geojson(rec, http_get=http_get))
    assert [f["properties"]["n"] for f in fc["features"]] == [0]


def test_copy_geojson_bounded_by_max_pages():
    from app.harvest.connectors.wfs import _MAX_COPY_PAGES

    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{BASE}?request=GetFeature",
    )
    seen = {"n": 0}

    def http_get(url: str) -> httpx.Response:
        seen["n"] += 1
        # Toujours une page pleine → sans borne, boucle infinie.
        return httpx.Response(
            200, json={"type": "FeatureCollection", "features": [_feature(0)] * 1000}
        )

    json.loads(WfsConnector().fetch_copy_geojson(rec, http_get=http_get))
    assert seen["n"] <= _MAX_COPY_PAGES


def test_get_connector_returns_wfs():
    c = get_connector("wfs")
    assert c.type == "wfs"
    assert c.supports_copy is True
