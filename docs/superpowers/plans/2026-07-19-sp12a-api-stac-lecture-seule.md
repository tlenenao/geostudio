# SP-12a — API STAC native (lecture seule) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer le catalogue de données GeoStudio via une API STAC native, lecture seule, dans le cœur (classes core → collections → features → item-search), sur les tables `collections`/features existantes, en respectant les permissions.

**Architecture:** Nouveau module `core/app/stac/` = serializers **purs** (dicts STAC, zéro I/O) + `extent.py` (emprise PostGIS estimée reprojetée 4326) + `routes.py` (routeur monté sous `/stac`). Les routes réutilisent le chemin de requête OGC Features de SP-3b (`select_features`/`get_feature`, `rls_scope`) et les portes de permission existantes (`list_visible_collections`, `get_readable_collection`, 404 non-fuyant). Aucune surface shell ni MCP.

**Tech Stack:** FastAPI, SQLAlchemy (SQL brut paramétré), PostGIS (`ST_EstimatedExtent`/`ST_Transform`), `stac-pydantic` (dépendance **de test** uniquement, validation de conformité offline).

## Global Constraints

- **Cœur uniquement.** Aucune modification `shell/` sauf régénération des types (Task 9). Les 38 specs E2E restent inchangées et ne sont pas relancées par ce plan.
- **`stac-pydantic` est une dépendance de TEST** (`[dependency-groups].dev`), jamais un import runtime. Les serializers construisent les dicts à la main.
- **`stac_version` = `"1.0.0"`** partout.
- **`conformsTo` annoncé** (verbatim, ordre libre) :
  - `https://api.stacspec.org/v1.0.0/core`
  - `https://api.stacspec.org/v1.0.0/collections`
  - `https://api.stacspec.org/v1.0.0/ogcapi-features`
  - `https://api.stacspec.org/v1.0.0/item-search`
  - `http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core`
  - `http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30`
  - `http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson`
