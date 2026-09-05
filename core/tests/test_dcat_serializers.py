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
        "vcard": "http://www.w3.org/2006/vcard/ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    }


def test_publisher_is_valid_foaf_agent(dcat_shacl_shapes):
    pub = s.publisher(base=BASE, name="Default")
    assert pub == {"@id": f"{BASE}/dcat/publisher", "@type": "foaf:Agent", "foaf:name": "Default"}
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


def test_publisher_id_distinct_per_producer_slug():
    # SP-41, correctif de revue finale : sans producer_slug, deux jeux de
    # données avec des producteurs déclarés différents partageaient la même
    # @id dct:publisher — un consommateur JSON-LD qui fusionne
    # GET /dcat/catalog en graphe RDF voyait un seul Agent avec N foaf:name
    # incohérents. producer_slug rend l'IRI distincte par collection.
    shared = s.publisher(base=BASE, name="Tenant par défaut")
    assert shared["@id"] == f"{BASE}/dcat/publisher"

    roads = s.publisher(base=BASE, name="Ma Régie", producer_slug="roads")
    rivers = s.publisher(base=BASE, name="Autre Régie", producer_slug="rivers")
    assert roads["@id"] == f"{BASE}/dcat/publisher/roads"
    assert rivers["@id"] == f"{BASE}/dcat/publisher/rivers"
    assert roads["@id"] != rivers["@id"]
    assert roads["@id"] != shared["@id"]


def test_dataset_publisher_id_distinct_when_producer_declared():
    without_producer = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        is_public=True,
        publisher_name="Tenant par défaut",
        bbox=None,
    )
    assert without_producer["dct:publisher"]["@id"] == f"{BASE}/dcat/publisher"

    with_producer_a = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        is_public=True,
        publisher_name="Ma Régie",
        bbox=None,
        producer_declared=True,
    )
    with_producer_b = s.dataset(
        base=BASE,
        collection_id="rivers",
        title="Rivières",
        description="d",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        is_public=True,
        publisher_name="Autre Régie",
        bbox=None,
        producer_declared=True,
    )
    assert with_producer_a["dct:publisher"]["foaf:name"] == "Ma Régie"
    assert with_producer_b["dct:publisher"]["foaf:name"] == "Autre Régie"
    assert with_producer_a["dct:publisher"]["@id"] != with_producer_b["dct:publisher"]["@id"]
    assert with_producer_a["dct:publisher"]["@id"] != without_producer["dct:publisher"]["@id"]


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
    d = s.distribution(
        title="GeoJSON (OGC API Features)",
        access_url="http://testserver/collections/roads/items",
        media_type="https://www.iana.org/assignments/media-types/application/geo+json",
        format_uri="http://publications.europa.eu/resource/authority/file-type/GEOJSON",
    )
    assert d["@type"] == "dcat:Distribution"
    assert d["dcat:accessURL"] == {"@id": "http://testserver/collections/roads/items"}
    assert d["dcat:mediaType"] == {
        "@id": "https://www.iana.org/assignments/media-types/application/geo+json"
    }
    assert d["dct:format"] == {
        "@id": "http://publications.europa.eu/resource/authority/file-type/GEOJSON"
    }


def test_distribution_optional_fields_omitted():
    d = s.distribution(
        title="STAC item-search", access_url="http://testserver/stac/collections/roads/items"
    )
    assert "dcat:mediaType" not in d
    assert "dct:format" not in d


def test_dataset_is_shacl_valid_standalone(dcat_shacl_shapes):
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="Réseau routier",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-10T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=[1.0, 44.0, 2.0, 45.0],
    )
    assert doc["@type"] == "dcat:Dataset"
    assert doc["dct:identifier"] == "roads"
    assert doc["dct:license"] == {"@id": s.LICENSE_OTHER}
    assert doc["dct:accessRights"] == {"@id": s.ACCESS_RIGHTS_PUBLIC}
    assert len(doc["dcat:distribution"]) == 2
    assert doc["dcat:distribution"][0]["dcat:accessURL"] == {
        "@id": "http://testserver/collections/roads/items"
    }
    assert doc["dcat:distribution"][1]["dcat:accessURL"] == {
        "@id": "http://testserver/stac/collections/roads/items"
    }
    standalone = {**doc, "@context": s.CONTEXT}
    g = rdflib.Graph()
    g.parse(data=json.dumps(standalone), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_restricted_access_rights_when_not_public():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=False,
        publisher_name="Default",
        bbox=None,
    )
    assert doc["dct:accessRights"] == {"@id": s.ACCESS_RIGHTS_RESTRICTED}
    assert doc["dct:description"] == "Routes"  # repli sur le titre, description vide


def test_dataset_no_bbox_falls_back_to_world():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
    )
    poly = json.loads(doc["dct:spatial"]["locn:geometry"]["@value"])
    assert poly["coordinates"][0][0] == [-180.0, -90.0]


