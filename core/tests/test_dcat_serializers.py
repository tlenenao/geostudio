# SPDX-License-Identifier: Apache-2.0
import json

import rdflib
from pyshacl import validate

from app.dcat import serializers as s

BASE = "http://testserver"


def test_context_has_expected_prefixes():
    assert s.CONTEXT == {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "locn": "http://www.w3.org/ns/locn#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }


def test_publisher_is_valid_foaf_agent(dcat_shacl_shapes):
    pub = s.publisher(base=BASE, name="Default")
    assert pub == {"@id": f"{BASE}/dcat/publisher", "@type": "foaf:Agent",
                   "foaf:name": "Default"}
    # Enveloppe minimale : un dcat:Catalog portant ce publisher doit être
    # SHACL-valide — preuve que le pipeline rdflib+pyshacl+shapes officielles
    # fonctionne réellement (gate empirique, spec §8).
    doc = {
        "@context": s.CONTEXT,
        "@id": f"{BASE}/dcat/catalog",
        "@type": "dcat:Catalog",
        "dct:title": "t",
        "dct:description": "d",
        "dct:publisher": pub,
    }
    g = rdflib.Graph()
    g.parse(data=json.dumps(doc), format="json-ld")
    assert len(g) > 0  # round-trip rdflib : parse sans exception, triples non vides
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_shacl_gate_actually_catches_violations(dcat_shacl_shapes):
    # Contre-preuve : un Dataset sans dct:title/dct:description (mandatoires)
    # DOIT être rejeté — sinon le gate ne prouve rien.
    doc = {"@context": s.CONTEXT, "@id": f"{BASE}/dcat/datasets/x", "@type": "dcat:Dataset"}
    g = rdflib.Graph()
    g.parse(data=json.dumps(doc), format="json-ld")
    conforms, _, _ = validate(g, shacl_graph=dcat_shacl_shapes)
    assert not conforms


def test_bbox_polygon_from_bbox():
    poly = s._bbox_polygon([1.0, 44.0, 2.0, 45.0])
    assert poly == {
        "type": "Polygon",
        "coordinates": [[[1.0, 44.0], [2.0, 44.0], [2.0, 45.0], [1.0, 45.0], [1.0, 44.0]]],
    }


def test_bbox_polygon_falls_back_to_world():
    poly = s._bbox_polygon(None)
    assert poly["coordinates"][0][0] == [-180.0, -90.0]


def test_distribution_shape():
    d = s.distribution(title="GeoJSON (OGC API Features)",
                       access_url="http://testserver/collections/roads/items",
                       media_type="https://www.iana.org/assignments/media-types/application/geo+json",
                       format_uri="http://publications.europa.eu/resource/authority/file-type/GEOJSON")
    assert d["@type"] == "dcat:Distribution"
    assert d["dcat:accessURL"] == {"@id": "http://testserver/collections/roads/items"}
    assert d["dcat:mediaType"] == {"@id": "https://www.iana.org/assignments/media-types/application/geo+json"}
    assert d["dct:format"] == {"@id": "http://publications.europa.eu/resource/authority/file-type/GEOJSON"}


def test_distribution_optional_fields_omitted():
    d = s.distribution(title="STAC item-search", access_url="http://testserver/stac/collections/roads/items")
    assert "dcat:mediaType" not in d
    assert "dct:format" not in d


def test_dataset_is_shacl_valid_standalone(dcat_shacl_shapes):
    doc = s.dataset(base=BASE, collection_id="roads", title="Routes",
                    description="Réseau routier", created_at="2026-07-01T00:00:00Z",
                    updated_at="2026-07-10T00:00:00Z", is_public=True,
                    publisher_name="Default", bbox=[1.0, 44.0, 2.0, 45.0])
    assert doc["@type"] == "dcat:Dataset"
    assert doc["dct:identifier"] == "roads"
    assert doc["dct:license"] == {"@id": s.LICENSE_OTHER}
    assert doc["dct:accessRights"] == {"@id": s.ACCESS_RIGHTS_PUBLIC}
    assert len(doc["dcat:distribution"]) == 2
    assert doc["dcat:distribution"][0]["dcat:accessURL"] == {
        "@id": "http://testserver/collections/roads/items"}
    assert doc["dcat:distribution"][1]["dcat:accessURL"] == {
        "@id": "http://testserver/stac/collections/roads/items"}
    standalone = {**doc, "@context": s.CONTEXT}
    g = rdflib.Graph()
    g.parse(data=json.dumps(standalone), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_restricted_access_rights_when_not_public():
    doc = s.dataset(base=BASE, collection_id="roads", title="Routes", description="",
                    created_at="2026-07-01T00:00:00Z", updated_at="2026-07-01T00:00:00Z",
                    is_public=False, publisher_name="Default", bbox=None)
    assert doc["dct:accessRights"] == {"@id": s.ACCESS_RIGHTS_RESTRICTED}
    assert doc["dct:description"] == "Routes"  # repli sur le titre, description vide


def test_dataset_no_bbox_falls_back_to_world():
    doc = s.dataset(base=BASE, collection_id="roads", title="Routes", description="d",
                    created_at="2026-07-01T00:00:00Z", updated_at="2026-07-01T00:00:00Z",
                    is_public=True, publisher_name="Default", bbox=None)
    poly = json.loads(doc["dct:spatial"]["locn:geometry"]["@value"])
    assert poly["coordinates"][0][0] == [-180.0, -90.0]