- **`license: "other"`** en dur sur chaque STAC Collection (§2.4, les collections n'ont pas de champ licence).
- **`datetime` synthétique** : tout STAC Item porte le `updated_at` de sa collection en RFC3339 (§2.2). `datetime` est une clé réservée dans `properties` (écrase un attribut homonyme).
- **404 non-fuyant** : une collection non lisible (anonyme/cross-tenant/non-publiée) renvoie 404, jamais 403 (convention SP-13). Anonyme → tenant `default` + publié/public seulement.
- **Préfixe `/stac`** : pas de collision avec les routes OGC Features racine (`GET /`, `GET /collections/...`).
- **Frontière de modules** : `app.stac` importe `app.collections`, `app.features`, `app.auth`, `app.tenants`, `app.db` ; jamais l'inverse. Contrat import-linter (Task 5).
- Chaque fichier source porte l'en-tête `# SPDX-License-Identifier: Apache-2.0` en première ligne (convention SP-9).
- Commandes : `cd core && uv run pytest ...` ; lint frontières : `cd core && uv run lint-imports`.

---

## Fichiers créés / modifiés

- **Create** `core/app/stac/__init__.py` — package vide.
- **Create** `core/app/stac/serializers.py` — fonctions pures : `conformance()`, `catalog()`, `collection()`, `item()`, `item_collection()`, constantes `STAC_VERSION`/`CONFORMANCE_CLASSES`, helper `_geojson_bbox()`.
- **Create** `core/app/stac/extent.py` — `estimated_bbox_4326(session, info)`.
- **Create** `core/app/stac/routes.py` — routeur `/stac` (landing, conformance, collections, items, search).
- **Modify** `core/app/main.py` — importer et monter `stac_routes.router`.
- **Modify** `core/pyproject.toml` — `stac-pydantic` en dep de test ; `app.stac` dans le contrat import-linter.
- **Modify** `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts` — régénérés (Task 9).
- **Create** tests : `core/tests/test_stac_serializers.py`, `core/tests/test_stac_extent.py`, `core/tests/test_stac_routes.py`, `core/tests/test_stac_search.py`, `core/tests/test_stac_integration.py`.

---

### Task 1: Serializers purs — conformance + landing Catalog (classe Core), validés stac-pydantic

**Files:**
- Create: `core/app/stac/__init__.py`
- Create: `core/app/stac/serializers.py`
- Modify: `core/pyproject.toml` (ajout `stac-pydantic` dev)
- Test: `core/tests/test_stac_serializers.py`

**Interfaces:**
- Produces:
  - `STAC_VERSION: str = "1.0.0"`
  - `CONFORMANCE_CLASSES: list[str]` (les 7 URIs des Global Constraints)
  - `conformance() -> dict` → `{"conformsTo": CONFORMANCE_CLASSES}`
  - `catalog(*, base: str, collection_ids: list[str]) -> dict` — Catalog landing avec `conformsTo` + links (self, root, `data`, `search`, `conformance`, un `child` par collection). `base` = racine du serveur sans slash final (ex. `http://testserver`).

- [ ] **Step 1: Ajouter `stac-pydantic` aux deps de test**

Dans `core/pyproject.toml`, sous `[dependency-groups] dev = [...]`, ajouter une entrée :

```toml
dev = [
    "pytest>=8.2",
    "import-linter>=2.0",
    "pip-audit>=2.7",
    "stac-pydantic>=3.1",  # SP-12a : validation de conformité STAC, offline, dep de test uniquement
]
```

- [ ] **Step 2: Synchroniser l'environnement**

Run: `cd core && uv sync`
Expected: résolution OK, `stac-pydantic` (et sa dépendance `pydantic`) installé, aucune erreur.

- [ ] **Step 3: Écrire le test qui échoue**

`core/tests/test_stac_serializers.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from stac_pydantic import Catalog

from app.stac import serializers as s

BASE = "http://testserver"

EXPECTED_CONFORMANCE = {
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
    "https://api.stacspec.org/v1.0.0/item-search",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
}


def test_conformance_lists_all_classes():
    assert set(s.conformance()["conformsTo"]) == EXPECTED_CONFORMANCE


def test_catalog_is_valid_and_links_children():
    cat = s.catalog(base=BASE, collection_ids=["roads", "rivers"])
    assert cat["type"] == "Catalog"
    assert cat["stac_version"] == "1.0.0"
    assert set(cat["conformsTo"]) == EXPECTED_CONFORMANCE
    rels = {l["rel"]: l["href"] for l in cat["links"]}
    assert rels["self"] == f"{BASE}/stac"
    assert rels["data"] == f"{BASE}/stac/collections"
    assert rels["search"] == f"{BASE}/stac/search"
    assert rels["conformance"] == f"{BASE}/stac/conformance"
    children = [l["href"] for l in cat["links"] if l["rel"] == "child"]
    assert children == [f"{BASE}/stac/collections/roads", f"{BASE}/stac/collections/rivers"]
    # stac-pydantic Catalog ne connaît pas conformsTo (champ STAC-API) : le retirer avant validation.
    Catalog.model_validate({k: v for k, v in cat.items() if k != "conformsTo"})
```

- [ ] **Step 4: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -v`
Expected: FAIL (`ModuleNotFoundError: app.stac` ou `AttributeError`).

- [ ] **Step 5: Créer le package + les serializers**

`core/app/stac/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
```

`core/app/stac/serializers.py` :

```python
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
```

- [ ] **Step 6: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/app/stac/__init__.py core/app/stac/serializers.py core/tests/test_stac_serializers.py
git commit -m "feat(core): STAC serializers — conformance + landing Catalog (SP-12a)"
```

---

### Task 2: Serializer STAC Collection (classe Collections)

**Files:**
- Modify: `core/app/stac/serializers.py`
- Test: `core/tests/test_stac_serializers.py`

**Interfaces:**
- Consumes: `STAC_VERSION`, `catalog` (Task 1).
- Produces:
  - `collection(*, base: str, collection_id: str, title: str, description: str, bbox: list[float] | None, temporal_start: str | None) -> dict` — STAC Collection. `bbox` None → emprise monde `[-180, -90, 180, 90]` avec note. `temporal_start` = RFC3339 de `created_at` (intervalle ouvert `[[temporal_start, None]]`). `license: "other"` en dur. Links : self, root, parent (→ landing), `items` (→ .../items).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_stac_serializers.py` :

```python
from stac_pydantic import Collection


def test_collection_valid_with_bbox_and_temporal():
    col = s.collection(base=BASE, collection_id="roads", title="Routes",
                       description="Réseau routier", bbox=[1.0, 44.0, 2.0, 45.0],
                       temporal_start="2026-07-01T00:00:00Z")
    assert col["type"] == "Collection"
    assert col["license"] == "other"
    assert col["extent"]["spatial"]["bbox"] == [[1.0, 44.0, 2.0, 45.0]]
    assert col["extent"]["temporal"]["interval"] == [["2026-07-01T00:00:00Z", None]]
    rels = {l["rel"]: l["href"] for l in col["links"]}
    assert rels["self"] == f"{BASE}/stac/collections/roads"
    assert rels["items"] == f"{BASE}/stac/collections/roads/items"
    assert rels["parent"] == f"{BASE}/stac"
    Collection.model_validate(col)


def test_collection_without_bbox_falls_back_to_world():
    col = s.collection(base=BASE, collection_id="empty", title="Vide",
                       description="", bbox=None, temporal_start=None)
    assert col["extent"]["spatial"]["bbox"] == [[-180.0, -90.0, 180.0, 90.0]]
    assert col["extent"]["temporal"]["interval"] == [[None, None]]
    assert "note" in col
    Collection.model_validate(col)
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -k collection -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'collection'`).

- [ ] **Step 3: Implémenter `collection`**

Ajouter à `core/app/stac/serializers.py` :

```python
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
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -k collection -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add core/app/stac/serializers.py core/tests/test_stac_serializers.py
git commit -m "feat(core): STAC Collection serializer (SP-12a)"
```

---

### Task 3: Serializers STAC Item + ItemCollection (classe Features)

**Files:**
- Modify: `core/app/stac/serializers.py`
- Test: `core/tests/test_stac_serializers.py`

**Interfaces:**
- Consumes: `STAC_VERSION` (Task 1).
- Produces:
  - `item(*, base: str, collection_id: str, feature: dict, datetime_value: str) -> dict` — STAC Item depuis une feature GeoJSON (`{"type":"Feature","id":..,"geometry":..,"properties":{..}}`). `id` = `str(feature["id"])`. `bbox` calculé depuis la géométrie (None si géométrie None). `properties.datetime = datetime_value` (écrase un attribut homonyme). `assets: {}`. Links : self, parent (→ collection), collection, root.
  - `item_collection(*, items: list[dict], links: list[dict]) -> dict` — `{"type":"FeatureCollection","features":items,"links":links}`.
  - `_geojson_bbox(geometry: dict | None) -> list[float] | None` — bbox `[minx,miny,maxx,maxy]` par parcours récursif des coordonnées (None si géométrie None/vide).

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à `core/tests/test_stac_serializers.py` :

```python
from stac_pydantic import Item, ItemCollection

DT = "2026-07-10T12:00:00Z"
FEAT = {"type": "Feature", "id": 7,
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
        "properties": {"titre": "Nid de poule", "datetime": "OVERRIDE-ME"}}


def test_item_valid_with_bbox_and_synthetic_datetime():
    it = s.item(base=BASE, collection_id="roads", feature=FEAT, datetime_value=DT)
    assert it["type"] == "Feature"
    assert it["id"] == "7"  # coercé en str
    assert it["collection"] == "roads"
    assert it["bbox"] == [1.85, 45.27, 1.85, 45.27]
    assert it["properties"]["datetime"] == DT  # écrase l'attribut homonyme de la feature
    assert it["properties"]["titre"] == "Nid de poule"
    assert it["assets"] == {}
    rels = {l["rel"]: l["href"] for l in it["links"]}
    assert rels["self"] == f"{BASE}/stac/collections/roads/items/7"
    assert rels["collection"] == f"{BASE}/stac/collections/roads"
    Item.model_validate(it)


def test_item_null_geometry_has_null_bbox():
    feat = {"type": "Feature", "id": "abc", "geometry": None, "properties": {}}
    it = s.item(base=BASE, collection_id="roads", feature=feat, datetime_value=DT)
    assert it["geometry"] is None
    assert it["bbox"] is None
    Item.model_validate(it)


def test_geojson_bbox_polygon():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 3], [0, 3], [0, 0]]]}
    assert s._geojson_bbox(geom) == [0.0, 0.0, 2.0, 3.0]


