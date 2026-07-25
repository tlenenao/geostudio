# SP-12b — Export DCAT-AP (JSON-LD moissonnable) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer le catalogue GeoStudio en DCAT-AP (JSON-LD, lecture seule) via deux nouvelles routes cœur — un dump complet (`GET /dcat/catalog`) et un `dcat:Dataset` dé-référençable (`GET /dcat/datasets/{id}`) — moissonnable par un portail open-data (data.gouv.fr, CKAN, GeoNetwork) sans API interactive ni SPARQL (A21).

**Architecture:** Nouveau module `core/app/dcat/` = `serializers.py` (fonctions pures, dicts JSON-LD, zéro I/O, même discipline que `app/stac/serializers.py`) + `routes.py` (routeur monté sous `/dcat`). Mapping plateforme `Collection` → `dcat:Dataset`, granularité identique à STAC Collection (SP-12a) — aucune descente à la feature. Réutilise `list_visible_collections`/`get_readable_collection` (permissions, 404 non-fuyant) et `app.stac.extent.estimated_bbox_4326` (emprise, aucun nouveau calcul). Aucune surface shell ni MCP.

**Tech Stack:** FastAPI, SQLAlchemy, PostGIS (emprise via `app.stac.extent`), `rdflib`+`pyshacl` (dépendances de **test** uniquement, validation de conformité DCAT-AP offline contre des shapes SHACL officielles vendues statiquement).

## Global Constraints

