# SPDX-License-Identifier: Apache-2.0
"""Serializers STAC purs : construisent des dicts (Catalog / Collection / Item /
ItemCollection / conformance) à partir de primitives. Zéro I/O, aucune
dépendance runtime à stac-pydantic (qui reste une dépendance de test). Les
liens sont construits depuis `base` = racine du serveur sans slash final."""

STAC_VERSION = "1.0.0"

CONFORMANCE_CLASSES = [
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
    "https://api.stacspec.org/v1.0.0/item-search",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]


def conformance() -> dict:
    return {"conformsTo": list(CONFORMANCE_CLASSES)}


def catalog(*, base: str, collection_ids: list[str]) -> dict:
    links = [
        {"rel": "self", "type": "application/json", "href": f"{base}/stac"},
        {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
        {"rel": "conformance", "type": "application/json", "href": f"{base}/stac/conformance"},
        {"rel": "data", "type": "application/json", "href": f"{base}/stac/collections"},
        {"rel": "search", "type": "application/geo+json", "href": f"{base}/stac/search"},
    ]
    for cid in collection_ids:
        links.append({"rel": "child", "type": "application/json",
                      "href": f"{base}/stac/collections/{cid}"})
    return {
        "type": "Catalog",
        "stac_version": STAC_VERSION,
        "id": "geostudio",
        "title": "GeoStudio STAC catalog",
        "description": "Catalogue de données GeoStudio exposé en STAC (lecture seule).",
        "conformsTo": list(CONFORMANCE_CLASSES),
        "links": links,
    }


WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


def collection(*, base: str, collection_id: str, title: str, description: str,
               bbox: list[float] | None, temporal_start: str | None) -> dict:
    doc = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "id": collection_id,
        "title": title,
        "description": description or "",
        "license": "other",
        "extent": {
            "spatial": {"bbox": [bbox if bbox is not None else list(WORLD_BBOX)]},
            "temporal": {"interval": [[temporal_start, None]]},
        },
        "links": [
            {"rel": "self", "type": "application/json",
             "href": f"{base}/stac/collections/{collection_id}"},
            {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
            {"rel": "parent", "type": "application/json", "href": f"{base}/stac"},
            {"rel": "items", "type": "application/geo+json",
             "href": f"{base}/stac/collections/{collection_id}/items"},
        ],
    }
    if bbox is None:
        doc["note"] = "Emprise indisponible (pas de géométrie ou table vide) : repli emprise monde."
    return doc