def test_item_collection_wraps():
    it = s.item(base=BASE, collection_id="roads", feature=FEAT, datetime_value=DT)
    ic = s.item_collection(items=[it], links=[{"rel": "self", "href": f"{BASE}/stac/search"}])
    assert ic["type"] == "FeatureCollection"
    assert ic["features"] == [it]
    ItemCollection.model_validate(ic)
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -k "item or bbox" -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implémenter `item`, `item_collection`, `_geojson_bbox`**

Ajouter à `core/app/stac/serializers.py` :

```python
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
            {"rel": "self", "type": "application/geo+json",
             "href": f"{base}/stac/collections/{collection_id}/items/{fid}"},
            {"rel": "parent", "type": "application/json",
             "href": f"{base}/stac/collections/{collection_id}"},
            {"rel": "collection", "type": "application/json",
             "href": f"{base}/stac/collections/{collection_id}"},
            {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
        ],
    }


def item_collection(*, items: list[dict], links: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": items, "links": links}
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_stac_serializers.py -v`
Expected: PASS (tous les tests du fichier, y compris Task 1/2).

- [ ] **Step 5: Commit**

```bash
git add core/app/stac/serializers.py core/tests/test_stac_serializers.py
git commit -m "feat(core): STAC Item + ItemCollection serializers (SP-12a)"
```

---

### Task 4: Emprise estimée reprojetée 4326 (`extent.py`)

**Files:**
- Create: `core/app/stac/extent.py`
- Test: `core/tests/test_stac_extent.py`

**Interfaces:**
- Consumes: `TableInfo` (`app.collections.introspection`), `quote_ident` (`app.collections.ddl`).
- Produces:
  - `estimated_bbox_4326(session, info: TableInfo) -> list[float] | None` — `[minx,miny,maxx,maxy]` en 4326 via `ST_EstimatedExtent`, repli `ST_Extent` si stats absentes. `None` si pas de colonne géométrie **ou** table vide.

- [ ] **Step 1: Écrire le test qui échoue**

`core/tests/test_stac_extent.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.introspection import ColumnInfo, TableInfo
from app.stac.extent import estimated_bbox_4326

NO_GEOM = TableInfo(table_name="t", pk_column="id", geometry_column=None,
                    geometry_type=None, srid=None,
                    columns=[ColumnInfo(name="id", type="integer", required=True)])


def test_no_geometry_column_returns_none_without_db():
    # Chemin toujours exécuté (aucun accès SQL) : geometry_column None → None.
    assert estimated_bbox_4326(session=None, info=NO_GEOM) is None


@pytest.mark.postgis
def test_estimated_bbox_reprojected(pg_session_factory):
    info = TableInfo(table_name="stac_extent_t", pk_column="id",
                     geometry_column="geom", geometry_type="Point", srid=4326,
                     columns=[ColumnInfo(name="id", type="integer", required=True)])
    with pg_session_factory() as s:
        s.execute(text("DROP TABLE IF EXISTS stac_extent_t"))
        s.execute(text("CREATE TABLE stac_extent_t (id serial PRIMARY KEY, "
                       "geom geometry(Point, 4326))"))
        s.execute(text("INSERT INTO stac_extent_t (geom) VALUES "
                       "(ST_SetSRID(ST_MakePoint(1.0, 44.0), 4326)), "
                       "(ST_SetSRID(ST_MakePoint(2.0, 45.0), 4326))"))
        s.execute(text("ANALYZE stac_extent_t"))
        s.commit()
        bbox = estimated_bbox_4326(s, info)
        assert bbox is not None
        assert bbox[0] == pytest.approx(1.0, abs=0.01)
        assert bbox[1] == pytest.approx(44.0, abs=0.01)
        assert bbox[2] == pytest.approx(2.0, abs=0.01)
        assert bbox[3] == pytest.approx(45.0, abs=0.01)
        s.execute(text("DROP TABLE IF EXISTS stac_extent_t"))
        s.commit()
```

- [ ] **Step 2: Lancer le test always-run, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_stac_extent.py::test_no_geometry_column_returns_none_without_db -v`
Expected: FAIL (`ModuleNotFoundError: app.stac.extent`).

- [ ] **Step 3: Implémenter `extent.py`**

`core/app/stac/extent.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale STAC d'une collection : ST_EstimatedExtent (rapide, via les
stats ANALYZE), repli ST_Extent quand les stats sont absentes, toujours
reprojetée en 4326. Les emprises STAC étant advisory, l'approximation par
statistiques est assumée (§2.3). None si pas de géométrie ou table vide →
l'appelant retombe sur l'emprise monde."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import TableInfo


def _box_4326(session: Session, inner_sql: str, params: dict) -> list[float] | None:
    row = session.execute(text(
        f"SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM "
        f"(SELECT ST_Transform(ST_SetSRID(({inner_sql})::geometry, :srid), 4326) AS g) s "
        f"WHERE g IS NOT NULL"
    ), params).one_or_none()
    return [row[0], row[1], row[2], row[3]] if row else None


