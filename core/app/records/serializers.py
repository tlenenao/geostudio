# SPDX-License-Identifier: Apache-2.0
"""OGC API Records Part 1 (OGC 20-004r1) : un item du catalogue = un record GeoJSON."""

from app.catalog.metadata import resolve_license
from app.items.schemas import ItemRead

SPEC = "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf"
RECORD_CORE = f"{SPEC}/record-core"
CONFORMANCE = [
    RECORD_CORE,
    f"{SPEC}/record-collection",
    f"{SPEC}/records-api",  # libellé de l'annexe A.3 (le texte §8 écrit « record-api »)
    f"{SPEC}/json",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]
CATALOG_ID = "catalog"


def _polygon(bbox: list[float]) -> dict:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def record(*, base: str, item: ItemRead) -> dict:
    props: dict = {
        "type": item.resourceType,
        "title": item.title,
        "description": item.abstract,
        "keywords": list(item.keywords),
        "language": {"code": item.language},
        "created": item.date,
        "updated": item.updatedAt,
        # Revue L6 M2 : un moissonneur authentifié doit voir qu'un item est déprécié.
        "status": item.contentStatus,
    }
    lic = resolve_license(item.license) if item.license else None
    if lic is not None:
        props["license"] = lic.spdx_id
    items = f"{base}/records/collections/{CATALOG_ID}"
    return {
        "id": item.pk,
        "type": "Feature",
        "conformsTo": [RECORD_CORE],
        "time": None,
        "geometry": _polygon(item.bbox) if item.bbox else None,
        "properties": props,
        "links": [
            {"rel": "self", "type": "application/geo+json", "href": f"{items}/items/{item.pk}"},
            {"rel": "collection", "type": "application/json", "href": items},
        ],
    }


def catalog(*, base: str) -> dict:
    href = f"{base}/records/collections/{CATALOG_ID}"
    return {
        "id": CATALOG_ID,
        "type": "Collection",
        "itemType": "record",
        "title": "Catalogue GeoStudio",
        "description": "Cartes, applications, tableaux de bord et jeux de données du catalogue.",
        "links": [
            {"rel": "self", "type": "application/ogc-catalog+json", "href": href},
            {"rel": "items", "type": "application/geo+json", "href": f"{href}/items"},
        ],
    }
