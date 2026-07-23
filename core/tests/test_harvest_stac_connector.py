# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.stac import StacConnector

API_COLLECTIONS = {
    "collections": [
        {
            "id": "buildings",
            "title": "Bâtiments",
            "description": "Empreintes de bâtiments",
            "keywords": ["bati", "urbain"],
            "extent": {"spatial": {"bbox": [[1.0, 45.0, 2.0, 46.0]]}},
            "links": [
                {"rel": "self", "href": "https://stac.example.com/collections/buildings"},
                {"rel": "items", "href": "https://stac.example.com/collections/buildings/items"},
            ],
        },
        {
            "id": "roads",
            # title/description/keywords/extent absents : tolérance §2.7.
            "links": [],
        },
    ],
}

CATALOG_ROOT = {
    "type": "Catalog",
    "id": "root",
    "links": [
        {"rel": "child", "href": "https://stac.example.com/child-collection.json"},
        {"rel": "child", "href": "https://stac.example.com/child-catalog.json"},
    ],
}

CHILD_COLLECTION = {
    "type": "Collection",
    "id": "parcels",
    "title": "Parcelles",
    "description": "Parcelles cadastrales",
    "keywords": ["cadastre"],
    "extent": {"spatial": {"bbox": [[3.0, 47.0, 4.0, 48.0]]}},
    "links": [
        {"rel": "self", "href": "https://stac.example.com/child-collection.json"},
        {"rel": "items", "href": "https://stac.example.com/child-collection/items"},
    ],
}

CHILD_CATALOG = {
    "type": "Catalog",
    "id": "sub",
    "links": [
        {"rel": "child", "href": "https://stac.example.com/grandchild-collection.json"},
    ],
}

GRANDCHILD_COLLECTION = {
    "type": "Collection",
    "id": "trails",
    "title": "Sentiers",
    "description": "Sentiers de randonnée",
    "links": [
        {"rel": "self", "href": "https://stac.example.com/grandchild-collection.json"},
        {"rel": "items", "href": "https://stac.example.com/grandchild-collection/items"},
    ],
}

CYCLIC_CATALOG = {
    "type": "Catalog",
    "id": "cyclic",
    "links": [{"rel": "child", "href": "https://stac.example.com/cyclic.json"}],
}


def _connector(handler) -> StacConnector:
    transport = httpx.MockTransport(handler)
    return StacConnector(client=httpx.Client(transport=transport))


def test_fetch_api_collections_endpoint_maps_all_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://stac.example.com/collections"
        return httpx.Response(200, json=API_COLLECTIONS)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert len(records) == 2
    buildings = next(r for r in records if r.external_id == "buildings")
    assert buildings.title == "Bâtiments"
    assert buildings.abstract == "Empreintes de bâtiments"
    assert buildings.keywords == ["bati", "urbain"]
    assert buildings.bbox == [1.0, 45.0, 2.0, 46.0]
    assert buildings.external_url == "https://stac.example.com/collections/buildings"
    assert buildings.items_url == "https://stac.example.com/collections/buildings/items"


def test_fetch_tolerates_missing_optional_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=API_COLLECTIONS)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    roads = next(r for r in records if r.external_id == "roads")
    assert roads.title == "roads"
    assert roads.abstract == ""
    assert roads.keywords == []
    assert roads.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert roads.items_url is None


def test_fetch_follows_static_catalog_child_links_recursively():
    docs = {
        "https://stac.example.com/catalog.json": CATALOG_ROOT,
        "https://stac.example.com/child-collection.json": CHILD_COLLECTION,
        "https://stac.example.com/child-catalog.json": CHILD_CATALOG,
        "https://stac.example.com/grandchild-collection.json": GRANDCHILD_COLLECTION,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=docs[str(request.url)])

    records = list(_connector(handler).fetch("https://stac.example.com/catalog.json"))
    assert {r.external_id for r in records} == {"parcels", "trails"}


def test_fetch_terminates_on_cyclic_catalog_links():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=CYCLIC_CATALOG)

    records = list(_connector(handler).fetch("https://stac.example.com/cyclic.json"))
    assert records == []


def test_fetch_caps_number_of_collections():
    many = {"collections": [
        {"id": f"c{i}", "title": f"C{i}", "links": []} for i in range(600)
    ]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=many)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert len(records) == 500


def test_fetch_returns_empty_on_http_error_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert records == []


def test_fetch_skips_malformed_collection_entries_and_keeps_valid_ones():
    payload = {
        "collections": [
            {
                "id": "buildings",
                "title": "Bâtiments",
                "links": [{"rel": "self", "href": "https://stac.example.com/collections/buildings"}],
            },
            None,
            {"id": "bad-bbox", "extent": {"spatial": {"bbox": [["a", "b", "c", "d"]]}}},
            "not-a-dict",
            {
                "id": "roads",
                "title": "Routes",
                "links": [{"rel": "self", "href": "https://stac.example.com/collections/roads"}],
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert {r.external_id for r in records} == {"buildings", "roads"}


def test_fetch_returns_empty_on_non_object_top_level_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert records == []


def test_fetch_returns_empty_on_null_top_level_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=None)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert records == []


def test_fetch_coerces_non_list_keywords_to_empty_list():
    payload = {"collections": [{"id": "x", "title": "X", "keywords": "not-a-list", "links": []}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    records = list(_connector(handler).fetch("https://stac.example.com/collections"))
    assert len(records) == 1
    assert records[0].keywords == []


def test_get_connector_returns_stac_connector():
    connector = get_connector("stac")
    assert connector.type == "stac"
    assert connector.supports_copy is True


def test_get_connector_unknown_type_raises():
    with pytest.raises(ValueError):
        get_connector("arcgis-fs")


def test_stac_fetch_copy_geojson_single_get_returns_bytes():
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, content=b'{"type":"FeatureCollection","features":[]}')

    rec = HarvestedRecord(
        external_id="c", title="C", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://stac.example.com/collections/c",
        items_url="https://stac.example.com/collections/c/items",
    )
    content = StacConnector().fetch_copy_geojson(rec, http_get=http_get)
    assert content == b'{"type":"FeatureCollection","features":[]}'
    assert calls == ["https://stac.example.com/collections/c/items"]


def test_stac_fetch_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="c", title="C", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://stac.example.com/collections/c", items_url=None,
    )
    called = []
    assert StacConnector().fetch_copy_geojson(rec, http_get=lambda u: called.append(u)) is None
    assert called == []


def test_stac_walk_caps_total_documents():
    # Un catalogue en éventail large : un Catalog racine liant plus de
    # _MAX_DOCUMENTS enfants Collection. _MAX_DOCUMENTS borne le nombre total
    # de GET, arrêt propre au plafond (§4.1).
    from app.harvest.connectors.stac import _MAX_DOCUMENTS

    n_children = _MAX_DOCUMENTS + 50
    root = {
        "type": "Catalog", "id": "root",
        "links": [
            {"rel": "child", "href": f"https://stac.example.com/c{i}.json"}
            for i in range(n_children)
        ],
    }
    seen = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["count"] += 1
        url = str(request.url)
        if url.endswith("root.json"):
            return httpx.Response(200, json=root)
        cid = url.rsplit("/", 1)[-1].removesuffix(".json")
        return httpx.Response(200, json={
            "type": "Collection", "id": cid, "title": cid,
            "links": [{"rel": "self", "href": url}],
        })

    list(_connector(handler).fetch("https://stac.example.com/root.json"))
    assert seen["count"] <= _MAX_DOCUMENTS