def estimated_bbox_4326(session: Session, info: TableInfo) -> list[float] | None:
    if info.geometry_column is None:
        return None
    srid = info.srid or 4326
    est = _box_4326(
        session, "ST_EstimatedExtent(:schema, :table, :geom)",
        {"schema": "public", "table": info.table_name,
         "geom": info.geometry_column, "srid": srid},
    )
    if est is not None:
        return est
    # Stats absentes (ST_EstimatedExtent NULL) : repli exact sur ST_Extent.
    t = quote_ident(session, info.table_name)
    g = quote_ident(session, info.geometry_column)
    return _box_4326(session, f"SELECT ST_Extent({g}) FROM public.{t}", {"srid": srid})
```

- [ ] **Step 4: Lancer le test always-run, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_stac_extent.py::test_no_geometry_column_returns_none_without_db -v`
Expected: PASS.

- [ ] **Step 5: Lancer le test postgis (si `CORE_TEST_DATABASE_URL` disponible)**

Run: `cd core && CORE_TEST_DATABASE_URL=$CORE_TEST_DATABASE_URL uv run pytest tests/test_stac_extent.py -v -m postgis`
Expected: PASS (bbox ≈ `[1,44,2,45]`). Si non disponible : skippé (documenter le skip).

- [ ] **Step 6: Commit**

```bash
git add core/app/stac/extent.py core/tests/test_stac_extent.py
git commit -m "feat(core): STAC estimated extent reprojected to 4326 (SP-12a)"
```

---

### Task 5: Routes STAC — landing, conformance, collections list, collection detail + montage + import-linter

**Files:**
- Create: `core/app/stac/routes.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml` (contrat import-linter)
- Test: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes:
  - `serializers.catalog/conformance/collection` (Tasks 1-2), `estimated_bbox_4326` (Task 4).
  - `list_visible_collections` (`app.collections.repository`), `get_readable_collection` (`app.collections.routes`), `get_introspector` (`app.collections.routes`).
  - `get_features_repo`, `get_rls_scope`, `null_rls_scope` (`app.features.routes`).
  - `get_or_create_default_tenant` (`app.tenants.repository`), `get_current_user_optional` (`app.auth.dependency`).
- Produces (utilisés par Tasks 6-7) :
  - `router: APIRouter` (prefix `/stac`).
  - `get_bbox_provider() -> Callable[[Session, TableInfo], list[float] | None]` — défaut `estimated_bbox_4326`, overridable en test.
  - `_visible_collections(session, user) -> list[Collection]` — collections visibles du tenant courant (défaut pour anonyme), triées par `id`.
  - `_base(request) -> str` — `str(request.base_url).rstrip("/")`.
  - `_rfc3339(dt) -> str` — datetime → RFC3339 UTC (`...Z`).

- [ ] **Step 1: Écrire les tests qui échouent**

`core/tests/test_stac_routes.py` (reprend le harnais SQLite de `test_features_routes_read.py`) :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.stac import routes as stac_routes
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
    app.dependency_overrides[stac_routes.get_bbox_provider] = (
        lambda: lambda session, info: [1.0, 44.0, 2.0, 45.0])
    return app, TestClient(app), admin


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_landing_advertises_conformance(env):
    app, client, _admin = env
    body = client.get("/stac").json()
    assert body["type"] == "Catalog"
    assert "https://api.stacspec.org/v1.0.0/item-search" in body["conformsTo"]


def test_conformance_endpoint(env):
    app, client, _admin = env
    body = client.get("/stac/conformance").json()
    assert "https://api.stacspec.org/v1.0.0/core" in body["conformsTo"]


def test_collections_list_shows_registered(env):
    app, client, admin = env
    _register(app, client, admin)
    body = client.get("/stac/collections").json()
    ids = [c["id"] for c in body["collections"]]
    assert "incidents" in ids
    assert body["collections"][0]["license"] == "other"


