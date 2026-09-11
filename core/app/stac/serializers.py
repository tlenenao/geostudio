# SPDX-License-Identifier: Apache-2.0
"""Serializers STAC purs : construisent des dicts (Catalog / Collection / Item /
ItemCollection / conformance) à partir de primitives. Zéro I/O, aucune
dépendance runtime à stac-pydantic (qui reste une dépendance de test). Les
liens sont construits depuis `base` = racine du serveur sans slash final."""

from app.catalog.metadata import resolve_license

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


def catalog(*, base: str, root: str, collection_ids: list[str]) -> dict:
    links = [
        {"rel": "self", "type": "application/json", "href": f"{base}/stac"},
        {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
        {"rel": "conformance", "type": "application/json", "href": f"{base}/stac/conformance"},
        {"rel": "data", "type": "application/json", "href": f"{base}/stac/collections"},
        {"rel": "search", "type": "application/geo+json", "href": f"{base}/stac/search"},
        # stac-api-validator (REV-098/GAP-04) exige ces deux liens sur la page
        # d'atterrissage (Core conformance). `root` (jamais `base`) : le
        # document OpenAPI et Swagger UI sont montés hors du préfixe /v1, sur
        # l'app FastAPI racine — app/main.py ne les nested pas sous v1_router.
        {"rel": "service-desc", "type": "application/json", "href": f"{root}/openapi.json"},
        {"rel": "service-doc", "type": "text/html", "href": f"{root}/docs"},
    ]
    for cid in collection_ids:
        links.append(
            {"rel": "child", "type": "application/json", "href": f"{base}/stac/collections/{cid}"}
        )
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


def collection(
    *,
    base: str,
    collection_id: str,
    title: str,
    description: str,
    bbox: list[float] | None,
    temporal_start: str | None,
    license: str = "",
    providers: list[dict] | None = None,
    temporal_end: str | None = None,
) -> dict:
    entry = resolve_license(license) if license else None
    doc = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "id": collection_id,
        "title": title,
        "description": description or title or "No description provided.",
        "license": entry.spdx_id if entry else "other",
        "extent": {
            "spatial": {"bbox": [bbox if bbox is not None else list(WORLD_BBOX)]},
            "temporal": {"interval": [[temporal_start, temporal_end]]},
        },
        "links": [
            {
                "rel": "self",
                "type": "application/json",
                "href": f"{base}/stac/collections/{collection_id}",
            },
            {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
            {"rel": "parent", "type": "application/json", "href": f"{base}/stac"},
            {
                "rel": "items",
                "type": "application/geo+json",
                "href": f"{base}/stac/collections/{collection_id}/items",
            },
        ],
    }
    if providers:
        doc["providers"] = providers
    if bbox is None:
        doc["note"] = "Emprise indisponible (pas de géométrie ou table vide) : repli emprise monde."
    return doc


def _iter_coords(coords):
    # coords est soit une paire [x, y(, z)], soit une liste imbriquée.
    if coords and isinstance(coords[0], (int, float)):
        yield coords
        return
    for sub in coords:
        yield from _iter_coords(sub)


def _geojson_bbox(geometry: dict | None) -> list[float] | None:
    if not geometry or not geometry.get("coordinates"):
        return None
    xs, ys = [], []
    for x, y, *_ in _iter_coords(geometry["coordinates"]):
        xs.append(float(x))
        ys.append(float(y))
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def item(*, base: str, collection_id: str, feature: dict, datetime_value: str) -> dict:
    fid = str(feature["id"])
    geometry = feature.get("geometry")
    properties = dict(feature.get("properties") or {})
    properties["datetime"] = datetime_value  # clé réservée : écrase un homonyme (§2.2)
    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "id": fid,
        "collection": collection_id,
        "geometry": geometry,
        "bbox": _geojson_bbox(geometry),
        "properties": properties,
        "assets": {},
        "links": [
            {
                "rel": "self",
                "type": "application/geo+json",
                "href": f"{base}/stac/collections/{collection_id}/items/{fid}",
            },
            {
                "rel": "parent",
                "type": "application/json",
                "href": f"{base}/stac/collections/{collection_id}",
            },
            {
                "rel": "collection",
                "type": "application/json",
                "href": f"{base}/stac/collections/{collection_id}",
            },
            {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
        ],
    }


def item_collection(*, items: list[dict], links: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": items, "links": links}
