# SPDX-License-Identifier: Apache-2.0
"""Serializers DCAT-AP purs : construisent des dicts JSON-LD (Catalog /
Dataset / Distribution) à partir de primitives. Zéro I/O, même discipline que
app.stac.serializers. @context DCAT-AP fixe en dur (préfixes dcat/dct/foaf/
locn/xsd) — jamais de résolution réseau au runtime ; rdflib/pyshacl restent
des dépendances de test uniquement."""

import json

CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "locn": "http://www.w3.org/ns/locn#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

LICENSE_OTHER = "http://publications.europa.eu/resource/authority/licence/OTHER"
ACCESS_RIGHTS_PUBLIC = "http://publications.europa.eu/resource/authority/access-right/PUBLIC"
ACCESS_RIGHTS_RESTRICTED = "http://publications.europa.eu/resource/authority/access-right/RESTRICTED"
WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


def publisher(*, base: str, name: str) -> dict:
    return {"@id": f"{base}/dcat/publisher", "@type": "foaf:Agent", "foaf:name": name}


def _bbox_polygon(bbox: list[float] | None) -> dict:
    minx, miny, maxx, maxy = bbox if bbox is not None else WORLD_BBOX
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def distribution(*, title: str, access_url: str,
                 media_type: str | None = None, format_uri: str | None = None) -> dict:
    doc = {
        "@type": "dcat:Distribution",
        "dct:title": title,
        "dcat:accessURL": {"@id": access_url},
    }
    if media_type:
        doc["dcat:mediaType"] = {"@id": media_type}
    if format_uri:
        doc["dct:format"] = {"@id": format_uri}
    return doc


def dataset(*, base: str, collection_id: str, title: str, description: str,
           created_at: str, updated_at: str, is_public: bool,
           publisher_name: str, bbox: list[float] | None) -> dict:
    return {
        "@id": f"{base}/dcat/datasets/{collection_id}",
        "@type": "dcat:Dataset",
        "dct:identifier": collection_id,
        "dct:title": title,
        "dct:description": description or title or "No description provided.",
        "dct:issued": {"@value": created_at, "@type": "xsd:dateTime"},
        "dct:modified": {"@value": updated_at, "@type": "xsd:dateTime"},
        "dct:license": {"@id": LICENSE_OTHER},
        "dct:accessRights": {"@id": ACCESS_RIGHTS_PUBLIC if is_public else ACCESS_RIGHTS_RESTRICTED},
        "dct:publisher": publisher(base=base, name=publisher_name),
        "dct:spatial": {
            "@type": "dct:Location",
            "locn:geometry": {
                "@value": json.dumps(_bbox_polygon(bbox)),
                "@type": "https://www.iana.org/assignments/media-types/application/vnd.geo+json",
            },
        },
        "dct:temporal": {
            "@type": "dct:PeriodOfTime",
            "dcat:startDate": {"@value": created_at, "@type": "xsd:dateTime"},
        },
        "dcat:distribution": [
            distribution(
                title="GeoJSON (OGC API Features)",
                access_url=f"{base}/collections/{collection_id}/items",
                media_type="https://www.iana.org/assignments/media-types/application/geo+json",
                format_uri="http://publications.europa.eu/resource/authority/file-type/GEOJSON",
            ),
            distribution(
                title="STAC item-search",
                access_url=f"{base}/stac/collections/{collection_id}/items",
                format_uri="http://publications.europa.eu/resource/authority/file-type/JSON",
            ),
        ],
    }


def catalog(*, base: str, tenant_name: str, datasets: list[dict]) -> dict:
    return {
        "@context": CONTEXT,
        "@id": f"{base}/dcat/catalog",
        "@type": "dcat:Catalog",
        "dct:title": "Catalogue GeoStudio",
        "dct:description": "Export DCAT-AP du catalogue de données GeoStudio (lecture seule).",
        "dct:publisher": publisher(base=base, name=tenant_name),
        "dct:language": "fr",
        "dcat:dataset": datasets,
    }
