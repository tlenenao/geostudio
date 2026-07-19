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