- **Cœur uniquement.** Aucune modification `shell/` sauf régénération des types (Task 6). Les 43 specs E2E restent inchangées et ne sont pas relancées par ce plan.
- **`rdflib`/`pyshacl` sont des dépendances de TEST** (`[dependency-groups].dev`), jamais un import runtime. Les serializers construisent les dicts JSON-LD à la main, sans dépendance à un contexte JSON-LD distant.
- **`@context` DCAT-AP fixe, en dur** (préfixes `dcat`, `dct`, `foaf`, `locn`, `xsd`) — jamais résolu en ligne.
- **Mapping :** `dcat:Catalog` = catalogue du tenant courant ; `dcat:Dataset` = une plateforme `Collection` (même granularité que STAC Collection, SP-12a) ; `dcat:Distribution` = un point d'accès *existant* (GeoJSON OGC API Features en premier, STAC item-search en second). Aucun nouveau chemin de requête sur les features. Les `items` (apps/dashboards/maps) ne sont pas exposés (même exclusion que STAC, A7).
- **`dct:accessRights` reflète `collection.is_public`** (`.../access-right/PUBLIC` si vrai, `.../access-right/RESTRICTED` sinon) — jamais une constante, contrairement à STAC dont l'audience anonyme est filtrée en amont.
- **`dct:license` = constante EU "autre"** (`http://publications.europa.eu/resource/authority/licence/OTHER`) en dur, symétrique au `license: "other"` de STAC (§2.3 spec) — `Collection` n'a pas de champ licence.
- **`dct:spatial` réutilise `app.stac.extent.estimated_bbox_4326`** (aucun nouveau calcul d'emprise), repli emprise monde silencieux si `None`, sérialisé en `dct:Location`/`locn:geometry` (littéral GeoJSON Polygon, `@type` = l'IRI média-type `application/vnd.geo+json`).
- **`dct:temporal`** : `dcat:startDate = collection.created_at` (RFC3339, `xsd:dateTime`), pas de `dcat:endDate` (ouvert vers le futur) — même simplification que STAC.
- **`dct:publisher` = `Tenant.name`** résolu pour le tenant de l'appelant (anonyme → tenant `default`) — aucune nouvelle variable d'environnement.
- **`dcat:keyword`/`dcat:theme` omis** — `Collection` n'a pas ces données ; jamais de valeur inventée.
- **`Content-Type: application/ld+json`** explicite sur les deux routes (`JSONResponse(..., media_type=...)`), jamais le défaut FastAPI `application/json`.
- **Pas de pagination** : `GET /dcat/catalog` embarque tous les datasets visibles en une réponse (YAGNI, A21).
- **404 non-fuyant** sur `GET /dcat/datasets/{id}` : non lisible/inexistant/cross-tenant → 404, jamais 403 (même convention que STAC/SP-13).
- **Frontière de modules** : `app.dcat` inséré entre `app.ingestion` et `app.stac` dans le contrat `layered architecture` (permet à `app.dcat` d'importer `app.stac.extent` sans inverser la dépendance). `app.dcat` peut aussi importer `app.collections`, `app.tenants`, `app.auth`, `app.features`, `app.db` ; jamais l'inverse.
- Chaque fichier source porte l'en-tête `# SPDX-License-Identifier: Apache-2.0` en première ligne (convention SP-9).
- Commandes : `cd core && uv run pytest ...` ; lint frontières : `cd core && uv run lint-imports`.

---

## Fichiers créés / modifiés

- **Create** `core/app/dcat/__init__.py` — package vide.
- **Create** `core/app/dcat/serializers.py` — fonctions pures : `publisher()`, `distribution()`, `dataset()`, `catalog()`, constantes `CONTEXT`/`LICENSE_OTHER`/`ACCESS_RIGHTS_PUBLIC`/`ACCESS_RIGHTS_RESTRICTED`/`WORLD_BBOX`, helper `_bbox_polygon()`.
- **Create** `core/app/dcat/routes.py` — routeur `/dcat` (`GET /dcat/catalog`, `GET /dcat/datasets/{id}`).
- **Modify** `core/app/main.py` — importer et monter `dcat_routes.router`.
- **Modify** `core/pyproject.toml` — `rdflib`/`pyshacl` en dep de test ; `app.dcat` dans le contrat import-linter.
- **Modify** `core/tests/conftest.py` — fixture partagée `dcat_shacl_shapes` (charge les shapes SHACL vendues une fois par session de test).
- **Create** `core/tests/fixtures/dcat/dcat-ap-SHACL.ttl` — copie statique vendue des shapes SHACL officielles DCAT-AP 2.1.1 (SEMICeu/DCAT-AP), jamais de récupération réseau en test.
- **Create** tests : `core/tests/test_dcat_serializers.py`, `core/tests/test_dcat_routes.py`, `core/tests/test_dcat_integration.py`.
- **Modify** `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts` — régénérés (Task 6).

---

### Task 1: Infra de conformité (deps + shapes SHACL vendues) + `serializers.py` — `CONTEXT`/`publisher()` validés bout-en-bout

**Files:**
- Create: `core/app/dcat/__init__.py`
- Create: `core/app/dcat/serializers.py`
- Create: `core/tests/fixtures/dcat/dcat-ap-SHACL.ttl`
- Modify: `core/pyproject.toml` (ajout `rdflib`/`pyshacl` dev)
- Modify: `core/tests/conftest.py` (fixture `dcat_shacl_shapes`)
- Test: `core/tests/test_dcat_serializers.py`

**Interfaces:**
- Produces:
  - `CONTEXT: dict` — `{"dcat": "http://www.w3.org/ns/dcat#", "dct": "http://purl.org/dc/terms/", "foaf": "http://xmlns.com/foaf/0.1/", "locn": "http://www.w3.org/ns/locn#", "xsd": "http://www.w3.org/2001/XMLSchema#"}`.
  - `LICENSE_OTHER: str`, `ACCESS_RIGHTS_PUBLIC: str`, `ACCESS_RIGHTS_RESTRICTED: str` — IRIs d'autorité EU.
  - `publisher(*, base: str, name: str) -> dict` — noeud `foaf:Agent` (`@id`, `@type`, `foaf:name`).
  - Fixture pytest (`conftest.py`, portée session) `dcat_shacl_shapes -> rdflib.Graph` — shapes SHACL DCAT-AP parsées une fois.

Ce spike GATE (empirique, risque identifié §8 de la spec) prouve que la chaîne rdflib (parse JSON-LD) + pyshacl (validation SHACL) + shapes officielles vendues fonctionne réellement, avant de construire le reste des serializers dessus.

- [ ] **Step 1: Vendorer les shapes SHACL officielles DCAT-AP 2.1.1**

```bash
mkdir -p core/tests/fixtures/dcat
curl -sS --fail -o core/tests/fixtures/dcat/dcat-ap-SHACL.ttl \
  https://raw.githubusercontent.com/SEMICeu/DCAT-AP/master/releases/2.1.1/dcat-ap_2.1.1_shacl_shapes.ttl
```

Run: `wc -l core/tests/fixtures/dcat/dcat-ap-SHACL.ttl`
Expected: `639 core/tests/fixtures/dcat/dcat-ap-SHACL.ttl` (copie exacte vérifiée le 2026-07-19 ; si le nombre de lignes diffère, le fichier amont a changé — relire son diff avant de continuer).

Run: `grep -c "sh:targetClass dcat:Dataset" core/tests/fixtures/dcat/dcat-ap-SHACL.ttl`
Expected: `1` (shape `Dataset_Shape` présente).

- [ ] **Step 2: Ajouter `rdflib`/`pyshacl` aux deps de test**

Dans `core/pyproject.toml`, sous `[dependency-groups] dev = [...]`, ajouter :

```toml
dev = [
    "pytest>=8.2",
    "import-linter>=2.0",
    "pip-audit>=2.7",
    "stac-pydantic>=3.1",  # SP-12a : validation de conformité STAC, offline, dep de test uniquement
    "rdflib>=7.0",  # SP-12b : parse JSON-LD pour validation SHACL, dep de test uniquement
    "pyshacl>=0.25",  # SP-12b : validation SHACL contre les shapes DCAT-AP vendues hors-ligne, dep de test uniquement
]
```

- [ ] **Step 3: Synchroniser l'environnement**

Run: `cd core && uv sync`
Expected: résolution OK, `rdflib`/`pyshacl` (et leurs dépendances transitives `owlrl`, `html5rdf`, `prettytable`) installés, aucune erreur.

- [ ] **Step 4: Ajouter la fixture partagée `dcat_shacl_shapes`**

Dans `core/tests/conftest.py`, ajouter en tête l'import et à la fin le fixture :

```python
from pathlib import Path
```

(ajouter cette ligne aux imports existants en haut du fichier, avec `os`/`pytest`/`sqlalchemy`).

Puis, à la fin du fichier :

```python


@pytest.fixture(scope="session")
def dcat_shacl_shapes():
    """Shapes SHACL DCAT-AP 2.1.1 officielles, vendues statiquement (jamais de
    récupération réseau en test). Chargées une fois par session pytest."""
    import rdflib

    g = rdflib.Graph()
    g.parse(
        Path(__file__).parent / "fixtures" / "dcat" / "dcat-ap-SHACL.ttl",
        format="turtle",
    )
    return g
```

- [ ] **Step 5: Écrire le test qui échoue**

`core/tests/test_dcat_serializers.py` :

```python
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
```

- [ ] **Step 6: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.dcat'`).

- [ ] **Step 7: Créer le package + les serializers**

`core/app/dcat/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
```

`core/app/dcat/serializers.py` :

```python
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
```

- [ ] **Step 8: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: PASS (3 tests).

- [ ] **Step 9: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/tests/conftest.py \
        core/tests/fixtures/dcat/dcat-ap-SHACL.ttl \
        core/app/dcat/__init__.py core/app/dcat/serializers.py \
        core/tests/test_dcat_serializers.py
git commit -m "feat(core): DCAT-AP serializers infra — shapes SHACL vendues, publisher() (SP-12b)"
```

---

### Task 2: Serializers `distribution()` + `_bbox_polygon()` + `dataset()` (classe Dataset), validés SHACL en standalone

**Files:**
- Modify: `core/app/dcat/serializers.py`
- Test: `core/tests/test_dcat_serializers.py`

**Interfaces:**
- Consumes: `CONTEXT`, `LICENSE_OTHER`, `ACCESS_RIGHTS_PUBLIC`, `ACCESS_RIGHTS_RESTRICTED`, `WORLD_BBOX`, `publisher()` (Task 1).
- Produces (utilisés par Task 3 et les routes, Task 4) :
  - `_bbox_polygon(bbox: list[float] | None) -> dict` — GeoJSON Polygon fermé (5 points) depuis `[minx,miny,maxx,maxy]` ; `WORLD_BBOX` si `bbox` est `None`.
  - `distribution(*, title: str, access_url: str, media_type: str | None = None, format_uri: str | None = None) -> dict` — `dcat:Distribution`.
  - `dataset(*, base: str, collection_id: str, title: str, description: str, created_at: str, updated_at: str, is_public: bool, publisher_name: str, bbox: list[float] | None) -> dict` — `dcat:Dataset` **sans** `@context` (destiné à être soit embarqué dans un Catalog, soit complété d'un `@context` par l'appelant pour un usage standalone). `created_at`/`updated_at` sont déjà des chaînes RFC3339 (formatage fait par l'appelant, cf. Task 4). `description` vide → repli sur `title` → repli sur `"No description provided."` (même règle que STAC SP-12a §2.2). Distributions : GeoJSON (OGC API Features) puis STAC item-search, dans cet ordre.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_dcat_serializers.py` :

```python
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
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -k "bbox or distribution or dataset" -v`
Expected: FAIL (`AttributeError: module 'app.dcat.serializers' has no attribute '_bbox_polygon'`).

- [ ] **Step 3: Implémenter `_bbox_polygon`, `distribution`, `dataset`**

Ajouter à `core/app/dcat/serializers.py` :

```python
import json


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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: PASS (tous les tests du fichier, y compris Task 1).

- [ ] **Step 5: Commit**

```bash
git add core/app/dcat/serializers.py core/tests/test_dcat_serializers.py
git commit -m "feat(core): DCAT-AP Dataset + Distribution serializers (SP-12b)"
```

---

### Task 3: Serializer `catalog()` (classe Catalog) — dump complet, validé SHACL avec datasets embarqués

**Files:**
- Modify: `core/app/dcat/serializers.py`
- Test: `core/tests/test_dcat_serializers.py`

**Interfaces:**
- Consumes: `publisher()` (Task 1), `dataset()` (Task 2).
- Produces (utilisé par les routes, Task 4) :
  - `catalog(*, base: str, tenant_name: str, datasets: list[dict]) -> dict` — `dcat:Catalog` avec `@context`, `dct:title`/`dct:description` fixes, `dct:publisher` (via `publisher()`), `dct:language: "fr"`, `dcat:dataset: datasets` (les dicts déjà construits par `dataset()`, embarqués tels quels — pas de `@context` dupliqué par dataset).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_dcat_serializers.py` :

```python
def test_catalog_embeds_datasets_and_is_shacl_valid(dcat_shacl_shapes):
    ds = s.dataset(base=BASE, collection_id="roads", title="Routes",
                  description="Réseau routier", created_at="2026-07-01T00:00:00Z",
                  updated_at="2026-07-10T00:00:00Z", is_public=True,
                  publisher_name="Default", bbox=[1.0, 44.0, 2.0, 45.0])
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
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -k catalog -v`
Expected: FAIL (`AttributeError: module 'app.dcat.serializers' has no attribute 'catalog'`).

- [ ] **Step 3: Implémenter `catalog`**

Ajouter à `core/app/dcat/serializers.py` :

```python
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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_dcat_serializers.py -v`
Expected: PASS (tous les tests du fichier).

- [ ] **Step 5: Commit**

```bash
git add core/app/dcat/serializers.py core/tests/test_dcat_serializers.py
git commit -m "feat(core): DCAT-AP Catalog serializer (SP-12b)"
```

---

### Task 4: Routes `/dcat/catalog` + `/dcat/datasets/{id}` — permissions, Content-Type, montage, import-linter

**Files:**
- Create: `core/app/dcat/routes.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml` (contrat import-linter)
- Test: `core/tests/test_dcat_routes.py`

**Interfaces:**
- Consumes:
  - `serializers.catalog`/`dataset` (Tasks 2-3), `serializers.CONTEXT`.
  - `estimated_bbox_4326` (`app.stac.extent`).
  - `list_visible_collections` (`app.collections.repository`), `get_readable_collection`, `get_introspector` (`app.collections.routes`).
  - `get_rls_scope`, `null_rls_scope` (`app.features.routes`).
  - `get_or_create_default_tenant` (`app.tenants.repository`), `Tenant` (`app.tenants.models`), `get_current_user_optional` (`app.auth.dependency`).
- Produces :
  - `router: APIRouter` (prefix `/dcat`).
  - `get_bbox_provider() -> Callable[[Session, TableInfo], list[float] | None]` — défaut `estimated_bbox_4326`, overridable en test (même patron que `app.stac.routes`).
  - `MEDIA_TYPE = "application/ld+json"`.

- [ ] **Step 1: Écrire les tests qui échouent**

`core/tests/test_dcat_routes.py` (reprend le harnais SQLite de `test_stac_routes.py`) :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.dcat import routes as dcat_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="incidents", pk_column="id", geometry_column="geom",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="titre", type="string", required=True)])


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = (
        lambda: lambda session, table: None)
    app.dependency_overrides[features_routes.get_rls_scope] = (
        lambda: features_routes.null_rls_scope)
    # ST_EstimatedExtent n'existe pas sur SQLite : stub d'emprise.
    app.dependency_overrides[dcat_routes.get_bbox_provider] = (
        lambda: lambda session, info: [1.0, 44.0, 2.0, 45.0])
    return app, TestClient(app), admin


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, *, public=False, description=""):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public,
                                      "description": description})