def test_collection_detail_and_leakproof_404(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    _as(app, admin)
    assert client.get("/stac/collections/incidents").json()["id"] == "incidents"
    assert client.get("/stac/collections/nope").status_code == 404
    # Anonyme sur collection non publique → 404 non-fuyant.
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/stac/collections/incidents").status_code == 404


def test_anonymous_lists_public_only(env):
    app, client, admin = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    assert client.get("/stac/collections").json()["collections"] == []
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_stac_routes.py -v`
Expected: FAIL (`ModuleNotFoundError: app.stac.routes`).

- [ ] **Step 3: Implémenter `routes.py` (landing/conformance/collections)**

`core/app/stac/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Routeur STAC (lecture seule) monté sous /stac. Réutilise le chemin de
requête OGC Features (select_features/get_feature, rls_scope) et les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant). Aucune écriture, aucune surface shell/MCP."""
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.routes import get_features_repo, get_rls_scope
from app.stac import serializers
from app.stac.extent import estimated_bbox_4326

router = APIRouter(prefix="/stac", tags=["stac"])

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return estimated_bbox_4326


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _rfc3339(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _visible_collections(session: Session, user):
    if user is not None:
        tenant_id = user.tenant_id
    else:
        from app.tenants.repository import get_or_create_default_tenant
        tenant_id = get_or_create_default_tenant(session).id
    cols = list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin),
    )
    return sorted(cols, key=lambda c: c.id)


@router.get("")
def landing(request: Request, user=Depends(get_current_user_optional),
            session: Session = Depends(get_session)):
    cols = _visible_collections(session, user)
    return serializers.catalog(base=_base(request), collection_ids=[c.id for c in cols])


@router.get("/conformance")
def conformance():
    return serializers.conformance()


@router.get("/collections")
def list_collections(request: Request, user=Depends(get_current_user_optional),
                     session: Session = Depends(get_session),
                     introspect=Depends(get_introspector),
                     bbox_provider=Depends(get_bbox_provider),
                     rls=Depends(get_rls_scope)):
    docs = []
    for col in _visible_collections(session, user):
        info = introspect(session, col.table_name)
        with rls(session, col.tenant_id):
            bbox = bbox_provider(session, info)
        docs.append(serializers.collection(
            base=_base(request), collection_id=col.id, title=col.title,
            description=col.description or "", bbox=bbox,
            temporal_start=_rfc3339(col.created_at)))
    return {"collections": docs,
            "links": [{"rel": "self", "type": "application/json",
                       "href": f"{_base(request)}/stac/collections"},
                      {"rel": "root", "type": "application/json",
                       "href": f"{_base(request)}/stac"}]}


@router.get("/collections/{collection_id}")
def get_collection(collection_id: str, request: Request,
                   user=Depends(get_current_user_optional),
                   session: Session = Depends(get_session),
                   introspect=Depends(get_introspector),
                   bbox_provider=Depends(get_bbox_provider),
                   rls=Depends(get_rls_scope)):
    col = get_readable_collection(session, user, collection_id)  # 404 non-fuyant
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)
    return serializers.collection(
        base=_base(request), collection_id=col.id, title=col.title,
        description=col.description or "", bbox=bbox,
        temporal_start=_rfc3339(col.created_at))
```

- [ ] **Step 4: Monter le routeur dans `main.py`**

Dans `core/app/main.py`, ajouter l'import à côté des autres (après la ligne `from app.sharing import routes as sharing_routes`) :

```python
from app.stac import routes as stac_routes
```

Et l'inclusion, après `app.include_router(ingestion_routes.router)` :

```python
    app.include_router(stac_routes.router)
```

- [ ] **Step 5: Ajouter `app.stac` au contrat import-linter**

Dans `core/pyproject.toml`, contrat `layered architecture`, insérer `"app.stac"` entre `"app.ingestion"` et `"app.features"` :

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.stac",
    "app.features",
    "app.collections",
    ...
]
```

- [ ] **Step 6: Lancer les tests + le lint de frontières**

Run: `cd core && uv run pytest tests/test_stac_routes.py -v && uv run lint-imports`
Expected: tests PASS (6 tests) ; `lint-imports` : contrat `layered architecture` **Kept**.

- [ ] **Step 7: Commit**

```bash
git add core/app/stac/routes.py core/app/main.py core/pyproject.toml core/tests/test_stac_routes.py
git commit -m "feat(core): STAC routes — landing, conformance, collections (SP-12a)"
```

---

### Task 6: Routes STAC — items d'une collection + item unique (pagination `next`)

**Files:**
- Modify: `core/app/stac/routes.py`
- Test: `core/tests/test_stac_routes.py`

**Interfaces:**
- Consumes: `serializers.item/item_collection`, `_base`, `_rfc3339`, `get_features_repo`, `get_rls_scope`, `get_introspector`, `get_readable_collection`, `MAX_LIMIT`, `DEFAULT_LIMIT` (Task 5).
- Produces (utilisé par Task 8) :
  - `GET /stac/collections/{collection_id}/items?limit=&offset=&bbox=` → ItemCollection + lien `next` (porte l'`offset` suivant tant qu'une page pleine est renvoyée).
  - `GET /stac/collections/{collection_id}/items/{feature_id}` → STAC Item, 404 si absent.
  - `_parse_bbox(raw) -> tuple[float,...] | None` — réutilise le format `minx,miny,maxx,maxy`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `core/tests/test_stac_routes.py` un fake repo (reprend `test_features_routes_read.py`) et les tests items :

```python
from types import SimpleNamespace

from app.features.repository import FeaturePage

FEAT = {"type": "Feature", "id": 1,
        "geometry": {"type": "Point", "coordinates": [1.0, 44.0]},
        "properties": {"titre": "a"}}


def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox)
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature, calls=calls)


@pytest.fixture()
def env_repo(env):
    app, client, admin = env
    repo = make_fake_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: repo
    return app, client, admin, repo


def test_items_returns_stac_item_collection_with_next(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    body = client.get("/stac/collections/incidents/items?limit=1&offset=0").json()
    assert body["type"] == "FeatureCollection"
    it = body["features"][0]
    assert it["stac_version"] == "1.0.0" and it["collection"] == "incidents"
    assert it["properties"]["datetime"].endswith("Z")
    rels = {l["rel"]: l["href"] for l in body["links"]}
    assert "offset=1" in rels["next"]  # 1 renvoyé sur 3 → next
    assert repo.calls["limit"] == 1 and repo.calls["offset"] == 0


def test_items_bbox_forwarded(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    client.get("/stac/collections/incidents/items?bbox=0,40,2,46")
    assert repo.calls["bbox"] == (0.0, 40.0, 2.0, 46.0)


def test_single_item_and_404(env_repo):
    app, client, admin, repo = env_repo
    _register(app, client, admin)
    assert client.get("/stac/collections/incidents/items/1").json()["id"] == "1"
    assert client.get("/stac/collections/incidents/items/999").status_code == 404
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_stac_routes.py -k "item" -v`
Expected: FAIL (404 sur `/items`, routes inexistantes).

- [ ] **Step 3: Implémenter les routes items**

Ajouter à `core/app/stac/routes.py` :

```python
from fastapi import HTTPException, Query


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")


@router.get("/collections/{collection_id}/items")
def list_items(collection_id: str, request: Request,
               limit: int = Query(DEFAULT_LIMIT, ge=1), offset: int = Query(0, ge=0),
               bbox: str | None = None,
               user=Depends(get_current_user_optional),
               session: Session = Depends(get_session),
               introspect=Depends(get_introspector), repo=Depends(get_features_repo),
               rls=Depends(get_rls_scope)):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    with rls(session, col.tenant_id):
        page = repo.select_features(session, info, limit=limit, offset=offset,
                                    bbox=parsed_bbox, filters=None)
    dtv = _rfc3339(col.updated_at)
    base = _base(request)
    items = [serializers.item(base=base, collection_id=col.id, feature=f, datetime_value=dtv)
             for f in page.features]
    links = [{"rel": "self", "type": "application/geo+json", "href": str(request.url)},
             {"rel": "root", "type": "application/json", "href": f"{base}/stac"}]
    if offset + page.number_returned < page.number_matched:
        links.append({"rel": "next", "type": "application/geo+json",
                      "href": str(request.url.include_query_params(
                          limit=limit, offset=offset + limit))})
    return serializers.item_collection(items=items, links=links)


@router.get("/collections/{collection_id}/items/{feature_id}")
def get_item(collection_id: str, feature_id: str, request: Request,
             user=Depends(get_current_user_optional),
             session: Session = Depends(get_session),
             introspect=Depends(get_introspector), repo=Depends(get_features_repo),
             rls=Depends(get_rls_scope)):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        feature = repo.get_feature(session, info, fid=feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="item not found")
    return serializers.item(base=_base(request), collection_id=col.id,
                            feature=feature, datetime_value=_rfc3339(col.updated_at))
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_stac_routes.py -v`
Expected: PASS (tous les tests du fichier).

- [ ] **Step 5: Commit**

```bash
git add core/app/stac/routes.py core/tests/test_stac_routes.py
git commit -m "feat(core): STAC items + single item endpoints (SP-12a)"
```

---

### Task 7: Route STAC `/search` cross-collections (GET + POST, token `next`)

**Files:**
- Modify: `core/app/stac/routes.py`
- Test: `core/tests/test_stac_search.py`

**Interfaces:**
- Consumes: `_visible_collections`, `serializers.item/item_collection`, `_base`, `_rfc3339`, `_parse_bbox`, `get_features_repo`, `get_rls_scope`, `get_introspector` (Tasks 5-6).
- Produces:
  - `GET/POST /stac/search` avec `bbox`, `datetime`, `collections` (liste), `ids` (liste), `limit`, `token`. Parcours des collections visibles (∩ `collections`) dans l'ordre stable par `id` ; token `next` = base64(`{"c":collectionId,"o":offset}`). Filtre `datetime` à la granularité collection (une collection est dans l'intervalle ssi son `updated_at` l'est).
  - `_encode_token`/`_decode_token`, `_collection_in_datetime(updated_at, datetime_param) -> bool`.

- [ ] **Step 1: Écrire les tests qui échouent**

`core/tests/test_stac_search.py` (deux collections, fake repo par collection) :

```python
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FeaturePage
from app.main import create_app
from app.stac import routes as stac_routes
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFOS = {
    "roads": TableInfo(table_name="roads", pk_column="id", geometry_column="geom",
                       geometry_type="Point", srid=4326,
                       columns=[ColumnInfo(name="n", type="string", required=False)]),
    "rivers": TableInfo(table_name="rivers", pk_column="id", geometry_column="geom",
                        geometry_type="Point", srid=4326,
                        columns=[ColumnInfo(name="n", type="string", required=False)]),
}


def fake_introspector(session, table_name):
    if table_name not in INFOS:
        raise TableNotFound(table_name)
    return INFOS[table_name]


def feat(fid):
    return {"type": "Feature", "id": fid,
            "geometry": {"type": "Point", "coordinates": [1.0, 44.0]}, "properties": {}}


def make_repo():
    # Chaque collection a 2 features (ids 1,2). matched=2 par collection.
    def select_features(session, info, *, limit, offset, bbox=None, filters=None):
        rows = [feat(1), feat(2)][offset:offset + limit]
        return FeaturePage(features=rows, number_matched=2, number_returned=len(rows))

    def get_feature(session, info, *, fid):
        return None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature)


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
    app.dependency_overrides[features_routes.get_features_repo] = lambda: make_repo()
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    for tn in ("roads", "rivers"):
        client.post("/collections", json={"tableName": tn})
    return app, client


def test_search_cross_collection(env):
    app, client = env
    body = client.get("/stac/search?limit=100").json()
    cols = {f["collection"] for f in body["features"]}
    assert cols == {"roads", "rivers"}
    assert len(body["features"]) == 4  # 2 + 2


def test_search_collections_filter(env):
    app, client = env
    body = client.get("/stac/search?collections=rivers").json()
    assert {f["collection"] for f in body["features"]} == {"rivers"}


def test_search_pagination_token(env):
    app, client = env
    page1 = client.get("/stac/search?limit=1").json()
    assert len(page1["features"]) == 1
    nxt = next(l["href"] for l in page1["links"] if l["rel"] == "next")
    page2 = client.get(nxt.replace("http://testserver", "")).json()
    assert len(page2["features"]) >= 1
    # Les deux pages ne renvoient pas exactement le même item du même collection.
    assert (page1["features"][0]["id"], page1["features"][0]["collection"]) != \
           (page2["features"][0]["id"], page2["features"][0]["collection"])


def test_search_post_body(env):
    app, client = env
    body = client.post("/stac/search", json={"collections": ["roads"], "limit": 100}).json()
    assert {f["collection"] for f in body["features"]} == {"roads"}
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_stac_search.py -v`
Expected: FAIL (404 sur `/stac/search`).

- [ ] **Step 3: Implémenter `/search`**

Ajouter à `core/app/stac/routes.py` :

```python
import base64
import json
from datetime import datetime

from pydantic import BaseModel


class SearchBody(BaseModel):
    bbox: list[float] | None = None
    datetime: str | None = None
    collections: list[str] | None = None
    ids: list[str] | None = None
    limit: int = DEFAULT_LIMIT
    token: str | None = None


def _encode_token(collection_id: str, offset: int) -> str:
    raw = json.dumps({"c": collection_id, "o": offset}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_token(token: str | None):
    if not token:
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(token.encode()))
        return str(d["c"]), int(d["o"])
    except Exception:
        return None


def _parse_dt(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _collection_in_datetime(updated_at, datetime_param: str | None) -> bool:
    if not datetime_param:
        return True
    ua = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    if "/" in datetime_param:
        start_s, end_s = datetime_param.split("/", 1)
        if start_s not in ("", "..") and ua < _parse_dt(start_s):
            return False
        if end_s not in ("", "..") and ua > _parse_dt(end_s):
            return False
        return True
    return ua == _parse_dt(datetime_param)


def _run_search(request, session, user, *, bbox, datetime_param, collections, ids, limit, token,
                introspect, repo, rls):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user)
    if collections:
        wanted = set(collections)
        cols = [c for c in cols if c.id in wanted]
    cols = [c for c in cols if _collection_in_datetime(c.updated_at, datetime_param)]

    decoded = _decode_token(token)
    start_c, start_o = decoded if decoded else (None, 0)
    started = start_c is None
    base = _base(request)
    results, next_token = [], None

    for col in cols:
        if not started:
            if col.id != start_c:
                continue
            started = True
            offset = start_o
        else:
            offset = 0
        info = introspect(session, col.table_name)
        remaining = limit - len(results)
        with rls(session, col.tenant_id):
            page = repo.select_features(session, info, limit=remaining, offset=offset,
                                        bbox=bbox, filters=None)
        dtv = _rfc3339(col.updated_at)
        for f in page.features:
            if ids and str(f["id"]) not in ids:
                continue
            results.append(serializers.item(base=base, collection_id=col.id,
                                             feature=f, datetime_value=dtv))
        consumed = offset + page.number_returned
        if len(results) >= limit and consumed < page.number_matched:
            next_token = _encode_token(col.id, consumed)
            break

    links = [{"rel": "self", "type": "application/geo+json", "href": str(request.url)},
             {"rel": "root", "type": "application/json", "href": f"{base}/stac"}]
    if next_token:
        links.append({"rel": "next", "type": "application/geo+json",
                      "href": f"{base}/stac/search?token={next_token}&limit={limit}"})
    return serializers.item_collection(items=results, links=links)


@router.get("/search")
def search_get(request: Request, bbox: str | None = None, datetime: str | None = None,
               collections: str | None = None, ids: str | None = None,
               limit: int = Query(DEFAULT_LIMIT, ge=1), token: str | None = None,
               user=Depends(get_current_user_optional),
               session: Session = Depends(get_session),
               introspect=Depends(get_introspector), repo=Depends(get_features_repo),
               rls=Depends(get_rls_scope)):
    return _run_search(
        request, session, user,
        bbox=_parse_bbox(bbox), datetime_param=datetime,
        collections=collections.split(",") if collections else None,
        ids=ids.split(",") if ids else None, limit=limit, token=token,
        introspect=introspect, repo=repo, rls=rls)


@router.post("/search")
def search_post(request: Request, body: SearchBody,
                user=Depends(get_current_user_optional),
                session: Session = Depends(get_session),
                introspect=Depends(get_introspector), repo=Depends(get_features_repo),
                rls=Depends(get_rls_scope)):
    return _run_search(
        request, session, user,
        bbox=tuple(body.bbox) if body.bbox else None, datetime_param=body.datetime,
        collections=body.collections, ids=body.ids, limit=body.limit, token=body.token,
        introspect=introspect, repo=repo, rls=rls)
```

> Note : `/search` est déclaré **avant** `/collections/{collection_id}` ? Non — les chemins ne collisionnent pas (`/stac/search` vs `/stac/collections/...`), l'ordre de déclaration n'importe pas ici. Le `datetime` en paramètre de query masque le `datetime` importé de `datetime` : c'est pourquoi l'import est `from datetime import datetime` utilisé seulement dans `_parse_dt` (défini avant les handlers). Vérifier qu'aucun handler n'appelle `datetime(...)` directement.

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_stac_search.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Non-régression du fichier routes + lint**

Run: `cd core && uv run pytest tests/test_stac_routes.py tests/test_stac_search.py -v && uv run lint-imports`
Expected: PASS + contrat Kept.

- [ ] **Step 6: Commit**

```bash
git add core/app/stac/routes.py core/tests/test_stac_search.py
git commit -m "feat(core): STAC item-search cross-collections with next token (SP-12a)"
```

---

### Task 8: Test d'intégration PostGIS bout-en-bout + adversarial anonyme

**Files:**
- Test: `core/tests/test_stac_integration.py`

**Interfaces:**
- Consumes: toute la surface `/stac` (Tasks 5-7), le vrai introspecteur/DDL/RLS (pas d'override de repo ni de scope), pattern de seed de `test_features_integration.py`.

- [ ] **Step 1: Écrire le test d'intégration**

`core/tests/test_stac_integration.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Bout en bout STAC sur PostGIS réel : vrai introspecteur, vraie DDL RLS,
vrai select_features sous rls_scope. Couvre §10 : navigation, portée anonyme
publié/public sans fuite, bbox, lien next, datetime granularité collection."""
import pytest
from fastapi.testclient import TestClient
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
        conn.execute(text("DROP TABLE IF EXISTS stac_roads"))
        conn.execute(text("CREATE TABLE stac_roads (id serial PRIMARY KEY, "
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
        conn.execute(text("DROP TABLE IF EXISTS stac_roads"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def _seed(app, client, public):
    client.post("/collections", json={"tableName": "stac_roads", "isPublic": public})
    for lon, lat in [(1.0, 44.0), (2.0, 45.0), (3.0, 46.0)]:
        client.post("/collections/stac_roads/items", json={
            "type": "Feature", "properties": {"n": "x"},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}})


def test_full_stac_navigation(pg_app):
    app, client = pg_app
    _seed(app, client, public=True)

    landing = client.get("/stac").json()
    assert "https://api.stacspec.org/v1.0.0/item-search" in landing["conformsTo"]

    col = client.get("/stac/collections/stac_roads").json()
    assert col["type"] == "Collection" and col["license"] == "other"
    bbox = col["extent"]["spatial"]["bbox"][0]
    assert bbox[0] == pytest.approx(1.0, abs=0.5) and bbox[2] == pytest.approx(3.0, abs=0.5)
    assert col["extent"]["temporal"]["interval"][0][1] is None

    items = client.get("/stac/collections/stac_roads/items?limit=2").json()
    assert items["type"] == "FeatureCollection" and len(items["features"]) == 2
    assert items["features"][0]["properties"]["datetime"].endswith("Z")
    assert any(l["rel"] == "next" for l in items["links"])

    # bbox filter : seul le point (1,44) est dans l'emprise serrée.
    tight = client.get("/stac/collections/stac_roads/items?bbox=0.9,43.9,1.1,44.1").json()
    assert len(tight["features"]) == 1

    search = client.get("/stac/search?collections=stac_roads&bbox=0,40,4,47").json()
    assert {f["collection"] for f in search["features"]} == {"stac_roads"}


def test_anonymous_sees_public_only_no_leak(pg_app):
    app, client = pg_app
    _seed(app, client, public=False)  # non publique
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    # Collection non publique → 404 non-fuyant (indistinguable d'inexistante).
    assert client.get("/stac/collections/stac_roads").status_code == 404
    assert client.get("/stac/collections/stac_roads/items").status_code == 404
    assert client.get("/stac/collections").json()["collections"] == []
    assert client.get("/stac/search").json()["features"] == []
    # Une collection inexistante renvoie le même 404.
    assert client.get("/stac/collections/does-not-exist").status_code == 404
```

- [ ] **Step 2: Lancer le test contre un PostGIS jetable**

Run: `cd core && CORE_TEST_DATABASE_URL=$CORE_TEST_DATABASE_URL uv run pytest tests/test_stac_integration.py -v -m postgis`
Expected: PASS (2 tests). Si `CORE_TEST_DATABASE_URL` absent : skippé — **le lancer réellement contre un conteneur PostGIS+pgvector avant de clore la tâche** (ne pas se fier au skip).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_stac_integration.py
git commit -m "test(core): STAC end-to-end PostGIS + adversarial anonymous (SP-12a)"
```

---

### Task 9: Régénération OpenAPI + types shell (dérive `api-types-drift`)

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:** aucune nouvelle interface ; synchronise les artefacts générés que le job CI `api-types-drift` compare.

- [ ] **Step 1: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: fichier réécrit, contient les chemins `/stac`, `/stac/conformance`, `/stac/collections`, `/stac/collections/{collection_id}`, `/stac/collections/{collection_id}/items`, `/stac/collections/{collection_id}/items/{feature_id}`, `/stac/search`.

- [ ] **Step 2: Vérifier la présence des nouveaux chemins**

Run: `cd core && grep -c '"/stac' openapi.json`
Expected: ≥ 7 (au moins un par endpoint).

- [ ] **Step 3: Régénérer les types TypeScript du shell**

Run: `cd shell && npm run gen:api-types`
Expected: `src/api/generated/core-schema.d.ts` réécrit sans erreur `openapi-typescript`.

- [ ] **Step 4: Vérifier que le build shell reste vert (tsc)**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` + `vite build` OK (le shell n'utilise pas ces types, mais ils doivent compiler).

- [ ] **Step 5: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(api): regenerate OpenAPI + shell types for STAC endpoints (SP-12a)"
```

---

## Validation finale de branche

- [ ] **Suite cœur complète (sans DB)** : `cd core && uv run pytest` → tous verts, nouveaux tests STAC inclus (serializers, extent None-case, routes, search) ; tests `postgis` skippés proprement.
- [ ] **Suite cœur avec PostGIS réel** : `cd core && CORE_TEST_DATABASE_URL=... uv run pytest -m postgis` → `test_stac_extent` + `test_stac_integration` verts.
- [ ] **Frontières** : `cd core && uv run lint-imports` → `layered architecture` Kept (`app.stac` correctement placé).
- [ ] **Pas de dérive OpenAPI** : `cd core && uv run python scripts/export_openapi.py /tmp/openapi-check.json && diff openapi.json /tmp/openapi-check.json` → aucune différence.
- [ ] **Smoke d'acceptation documenté (non bloquant)** : contre une instance vive seedée, lancer `stac-api-validator --root-url http://localhost:8000/stac ...` et une navigation `pystac-client` (`Client.open("http://localhost:8000/stac")`, `.get_collections()`, `.search(bbox=...)`) ; consigner le résultat dans le rapport de tâche (comme les validations empiriques SP-10b/SP-11). Non exécuté par la CI.
- [ ] **Revue finale de branche** (modèle opus) : tracer bout-en-bout la propriété d'anonymat non-fuyant (collection non lisible → 404 identique à inexistante, sur `/collections/{id}`, `/items`, `/search`) et l'absence de fuite cross-tenant sur collections **et** items.

---

## Self-review (couverture spec)

| Section spec | Task(s) |
|---|---|
| §1 périmètre (STAC lecture seule, core→collections→features→item-search) | 1, 5, 6, 7 |
| §2.1 mapping Collection→Collection, feature→Item, réutilise select_features | 3, 6, 7 |
| §2.2 datetime synthétique = collection.updated_at, clé réservée | 3, 6 |
| §2.3 emprise ST_EstimatedExtent + repli ST_Extent, 4326, repli monde | 2, 4, 5 |
| §2.4 license "other" en dur | 2 |
| §3 module app/stac/ (serializers/extent/routes), frontière import-linter | 1, 4, 5 |
| §4 surface d'endpoints + conformsTo | 1, 5, 6, 7 |
| §5.1/5.2 objets STAC Collection/Item | 2, 3 |
| §6 permissions (list_visible_collections, get_readable_collection, 404, rls, adversarial) | 5, 6, 7, 8 |
| §7 pagination items (offset/next) + search (token {collectionId,offset}) | 6, 7 |
| §8 gate stac-pydantic offline + intégration postgis + smoke documenté | 1-3, 8, validation finale |
| §9 dérive OpenAPI régénérée | 9 |
| §10 critères d'acceptation | 8 + validation finale |
