# SPDX-License-Identifier: Apache-2.0
"""Serializers DCAT-AP purs : construisent des dicts JSON-LD (Catalog /
Dataset / Distribution) à partir de primitives. Zéro I/O, même discipline que
app.stac.serializers. @context DCAT-AP fixe en dur (préfixes dcat/dct/foaf/
locn/xsd) — jamais de résolution réseau au runtime ; rdflib/pyshacl restent
des dépendances de test uniquement."""

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
