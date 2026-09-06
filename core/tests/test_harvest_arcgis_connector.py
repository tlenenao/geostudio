# SPDX-License-Identifier: Apache-2.0
import json

import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestedRecord, HarvestFetchError

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer"

SERVICE_META = {
    "layers": [{"id": 0, "name": "Bâtiments"}, {"id": 1, "name": "Routes"}],
    "documentInfo": {"Keywords": "bati,urbain"},
}
LAYER_0 = {
    "id": 0,
    "name": "Bâtiments",
    "description": "Empreintes",
    "geometryType": "esriGeometryPolygon",
    "maxRecordCount": 2000,
    "extent": {
        "xmin": 647850.0,
        "ymin": 6861300.0,
        "xmax": 647950.0,
        "ymax": 6861400.0,
        "spatialReference": {"latestWkid": 2154},
    },
}
LAYER_1 = {"id": 1, "name": "Routes", "extent": None}


def _handler(docs):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert "f=json" in url
        base = url.split("?")[0]
        return httpx.Response(200, json=docs[base])

    return handler


def _connector(docs) -> ArcgisConnector:
    transport = httpx.MockTransport(_handler(docs))
    return ArcgisConnector(client=httpx.Client(transport=transport))


def test_fetch_maps_each_layer_to_a_record():
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    assert {r.external_id for r in records} == {f"{SERVICE}/0", f"{SERVICE}/1"}
    b = next(r for r in records if r.external_id == f"{SERVICE}/0")
    assert b.title == "Bâtiments"
    assert b.abstract == "Empreintes"
    assert b.keywords == ["bati", "urbain"]
    assert b.external_url == f"{SERVICE}/0"
    assert b.items_url == f"{SERVICE}/0/query?where=1=1&outFields=*&f=geojson"


def test_fetch_reprojects_non_4326_extent_to_wgs84():
    # EPSG:2154 (Lambert-93, région parisienne) → WGS84 ~ (2.29°, 48.85°).
    # Échoue si on retire pyproj (les coords brutes 647850 ne sont pas du WGS84).
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    b = next(r for r in records if r.external_id == f"{SERVICE}/0")
    assert 2.0 < b.bbox[0] < 3.0
    assert 48.0 < b.bbox[1] < 49.0
    assert 2.0 < b.bbox[2] < 3.0
    assert 48.0 < b.bbox[3] < 49.0


def test_fetch_layer_without_extent_gets_world_bbox():
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    r = next(r for r in records if r.external_id == f"{SERVICE}/1")
    assert r.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert r.title == "Routes"


def test_fetch_no_layers_key_returns_empty():
    docs = {SERVICE: {"description": "no layers here"}}
    assert list(_connector(docs).fetch(SERVICE)) == []


def test_fetch_non_object_service_response_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    transport = httpx.MockTransport(handler)
    assert list(ArcgisConnector(client=httpx.Client(transport=transport)).fetch(SERVICE)) == []


def test_fetch_raises_when_root_service_document_unreachable():
    # GAP-59.2 (SP-50) : le tout premier appel (métadonnées du service,
    # depth "racine") injoignable doit être signalé — distinct des couches
    # (par-layer) qui restent tolérantes, cf.
    # test_fetch_layer_meta_error_skips_that_layer ci-dessous, inchangé.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    connector = ArcgisConnector(client=httpx.Client(transport=transport))
    with pytest.raises(HarvestFetchError):
        list(connector.fetch(SERVICE))


def test_fetch_layer_meta_error_skips_that_layer():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        base = url.split("?")[0]
        if base == SERVICE:
            return httpx.Response(200, json=SERVICE_META)
        if base == f"{SERVICE}/0":
            return httpx.Response(200, json=LAYER_0)
        return httpx.Response(500)  # couche 1 en erreur

    transport = httpx.MockTransport(handler)
    records = list(ArcgisConnector(client=httpx.Client(transport=transport)).fetch(SERVICE))
    assert {r.external_id for r in records} == {f"{SERVICE}/0"}


def test_fetch_caps_number_of_layers():
    from app.harvest.connectors.arcgis import _MAX_LAYERS

    n = _MAX_LAYERS + 20
    meta = {"layers": [{"id": i, "name": f"L{i}"} for i in range(n)]}
    docs = {SERVICE: meta}
    for i in range(n):
        docs[f"{SERVICE}/{i}"] = {"id": i, "name": f"L{i}", "extent": None}
    records = list(_connector(docs).fetch(SERVICE))
    assert len(records) <= _MAX_LAYERS


def test_get_connector_returns_arcgis_connector():
    c = get_connector("arcgis")
    assert c.type == "arcgis"
    assert c.supports_copy is True


def _page(features, *, exceeded):
    return {"type": "FeatureCollection", "features": features, "exceededTransferLimit": exceeded}


def _feature(i):
    return {
        "type": "Feature",
        "properties": {"n": i},
        "geometry": {"type": "Point", "coordinates": [i, i]},
    }


def test_copy_geojson_assembles_all_pages():
    rec = HarvestedRecord(
        external_id=f"{SERVICE}/0",
        title="B",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url=f"{SERVICE}/0",
        items_url=f"{SERVICE}/0/query?where=1=1&outFields=*&f=geojson",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        if "resultOffset=0" in url:
            return httpx.Response(200, json=_page([_feature(0), _feature(1)], exceeded=True))
        return httpx.Response(200, json=_page([_feature(2)], exceeded=False))

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert fc["type"] == "FeatureCollection"
    assert [f["properties"]["n"] for f in fc["features"]] == [0, 1, 2]
    assert len(calls) == 2
    assert all("resultOffset=" in c and "resultRecordCount=" in c for c in calls)


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
    assert ArcgisConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_copy_geojson_truncates_at_max_features():
    from app.harvest.connectors.arcgis import _MAX_COPY_FEATURES

    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{SERVICE}/0/query?f=geojson",
    )

    def http_get(url: str) -> httpx.Response:
        # Chaque page renvoie une page pleine et prétend qu'il en reste : sans
        # plafond, la boucle serait infinie.
        return httpx.Response(200, json=_page([_feature(0)] * 500, exceeded=True))

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert len(fc["features"]) <= _MAX_COPY_FEATURES


def test_copy_geojson_caps_number_of_pages():
    from app.harvest.connectors.arcgis import _MAX_COPY_PAGES

    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{SERVICE}/0/query?f=geojson",
    )
    calls = {"n": 0}

    def http_get(url: str) -> httpx.Response:
        # 1 feature/page, always claims more remain: without a page cap this
        # would run _MAX_COPY_FEATURES (200k) GETs. The page cap must stop it.
        calls["n"] += 1
        return httpx.Response(200, json=_page([_feature(0)], exceeded=True))

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert calls["n"] <= _MAX_COPY_PAGES
    assert len(fc["features"]) <= _MAX_COPY_PAGES  # 1 feature/page, capped by pages


def test_copy_geojson_stops_cleanly_on_malformed_page():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{SERVICE}/0/query?f=geojson",
    )

    def http_get(url: str) -> httpx.Response:
        if "resultOffset=0" in url:
            return httpx.Response(200, json=_page([_feature(0)], exceeded=True))
        return httpx.Response(200, json={"features": "not-a-list"})  # malformé

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert [f["properties"]["n"] for f in fc["features"]] == [0]