def test_catalog_embeds_datasets_and_is_shacl_valid(dcat_shacl_shapes):
    ds = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="Réseau routier",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-10T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=[1.0, 44.0, 2.0, 45.0],
    )
    cat = s.catalog(base=BASE, tenant_name="Default", datasets=[ds])
    assert cat["@type"] == "dcat:Catalog"
    assert cat["@context"] == s.CONTEXT
    assert cat["dcat:dataset"] == [ds]
    assert cat["dct:publisher"]["foaf:name"] == "Default"
    g = rdflib.Graph()
    g.parse(data=json.dumps(cat), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_catalog_empty_dataset_list_still_valid(dcat_shacl_shapes):
    cat = s.catalog(base=BASE, tenant_name="Default", datasets=[])
    g = rdflib.Graph()
    g.parse(data=json.dumps(cat), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_resolves_declared_license():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="etalab-2.0",
    )
    assert doc["dct:license"] == {"@id": "https://spdx.org/licenses/etalab-2.0.html"}


def test_dataset_other_license_uses_declared_uri():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="other",
        license_uri="https://example.org/my-license",
    )
    assert doc["dct:license"] == {"@id": "https://example.org/my-license"}


def test_dataset_other_license_without_uri_falls_back_to_license_other():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        license="other",
    )
    assert doc["dct:license"] == {"@id": s.LICENSE_OTHER}


def test_dataset_declared_language_overrides_default(dcat_shacl_shapes):
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        language="en",
    )
    assert doc["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/ENG"
    }
    standalone = {**doc, "@context": s.CONTEXT}
    g = rdflib.Graph()
    g.parse(data=json.dumps(standalone), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_omits_new_optional_fields_when_not_declared():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
    )
    assert "dct:accrualPeriodicity" not in doc
    assert "dct:provenance" not in doc
    assert "dcat:contactPoint" not in doc
    assert "dct:hasVersion" not in doc
    assert doc["dct:temporal"] == {
        "@type": "dct:PeriodOfTime",
        "dcat:startDate": {"@value": "2026-07-01T00:00:00Z", "@type": "xsd:dateTime"},
    }
    # dct:language N'EST PAS dans cette liste d'omission : contrairement aux
    # six champs ci-dessus, "language" n'a pas d'état non déclaré (défaut
    # "fr", jamais vide) — il apparaît donc inconditionnellement, exception
    # documentée à la spec §3/§7.2, pas une régression.
    assert doc["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/FRA"
    }


def test_dataset_declares_accrual_periodicity():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        update_frequency="monthly",
    )
    assert doc["dct:accrualPeriodicity"] == {
        "@id": "http://publications.europa.eu/resource/authority/frequency/MONTHLY"
    }


def test_dataset_declares_provenance():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        lineage="Relevé terrain 2026",
    )
    assert doc["dct:provenance"] == {
        "@type": "dct:ProvenanceStatement",
        "rdfs:label": "Relevé terrain 2026",
    }


def test_dataset_contact_point_email_heuristic():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        contact="contact@example.org",
    )
    assert doc["dcat:contactPoint"] == {
        "@type": "vcard:Kind",
        "vcard:hasEmail": "mailto:contact@example.org",
    }


def test_dataset_contact_point_plain_name():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        contact="Service SIG",
    )
    assert doc["dcat:contactPoint"] == {"@type": "vcard:Kind", "vcard:fn": "Service SIG"}


def test_dataset_declares_version():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        version="2.1",
    )
    assert doc["dct:hasVersion"] == "2.1"


def test_dataset_declared_temporal_extent():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        temporal_start="2020-01-01",
        temporal_end="2026-12-31",
    )
    assert doc["dct:temporal"] == {
        "@type": "dct:PeriodOfTime",
        "dcat:startDate": {"@value": "2020-01-01", "@type": "xsd:date"},
        "dcat:endDate": {"@value": "2026-12-31", "@type": "xsd:date"},
    }


def test_dataset_declared_temporal_extent_start_only():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        temporal_start="2020-01-01",
    )
    temporal = doc["dct:temporal"]
    assert temporal["dcat:startDate"] == {"@value": "2020-01-01", "@type": "xsd:date"}
    assert "dcat:endDate" not in temporal


def test_dataset_declared_temporal_extent_end_only_falls_back_to_created_at():
    doc = s.dataset(
        base=BASE,
        collection_id="roads",
        title="Routes",
        description="d",
        created_at="2026-07-01T00:00:00Z",
        updated_at="2026-07-01T00:00:00Z",
        is_public=True,
        publisher_name="Default",
        bbox=None,
        temporal_end="2026-12-31",
    )
    assert doc["dct:temporal"] == {
        "@type": "dct:PeriodOfTime",
        "dcat:startDate": {"@value": "2026-07-01T00:00:00Z", "@type": "xsd:dateTime"},
        "dcat:endDate": {"@value": "2026-12-31", "@type": "xsd:date"},
    }
