# SPDX-License-Identifier: Apache-2.0
import json

import httpx

from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.ckan import CkanConnector

PORTAL = "https://demo.data.gouv.fr"
SEARCH = f"{PORTAL}/api/3/action/package_search"


def _search_response(results, *, count=None):
    return {
        "success": True,
        "result": {"count": count if count is not None else len(results), "results": results},
    }


def _pkg(**overrides):
    pkg = {
        "id": "pkg-1",
        "name": "batiments-ville",
        "title": "Bâtiments de la ville",
        "notes": "Empreintes de bâtiments",
        "tags": [{"name": "bati"}, {"name": "urbain"}],
        "resources": [],
    }
    pkg.update(overrides)
    return pkg


def _connector(handler) -> CkanConnector:
    return CkanConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_single_page_extracts_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(SEARCH)
        return httpx.Response(200, json=_search_response([_pkg()]))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "pkg-1"
    assert rec.title == "Bâtiments de la ville"
    assert rec.abstract == "Empreintes de bâtiments"
    assert rec.keywords == ["bati", "urbain"]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec.external_url == f"{PORTAL}/dataset/batiments-ville"
    assert rec.items_url is None
    assert rec.copy_filename is None
    assert rec.raster_tiles_url is None


def test_title_falls_back_to_name_and_external_url_to_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_search_response(
                [
                    _pkg(title=None, name=None, id="pkg-2"),
                ]
            ),
        )

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.title == "pkg-2"
    assert rec.external_url == f"{PORTAL}/dataset/pkg-2"


def test_package_without_id_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([_pkg(id=None)]))

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_pagination_merges_query_params_and_advances_start():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        calls.append(qs)
        assert qs["organization"] == "ville-x"
        assert qs["tags"] == "geo"
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg(id="p1", name="p1")], count=2))
        return httpx.Response(200, json=_search_response([_pkg(id="p2", name="p2")], count=2))

    records = list(_connector(handler).fetch(f"{PORTAL}?organization=ville-x&tags=geo"))
    assert [r.external_id for r in records] == ["p1", "p2"]
    assert [c["start"] for c in calls] == ["0", "1"]
    assert all(c["rows"] == "100" for c in calls)


def test_admin_url_start_and_rows_are_overridden_not_duplicated():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = request.url.params.multi_items()
        keys = [k for k, _ in qs]
        assert keys.count("start") == 1
        assert keys.count("rows") == 1
        return httpx.Response(200, json=_search_response([_pkg()]))

    list(_connector(handler).fetch(f"{PORTAL}?start=999&rows=5"))


def test_pagination_stops_when_count_exhausted():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_search_response([_pkg(id="only", name="only")], count=1))

    records = list(_connector(handler).fetch(PORTAL))
    assert calls["n"] == 1
    assert [r.external_id for r in records] == ["only"]


def test_pagination_stops_on_empty_page():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg()], count=999))
        return httpx.Response(200, json=_search_response([]))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == 1


def test_datasets_capped_at_max():
    from app.harvest.connectors.ckan import _MAX_CKAN_DATASETS

    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        start = int(qs["start"])
        page = [_pkg(id=f"p{start + i}", name=f"p{start + i}") for i in range(100)]
        return httpx.Response(200, json=_search_response(page, count=10_000))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == _MAX_CKAN_DATASETS


def test_pages_capped_at_max_when_page_barely_advances():
    from app.harvest.connectors.ckan import _MAX_CKAN_PAGES

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        qs = dict(request.url.params)
        start = int(qs["start"])
        return httpx.Response(
            200, json=_search_response([_pkg(id=f"p{start}", name=f"p{start}")], count=10_000)
        )

    records = list(_connector(handler).fetch(PORTAL))
    assert calls["n"] <= _MAX_CKAN_PAGES
    assert len(records) == _MAX_CKAN_PAGES


def test_bbox_from_valid_spatial_extra():
    pkg = _pkg(
        extras=[
            {
                "key": "spatial",
                "value": json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [[1.0, 45.0], [2.0, 45.0], [2.0, 46.0], [1.0, 46.0], [1.0, 45.0]]
                        ],
                    }
                ),
            }
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [1.0, 45.0, 2.0, 46.0]


def test_bbox_defaults_to_world_when_extras_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([_pkg()]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_bbox_defaults_to_world_when_spatial_extra_is_malformed_json():
    pkg = _pkg(extras=[{"key": "spatial", "value": "not json"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_copy_resource_selection_prefers_geojson_over_gpkg_over_shp():
    pkg = _pkg(
        resources=[
            {"format": "SHP", "url": f"{PORTAL}/r/a.zip"},
            {"format": "GPKG", "url": f"{PORTAL}/r/a.gpkg"},
            {"format": "GeoJSON", "url": f"{PORTAL}/r/a.geojson"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.geojson"
    assert rec.copy_filename == "harvest.geojson"


def test_copy_resource_selection_gpkg_only():
    pkg = _pkg(resources=[{"format": "GEOPACKAGE", "url": f"{PORTAL}/r/a.gpkg"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.gpkg"
    assert rec.copy_filename == "harvest.gpkg"


def test_copy_resource_selection_shapefile_zipped_only():
    pkg = _pkg(resources=[{"format": "Shapefile", "url": f"{PORTAL}/r/a.zip"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.zip"
    assert rec.copy_filename == "harvest.zip"


def test_copy_resource_selection_csv_only_is_reference_only():
    pkg = _pkg(resources=[{"format": "CSV", "url": f"{PORTAL}/r/a.csv"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url is None
    assert rec.copy_filename is None


def test_copy_resource_without_url_is_ignored():
    pkg = _pkg(resources=[{"format": "GeoJSON"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url is None
    assert rec.copy_filename is None


def test_tolerant_to_malformed_package_fields():
    pkg = _pkg(tags="not-a-list", extras="not-a-list", resources="not-a-list")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.keywords == []
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec.items_url is None


def test_non_dict_package_is_ignored():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response(["not-a-dict", _pkg()]))

    records = list(_connector(handler).fetch(PORTAL))
    assert [r.external_id for r in records] == ["pkg-1"]


def test_missing_result_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_invalid_json_page_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_http_error_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_next_page_failure_keeps_partial_results():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg()], count=999))
        return httpx.Response(500)

    records = list(_connector(handler).fetch(PORTAL))
    assert [r.external_id for r in records] == ["pkg-1"]


def test_fetch_copy_geojson_calls_http_get_on_items_url():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=f"{PORTAL}/r/a.gpkg",
        copy_filename="harvest.gpkg",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, content=b"gpkg-bytes")

    content = CkanConnector().fetch_copy_geojson(rec, http_get=http_get)
    assert content == b"gpkg-bytes"
    assert calls == [f"{PORTAL}/r/a.gpkg"]


def test_fetch_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=None,
    )
    assert CkanConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_get_connector_returns_ckan():
    from app.harvest.connectors import get_connector

    c = get_connector("ckan")
    assert c.type == "ckan"
    assert c.supports_copy is True
