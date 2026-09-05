# SPDX-License-Identifier: Apache-2.0
"""Serializers DCAT-AP purs : construisent des dicts JSON-LD (Catalog /
Dataset / Distribution) à partir de primitives. Zéro I/O, même discipline que
app.stac.serializers. @context DCAT-AP fixe en dur (préfixes dcat/dct/foaf/
locn/xsd) — jamais de résolution réseau au runtime ; rdflib/pyshacl restent
des dépendances de test uniquement."""

import json

from app.catalog.metadata import resolve_frequency, resolve_language, resolve_license

CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "locn": "http://www.w3.org/ns/locn#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

LICENSE_OTHER = "http://publications.europa.eu/resource/authority/licence/OTHER"
ACCESS_RIGHTS_PUBLIC = "http://publications.europa.eu/resource/authority/access-right/PUBLIC"
ACCESS_RIGHTS_RESTRICTED = (
    "http://publications.europa.eu/resource/authority/access-right/RESTRICTED"
)
WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


def publisher(*, base: str, name: str, producer_slug: str | None = None) -> dict:
    # Sans producer_slug (défaut, cf. catalog() ci-dessous et dataset() quand
    # aucun producteur n'est déclaré) : IRI partagée à l'échelle du tenant,
    # inchangée. Avec producer_slug (dataset() quand col.producer est déclaré,
    # SP-41 correctif de revue finale) : IRI distincte par collection — sans
    # quoi GET /dcat/catalog fait pointer tous les jeux de données vers le
    # même @id de publisher avec des foaf:name différents et incohérents pour
    # un consommateur JSON-LD qui fusionne le document en graphe RDF.
    publisher_id = (
        f"{base}/dcat/publisher/{producer_slug}" if producer_slug else f"{base}/dcat/publisher"
    )
    return {"@id": publisher_id, "@type": "foaf:Agent", "foaf:name": name}


def _bbox_polygon(bbox: list[float] | None) -> dict:
    minx, miny, maxx, maxy = bbox if bbox is not None else WORLD_BBOX
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def distribution(
    *, title: str, access_url: str, media_type: str | None = None, format_uri: str | None = None
) -> dict:
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


def _contact_point(contact: str) -> dict:
    if "@" in contact:
        return {"@type": "vcard:Kind", "vcard:hasEmail": f"mailto:{contact}"}
    return {"@type": "vcard:Kind", "vcard:fn": contact}


def dataset(
    *,
    base: str,
    collection_id: str,
    title: str,
    description: str,
    created_at: str,
    updated_at: str,
    is_public: bool,
    publisher_name: str,
    bbox: list[float] | None,
    license: str = "",
    license_uri: str = "",
    language: str = "fr",
    update_frequency: str = "",
    lineage: str = "",
    contact: str = "",
    version: str = "",
    temporal_start: str | None = None,
    temporal_end: str | None = None,
    producer_declared: bool = False,
) -> dict:
    license_entry = resolve_license(license) if license else None
    if license_entry is not None and license_entry.dcat_uri:
        license_id = {"@id": license_entry.dcat_uri}
    elif license == "other" and license_uri:
        license_id = {"@id": license_uri}
    else:
        license_id = {"@id": LICENSE_OTHER}

    temporal: dict = {"@type": "dct:PeriodOfTime"}
    if temporal_start:
        temporal["dcat:startDate"] = {"@value": temporal_start, "@type": "xsd:date"}
    else:
        temporal["dcat:startDate"] = {"@value": created_at, "@type": "xsd:dateTime"}
    if temporal_end:
        temporal["dcat:endDate"] = {"@value": temporal_end, "@type": "xsd:date"}

    doc = {
        "@id": f"{base}/dcat/datasets/{collection_id}",
        "@type": "dcat:Dataset",
        "dct:identifier": collection_id,
        "dct:title": title,
        "dct:description": description or title or "No description provided.",
        "dct:issued": {"@value": created_at, "@type": "xsd:dateTime"},
        "dct:modified": {"@value": updated_at, "@type": "xsd:dateTime"},
        "dct:license": license_id,
        "dct:language": {
            "@id": (
                "http://publications.europa.eu/resource/authority/language/"
                f"{resolve_language(language).alpha3}"
            )
        },
        "dct:accessRights": {
            "@id": ACCESS_RIGHTS_PUBLIC if is_public else ACCESS_RIGHTS_RESTRICTED
        },
        "dct:publisher": publisher(
            base=base,
            name=publisher_name,
            producer_slug=collection_id if producer_declared else None,
        ),
        "dct:spatial": {
            "@type": "dct:Location",
            "locn:geometry": {
                "@value": json.dumps(_bbox_polygon(bbox)),
                "@type": "https://www.iana.org/assignments/media-types/application/vnd.geo+json",
            },
        },
        "dct:temporal": temporal,
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
    if update_frequency:
        freq_entry = resolve_frequency(update_frequency)
        if freq_entry is not None:
            doc["dct:accrualPeriodicity"] = {"@id": freq_entry.mdr_freq_uri}
    if lineage:
        doc["dct:provenance"] = {"@type": "dct:ProvenanceStatement", "rdfs:label": lineage}
    if contact:
        doc["dcat:contactPoint"] = _contact_point(contact)
    if version:
        doc["dct:hasVersion"] = version
    return doc


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
