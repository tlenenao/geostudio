# SPDX-License-Identifier: Apache-2.0
from stac_pydantic import Catalog

from app.stac import serializers as s

BASE = "http://testserver"

EXPECTED_CONFORMANCE = {
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
    "https://api.stacspec.org/v1.0.0/item-search",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
}


def test_conformance_lists_all_classes():
    assert set(s.conformance()["conformsTo"]) == EXPECTED_CONFORMANCE


def test_catalog_is_valid_and_links_children():
    cat = s.catalog(base=BASE, collection_ids=["roads", "rivers"])
    assert cat["type"] == "Catalog"
    assert cat["stac_version"] == "1.0.0"
    assert set(cat["conformsTo"]) == EXPECTED_CONFORMANCE
    rels = {l["rel"]: l["href"] for l in cat["links"]}
    assert rels["self"] == f"{BASE}/stac"
    assert rels["data"] == f"{BASE}/stac/collections"
    assert rels["search"] == f"{BASE}/stac/search"
    assert rels["conformance"] == f"{BASE}/stac/conformance"
    children = [l["href"] for l in cat["links"] if l["rel"] == "child"]
    assert children == [f"{BASE}/stac/collections/roads", f"{BASE}/stac/collections/rivers"]
    # stac-pydantic Catalog ne connaît pas conformsTo (champ STAC-API) : le retirer avant validation.
    Catalog.model_validate({k: v for k, v in cat.items() if k != "conformsTo"})
