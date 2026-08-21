# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.ogc_records import OgcRecordsConnector

OGC_ROOT = "https://records.example.com/api"

COLLECTIONS = {"collections": [{"id": "buildings"}, {"id": "roads"}]}

ITEMS_BUILDINGS_P1 = {
    "type": "FeatureCollection",
    "features": [
        {
            "id": "rec-1",
            "properties": {
                "title": "Batiments centre-ville",
                "description": "Empreintes",
                "keywords": ["bati", "centre"],
            },
            "bbox": [1.0, 45.0, 2.0, 46.0],
            "links": [
                {
                    "rel": "self",
                    "href": "https://records.example.com/api/collections/buildings/items/rec-1",
                }
            ],
        },
    ],
    "links": [
        {
            "rel": "next",
            "href": "https://records.example.com/api/collections/buildings/items?limit=100&offset=100",
        }
    ],
}
ITEMS_BUILDINGS_P2 = {
    "type": "FeatureCollection",
    "features": [{"id": "rec-2", "properties": {"title": "Batiments peripherie"}}],
    "links": [],
}
ITEMS_ROADS_P1 = {
    "type": "FeatureCollection",
    "features": [{"id": "rec-3", "properties": {"title": "Routes"}}],
    "links": [],
}


def _connector(handler) -> OgcRecordsConnector:
    return OgcRecordsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_collections_and_items_maps_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=COLLECTIONS)
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(200, json=ITEMS_BUILDINGS_P1)
        if (
            url
            == "https://records.example.com/api/collections/buildings/items?limit=100&offset=100"
        ):
            return httpx.Response(200, json=ITEMS_BUILDINGS_P2)
        if url == f"{OGC_ROOT}/collections/roads/items?limit=100":
            return httpx.Response(200, json=ITEMS_ROADS_P1)
        raise AssertionError(f"unexpected url {url}")

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-1", "rec-2", "rec-3"}

    rec1 = next(r for r in records if r.external_id == "rec-1")
    assert rec1.title == "Batiments centre-ville"
    assert rec1.abstract == "Empreintes"
    assert rec1.keywords == ["bati", "centre"]
    assert rec1.bbox == [1.0, 45.0, 2.0, 46.0]
    assert rec1.external_url == "https://records.example.com/api/collections/buildings/items/rec-1"
    assert rec1.items_url is None
    assert rec1.raster_tiles_url is None

    rec2 = next(r for r in records if r.external_id == "rec-2")
    assert rec2.title == "Batiments peripherie"
    assert rec2.abstract == ""
    assert rec2.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec2.external_url == f"{OGC_ROOT}/collections/buildings/items?limit=100"


def test_root_url_trailing_slash_is_stripped():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{OGC_ROOT}/collections"
        return httpx.Response(200, json={"collections": []})

    assert list(_connector(handler).fetch(f"{OGC_ROOT}/")) == []


def test_malformed_collections_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert list(_connector(handler).fetch(OGC_ROOT)) == []


def test_collection_first_page_failure_is_ignored_others_continue():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=COLLECTIONS)
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(500)
        if url == f"{OGC_ROOT}/collections/roads/items?limit=100":
            return httpx.Response(200, json=ITEMS_ROADS_P1)
        raise AssertionError(url)

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-3"}


def test_next_page_failure_keeps_partial_for_collection():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "buildings"}]})
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(200, json=ITEMS_BUILDINGS_P1)
        return httpx.Response(500)  # page suivante (offset=100) echoue

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-1"}


def test_feature_without_id_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "x"}]})
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [{"properties": {"title": "no id"}}],
                "links": [],
            },
        )

    assert list(_connector(handler).fetch(OGC_ROOT)) == []


def test_pages_per_collection_capped():
    from app.harvest.connectors.ogc_records import _MAX_OGC_PAGES_PER_COLLECTION

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "x"}]})
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [{"id": f"r{calls['n']}"}],
                "links": [
                    {
                        "rel": "next",
                        "href": f"{OGC_ROOT}/collections/x/items?limit=100&offset={calls['n']}",
                    }
                ],
            },
        )

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert calls["n"] <= _MAX_OGC_PAGES_PER_COLLECTION
    assert len(records) == calls["n"]


def test_collections_capped_at_max():
    from app.harvest.connectors.ogc_records import _MAX_OGC_COLLECTIONS

    many = {"collections": [{"id": f"c{i}"} for i in range(80)]}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=many)
        cid = url.split("/collections/")[1].split("/items")[0]
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [{"id": f"{cid}-rec"}],
                "links": [],
            },
        )

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert len(records) == _MAX_OGC_COLLECTIONS


def test_fetch_copy_geojson_is_none():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=None,
    )
    assert OgcRecordsConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_get_connector_returns_ogc_records():
    from app.harvest.connectors import get_connector

    c = get_connector("ogc-records")
    assert c.type == "ogc-records"
    assert c.supports_copy is False