def test_catalog_content_type_and_shape(env):
    app, client, admin = env
    _register(app, client, admin, public=True, description="Réseau routier")
    resp = client.get("/dcat/catalog")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@type"] == "dcat:Catalog"
    assert len(body["dcat:dataset"]) == 1
    ds = body["dcat:dataset"][0]
    assert ds["dct:identifier"] == "incidents"
    assert ds["dct:description"] == "Réseau routier"
    assert ds["dct:accessRights"]["@id"].endswith("/PUBLIC")
    assert len(ds["dcat:distribution"]) == 2


def test_catalog_reflects_restricted_access_rights(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    resp = client.get("/dcat/catalog")  # vue admin : voit sa propre collection non publique
    ds = resp.json()["dcat:dataset"][0]
    assert ds["dct:accessRights"]["@id"].endswith("/RESTRICTED")


def test_dataset_detail_is_self_contained_with_context(env):
    app, client, admin = env
    _register(app, client, admin, public=True)
    resp = client.get("/dcat/datasets/incidents")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@context"] == {
        "dcat": "http://www.w3.org/ns/dcat#", "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/", "locn": "http://www.w3.org/ns/locn#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    assert body["dct:identifier"] == "incidents"


def test_dataset_detail_404_non_leaking(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    _as(app, admin)
    assert client.get("/dcat/datasets/nope").status_code == 404
    # Anonyme sur collection non publique → 404 non-fuyant.
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/dcat/datasets/incidents").status_code == 404


def test_anonymous_catalog_shows_public_only_no_leak(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    assert client.get("/dcat/catalog").json()["dcat:dataset"] == []
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_dcat_routes.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.dcat.routes'`).

- [ ] **Step 3: Implémenter `routes.py`**

`core/app/dcat/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Routeur DCAT-AP (lecture seule) monté sous /dcat. Réutilise les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant) et l'emprise STAC (app.stac.extent.estimated_bbox_4326) —
aucun nouveau calcul d'emprise, aucune écriture, aucune surface shell/MCP."""
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector, get_readable_collection
from app.dcat import serializers
from app.db import get_session
from app.features.routes import get_rls_scope
from app.stac.extent import estimated_bbox_4326
from app.tenants.models import Tenant

router = APIRouter(prefix="/dcat", tags=["dcat"])

MEDIA_TYPE = "application/ld+json"


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return estimated_bbox_4326


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _rfc3339(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_tenant(session: Session, user) -> Tenant:
    if user is not None:
        return session.get(Tenant, user.tenant_id)
    from app.tenants.repository import get_or_create_default_tenant
    return get_or_create_default_tenant(session)


def _visible_collections(session: Session, user, tenant: Tenant):
    cols = list_visible_collections(
        session, tenant_id=tenant.id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin),
    )
    return sorted(cols, key=lambda c: c.id)


def _dataset_doc(*, base, col, introspect, bbox_provider, rls, session, publisher_name):
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)
    return serializers.dataset(
        base=base, collection_id=col.id, title=col.title,
        description=col.description, created_at=_rfc3339(col.created_at),
        updated_at=_rfc3339(col.updated_at), is_public=col.is_public,
        publisher_name=publisher_name, bbox=bbox)


@router.get("/catalog")
def get_catalog(request: Request, user=Depends(get_current_user_optional),
               session: Session = Depends(get_session),
               introspect=Depends(get_introspector),
               bbox_provider=Depends(get_bbox_provider),
               rls=Depends(get_rls_scope)):
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    cols = _visible_collections(session, user, tenant)
    datasets = [
        _dataset_doc(base=base, col=col, introspect=introspect, bbox_provider=bbox_provider,
                    rls=rls, session=session, publisher_name=tenant.name)
        for col in cols
    ]
    doc = serializers.catalog(base=base, tenant_name=tenant.name, datasets=datasets)
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)


@router.get("/datasets/{collection_id}")
def get_dataset(collection_id: str, request: Request,
               user=Depends(get_current_user_optional),
               session: Session = Depends(get_session),
               introspect=Depends(get_introspector),
               bbox_provider=Depends(get_bbox_provider),
               rls=Depends(get_rls_scope)):
    col = get_readable_collection(session, user, collection_id)  # 404 non-fuyant
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    doc = _dataset_doc(base=base, col=col, introspect=introspect, bbox_provider=bbox_provider,
                       rls=rls, session=session, publisher_name=tenant.name)
    doc["@context"] = serializers.CONTEXT
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)
```

- [ ] **Step 4: Monter le routeur dans `main.py`**

Dans `core/app/main.py`, ajouter l'import à côté des autres (après la ligne `from app.stac import routes as stac_routes`) :

```python
from app.dcat import routes as dcat_routes
```

Note : `app.dcat` importe `app.stac.extent`, donc au niveau des imports Python cette ligne d'import doit rester syntaxiquement où bon vous semble dans `main.py` (l'ordre des lignes d'import n'a pas d'incidence runtime) — seul le contrat import-linter (Step 5) encode la vraie contrainte de couches.

Et l'inclusion, après `app.include_router(stac_routes.router)` :

```python
    app.include_router(dcat_routes.router)
```

- [ ] **Step 5: Ajouter `app.dcat` au contrat import-linter**

Dans `core/pyproject.toml`, contrat `layered architecture`, insérer `"app.dcat"` entre `"app.ingestion"` et `"app.stac"` :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

- [ ] **Step 6: Lancer les tests + le lint de frontières**

Run: `cd core && uv run pytest tests/test_dcat_routes.py -v && uv run lint-imports`
Expected: tests PASS (5 tests) ; `lint-imports` : contrat `layered architecture` **Kept**.

- [ ] **Step 7: Commit**

```bash
git add core/app/dcat/routes.py core/app/main.py core/pyproject.toml core/tests/test_dcat_routes.py
git commit -m "feat(core): DCAT-AP routes — /dcat/catalog + /dcat/datasets/{id} (SP-12b)"
```

---

### Task 5: Test d'intégration PostGIS bout-en-bout + adversarial anonyme + conformité SHACL sur payload réel

**Files:**
- Test: `core/tests/test_dcat_integration.py`

**Interfaces:**
- Consumes : toute la surface `/dcat` (Task 4), le vrai introspecteur/DDL/RLS (pas d'override de bbox_provider ni de scope), `dcat_shacl_shapes` (Task 1), pattern de seed de `test_stac_integration.py`.

- [ ] **Step 1: Écrire le test d'intégration**

`core/tests/test_dcat_integration.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Bout en bout DCAT-AP sur PostGIS réel : vrai introspecteur, vraie DDL RLS,
vraie emprise ST_EstimatedExtent (app.stac.extent, réutilisée telle quelle).
Couvre §10 : dump complet, dataset dé-référençable, portée anonyme
publié/public sans fuite, conformité SHACL sur un payload réellement produit
par les routes (pas seulement les serializers en isolation, Tasks 1-3)."""
import json

import pytest
import rdflib
from fastapi.testclient import TestClient
from pyshacl import validate
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dcat_roads"))
        conn.execute(text("CREATE TABLE dcat_roads (id serial PRIMARY KEY, "
                          "n text, geom geometry(Point, 4326))"))
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    yield app, TestClient(app)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dcat_roads"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def _seed(app, client, public):
    client.post("/collections", json={"tableName": "dcat_roads", "isPublic": public,
                                      "description": "Réseau routier"})
    for lon, lat in [(1.0, 44.0), (2.0, 45.0), (3.0, 46.0)]:
        client.post("/collections/dcat_roads/items", json={
            "type": "Feature", "properties": {"n": "x"},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}})


def test_full_dcat_dump_is_shacl_valid_with_real_bbox(pg_app, dcat_shacl_shapes):
    app, client = pg_app
    _seed(app, client, public=True)

    cat = client.get("/dcat/catalog")
    assert cat.headers["content-type"] == "application/ld+json"
    body = cat.json()
    ds = body["dcat:dataset"][0]
    poly = json.loads(ds["dct:spatial"]["locn:geometry"]["@value"])
    xs = [p[0] for p in poly["coordinates"][0]]
    ys = [p[1] for p in poly["coordinates"][0]]
    assert min(xs) == pytest.approx(1.0, abs=0.5) and max(xs) == pytest.approx(3.0, abs=0.5)
    assert min(ys) == pytest.approx(44.0, abs=0.5) and max(ys) == pytest.approx(46.0, abs=0.5)

    g = rdflib.Graph()
    g.parse(data=json.dumps(body), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_dataset_detail_is_shacl_valid_standalone(pg_app, dcat_shacl_shapes):
    app, client = pg_app
    _seed(app, client, public=True)
    body = client.get("/dcat/datasets/dcat_roads").json()
    g = rdflib.Graph()
    g.parse(data=json.dumps(body), format="json-ld")
    conforms, _, text = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text


def test_anonymous_sees_public_only_no_leak(pg_app):
    app, client = pg_app
    _seed(app, client, public=False)  # non publique
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/dcat/catalog").json()["dcat:dataset"] == []
    # Collection non publique → 404 non-fuyant (indistinguable d'inexistante).
    assert client.get("/dcat/datasets/dcat_roads").status_code == 404
    assert client.get("/dcat/datasets/does-not-exist").status_code == 404
```

- [ ] **Step 2: Lancer le test contre un PostGIS jetable**

Run: `cd core && CORE_TEST_DATABASE_URL=$CORE_TEST_DATABASE_URL uv run pytest tests/test_dcat_integration.py -v -m postgis`
Expected: PASS (3 tests). Si `CORE_TEST_DATABASE_URL` absent : skippé — **le lancer réellement contre un conteneur PostGIS+pgvector avant de clore la tâche** (ne pas se fier au skip).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_dcat_integration.py
git commit -m "test(core): DCAT-AP end-to-end PostGIS + adversarial anonymous + SHACL on real payload (SP-12b)"
```

---

### Task 6: Régénération OpenAPI + types shell (dérive `api-types-drift`)

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:** aucune nouvelle interface ; synchronise les artefacts générés que le job CI `api-types-drift` compare.

- [ ] **Step 1: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: fichier réécrit, contient les chemins `/dcat/catalog` et `/dcat/datasets/{collection_id}`.

- [ ] **Step 2: Vérifier la présence des nouveaux chemins**

Run: `cd core && grep -c '"/dcat' openapi.json`
Expected: `2`.

- [ ] **Step 3: Régénérer les types TypeScript du shell**

Run: `cd shell && npm run gen:api-types`
Expected: `src/api/generated/core-schema.d.ts` réécrit sans erreur `openapi-typescript`.

- [ ] **Step 4: Vérifier que le build shell reste vert (tsc)**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` + `vite build` OK (le shell n'utilise pas ces types, mais ils doivent compiler).

- [ ] **Step 5: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(api): regenerate OpenAPI + shell types for DCAT-AP endpoints (SP-12b)"
```

---

## Validation finale de branche

- [ ] **Suite cœur complète (sans DB)** : `cd core && uv run pytest` → tous verts, nouveaux tests DCAT inclus (serializers, routes, gate SHACL) ; tests `postgis` skippés proprement.
- [ ] **Suite cœur avec PostGIS réel** : `cd core && CORE_TEST_DATABASE_URL=... uv run pytest -m postgis` → `test_dcat_integration` vert (dont conformité SHACL sur un dump réel).
- [ ] **Frontières** : `cd core && uv run lint-imports` → `layered architecture` Kept (`app.dcat` correctement placé entre `app.ingestion` et `app.stac`).
- [ ] **Pas de dérive OpenAPI** : `cd core && uv run python scripts/export_openapi.py /tmp/openapi-check.json && diff openapi.json /tmp/openapi-check.json` → aucune différence.
- [ ] **Smoke d'acceptation documenté (non bloquant)** : contre une instance vive seedée, soumettre `GET /dcat/catalog` au validateur DCAT-AP data.gouv.fr (ou son équivalent SHACL en ligne) ; consigner le résultat dans le rapport de tâche. **Si ce smoke révèle un champ obligatoire non couvert par le profil SHACL générique vendu hors-ligne** (ex. `dcat:theme` exigé par un profil FR strict), documenter précisément le gap ici en suivi — ne pas le deviner par avance. Non exécuté par la CI.
- [ ] **Revue finale de branche** (modèle opus) : tracer bout-en-bout la propriété d'anonymat non-fuyant (`/dcat/catalog` anonyme ne montre que le publié/public, `/dcat/datasets/{id}` 404 non-fuyant identique à STAC) et l'absence de fuite cross-tenant ; vérifier qu'aucune route DCAT n'a été oubliée dans `read_only_guard` (elles sont `GET`, donc déjà hors de son périmètre — confirmer qu'aucun ajout involontaire de méthode d'écriture n'a eu lieu).

---

## Self-review (couverture spec)

| Section spec | Task(s) |
|---|---|
| §1 périmètre (2 routes lecture seule, cœur uniquement, aucun nouvel endpoint de données) | 4 |
| §2.1 mapping Collection→Dataset, Distribution→endpoints existants | 2, 3 |
| §2.2 `dct:accessRights` reflète `is_public`, jamais une constante | 2, 4 |
| §2.3 `dct:license` constante EU "autre" | 2 |
| §2.4 `dct:spatial` réutilise `estimated_bbox_4326`, repli monde silencieux | 2, 4, 5 |
| §2.5 `dct:temporal` simplifié (startDate seul) | 2 |
| §2.6 `dct:publisher` = `Tenant.name`, aucune nouvelle variable d'env | 1, 3, 4 |
| §2.7 `dcat:keyword`/`dcat:theme` omis, jamais inventés | 2 (absence testée implicitement — aucune clé émise) |
| §3 module `app/dcat/` (serializers/routes), frontière import-linter | 1, 4 |
| §4 surface d'endpoints + Content-Type `application/ld+json` | 4 |
| §5.1-5.4 objets DCAT-AP (@context, Catalog, Dataset, Distribution) | 1, 2, 3 |
| §6 permissions (list_visible_collections, get_readable_collection, 404, RLS, adversarial) | 4, 5 |
| §7 pas de pagination (dump complet) | 4 |
| §8 gate rdflib+pyshacl offline + intégration postgis + smoke documenté | 1-3, 5, validation finale |
| §9 dérive OpenAPI régénérée | 6 |
| §10 critères d'acceptation | 5 + validation finale |
| §11 risques & simplifications assumées | documentés dans Global Constraints + serializers |
