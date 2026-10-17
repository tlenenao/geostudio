# SPDX-License-Identifier: Apache-2.0
"""AUD-128 : connecteur udata (data.gouv.fr ne sert pas l'API CKAN, /api/3 -> 404)."""

import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestFetchError
from app.harvest.connectors.udata import UdataConnector

PORTAL = "https://www.data.gouv.fr"
API = f"{PORTAL}/api/1/datasets/"


def _ds(**overrides):
    ds = {
        "id": "ds-1",
        "slug": "batiments-ville",
        "title": "Bâtiments de la ville",
        "description": "Empreintes",
        "tags": ["bati", "urbain"],
        "page": f"{PORTAL}/fr/datasets/batiments-ville/",
        "spatial": {"geom": {"type": "Point", "coordinates": [2.0, 48.0]}},
        "resources": [
            {"format": "csv", "url": "https://x.test/a.csv"},
            {"format": "geojson", "url": "https://x.test/a.geojson"},
        ],
    }
    ds.update(overrides)
    return ds


def _page(data, next_page=None):
    return {"data": data, "next_page": next_page, "page": 1, "page_size": 100, "total": len(data)}


def _connector(handler) -> UdataConnector:
    return UdataConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_maps_dataset_fields_and_keeps_admin_filters():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=_page([_ds()]))

    recs = _connector(handler).fetch(f"{PORTAL}/?organization=abc&page=7")
    assert seen[0].path == "/api/1/datasets/"
    assert seen[0].params["organization"] == "abc"
    assert "page" not in seen[0].params and seen[0].params["page_size"] == "100"
    [r] = recs
    assert (r.external_id, r.title, r.abstract) == ("ds-1", "Bâtiments de la ville", "Empreintes")
    assert r.keywords == ["bati", "urbain"]
    assert r.bbox == [2.0, 48.0, 2.0, 48.0]
    assert r.external_url == f"{PORTAL}/fr/datasets/batiments-ville/"
    assert (r.items_url, r.copy_filename) == ("https://x.test/a.geojson", "harvest.geojson")


def test_follows_next_page_on_same_host_only():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200, json=_page([_ds(id="ds-2")], "https://evil.test/api/1/datasets/?page=3")
            )
        return httpx.Response(200, json=_page([_ds()], f"{API}?page=2&page_size=100"))

    recs = _connector(handler).fetch(PORTAL)
    assert [r.external_id for r in recs] == ["ds-1", "ds-2"]


def test_missing_spatial_and_page_fall_back():
    def handler(request):
        return httpx.Response(200, json=_page([_ds(spatial=None, page=None, resources=[])]))

    [r] = _connector(handler).fetch(PORTAL)
    assert r.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert r.external_url == f"{PORTAL}/datasets/batiments-ville"
    assert r.items_url is None


def test_root_failure_is_reported():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(HarvestFetchError):
        _connector(handler).fetch(PORTAL)


def test_registered_and_copy_capable():
    c = get_connector("udata")
    assert c.type == "udata" and c.supports_copy is True
