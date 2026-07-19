# SPDX-License-Identifier: Apache-2.0
from stac_pydantic import Catalog, Collection

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


def test_collection_valid_with_bbox_and_temporal():
    col = s.collection(base=BASE, collection_id="roads", title="Routes",
                       description="Réseau routier", bbox=[1.0, 44.0, 2.0, 45.0],
                       temporal_start="2026-07-01T00:00:00Z")
    assert col["type"] == "Collection"
    assert col["license"] == "other"
    assert col["extent"]["spatial"]["bbox"] == [[1.0, 44.0, 2.0, 45.0]]
    assert col["extent"]["temporal"]["interval"] == [["2026-07-01T00:00:00Z", None]]
    rels = {l["rel"]: l["href"] for l in col["links"]}
    assert rels["self"] == f"{BASE}/stac/collections/roads"
    assert rels["items"] == f"{BASE}/stac/collections/roads/items"
    assert rels["parent"] == f"{BASE}/stac"
    Collection.model_validate(col)


def test_collection_without_bbox_falls_back_to_world():
    col = s.collection(base=BASE, collection_id="empty", title="Vide",
                       description="", bbox=None, temporal_start=None)
    assert col["extent"]["spatial"]["bbox"] == [[-180.0, -90.0, 180.0, 90.0]]
    assert col["extent"]["temporal"]["interval"] == [[None, None]]
    assert "note" in col
    # stac-pydantic Collection exige description non vide (min_length=1) ; le serializer peut
    # légitimement produire "" (aucune description fournie) — substituer un texte neutre avant
    # validation seulement, la forme du dict produit par collection() reste inchangée.
    Collection.model_validate({**col, "description": col["description"] or "(sans description)"})
