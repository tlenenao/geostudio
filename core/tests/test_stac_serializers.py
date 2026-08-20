# SPDX-License-Identifier: Apache-2.0
from stac_pydantic import Catalog, Collection, Item, ItemCollection

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
    rels = {link["rel"]: link["href"] for link in cat["links"]}
    assert rels["self"] == f"{BASE}/stac"
    assert rels["data"] == f"{BASE}/stac/collections"
    assert rels["search"] == f"{BASE}/stac/search"
    assert rels["conformance"] == f"{BASE}/stac/conformance"
    children = [link["href"] for link in cat["links"] if link["rel"] == "child"]
    assert children == [f"{BASE}/stac/collections/roads", f"{BASE}/stac/collections/rivers"]
    # stac-pydantic Catalog ne connaît pas conformsTo (champ STAC-API) : le
    # retirer avant validation.
    Catalog.model_validate({k: v for k, v in cat.items() if k != "conformsTo"})


def test_collection_valid_with_bbox_and_temporal():
    col = s.collection(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="Réseau routier",
        bbox=[1.0, 44.0, 2.0, 45.0],
        temporal_start="2026-07-01T00:00:00Z",
    )
    assert col["type"] == "Collection"
    assert col["license"] == "other"
    assert col["extent"]["spatial"]["bbox"] == [[1.0, 44.0, 2.0, 45.0]]
    assert col["extent"]["temporal"]["interval"] == [["2026-07-01T00:00:00Z", None]]
    rels = {link["rel"]: link["href"] for link in col["links"]}
    assert rels["self"] == f"{BASE}/stac/collections/roads"
    assert rels["items"] == f"{BASE}/stac/collections/roads/items"
    assert rels["parent"] == f"{BASE}/stac"
    Collection.model_validate(col)


def test_collection_without_bbox_falls_back_to_world():
    col = s.collection(
        base=BASE,
        collection_id="empty",
        title="Vide",
        description="",
        bbox=None,
        temporal_start=None,
    )
    assert col["extent"]["spatial"]["bbox"] == [[-180.0, -90.0, 180.0, 90.0]]
    assert col["extent"]["temporal"]["interval"] == [[None, None]]
    assert "note" in col
    # description vide en entrée : le serializer replie sur le title, jamais une chaîne vide
    # (stac-pydantic Collection exige min_length=1).
    assert col["description"] == "Vide"
    Collection.model_validate(col)


DT = "2026-07-10T12:00:00Z"
FEAT = {
    "type": "Feature",
    "id": 7,
    "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
    "properties": {"titre": "Nid de poule", "datetime": "OVERRIDE-ME"},
}


def test_item_valid_with_bbox_and_synthetic_datetime():
    it = s.item(base=BASE, collection_id="roads", feature=FEAT, datetime_value=DT)
    assert it["type"] == "Feature"
    assert it["id"] == "7"  # coercé en str
    assert it["collection"] == "roads"
    assert it["bbox"] == [1.85, 45.27, 1.85, 45.27]
    assert it["properties"]["datetime"] == DT  # écrase l'attribut homonyme de la feature
    assert it["properties"]["titre"] == "Nid de poule"
    assert it["assets"] == {}
    rels = {link["rel"]: link["href"] for link in it["links"]}
    assert rels["self"] == f"{BASE}/stac/collections/roads/items/7"
    assert rels["collection"] == f"{BASE}/stac/collections/roads"
    Item.model_validate(it)


def test_item_null_geometry_has_null_bbox():
    feat = {"type": "Feature", "id": "abc", "geometry": None, "properties": {}}
    it = s.item(base=BASE, collection_id="roads", feature=feat, datetime_value=DT)
    assert it["geometry"] is None
    assert it["bbox"] is None
    Item.model_validate(it)


def test_geojson_bbox_polygon():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 3], [0, 3], [0, 0]]]}
    assert s._geojson_bbox(geom) == [0.0, 0.0, 2.0, 3.0]


def test_item_collection_wraps():
    it = s.item(base=BASE, collection_id="roads", feature=FEAT, datetime_value=DT)
    ic = s.item_collection(items=[it], links=[{"rel": "self", "href": f"{BASE}/stac/search"}])
    assert ic["type"] == "FeatureCollection"
    assert ic["features"] == [it]
    ItemCollection.model_validate(ic)
