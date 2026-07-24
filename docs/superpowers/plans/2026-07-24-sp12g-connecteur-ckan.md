# SP-12g — Connecteur CKAN / data.gouv.fr — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le cinquième et dernier connecteur de moissonnage (A22) —
`ckan` (API Action CKAN `package_search`, JSON REST paginé) — avec **support
de copie opt-in** (`supports_copy = True`), branché sur le `HarvestConnector`
existant, avec son UI d'administration et ses E2E. Ferme l'arbitrage A22 (les
cinq connecteurs).

**Architecture:** `HarvestedRecord` (dataclass frozen, `base.py`) gagne un
champ optionnel `copy_filename: str | None = None`, consommé par
`service.py::_upsert_copy` à la place du littéral codé en dur
`"harvest.geojson"` — extension du pipeline de copie partagé, zéro
changement de comportement pour les connecteurs existants (défaut `None`).
Nouveau fichier `core/app/harvest/connectors/ckan.py` (`CkanConnector`, style
JSON tolérant proche de `stac.py`/`arcgis.py`), enregistré dans `_REGISTRY`
et le `Literal` de `schemas.py`. Shell : nouvelle option dans
`CreateHarvestSourceDialog`, **et** ajout à `COPY_TYPES` (contrairement à
CSW/OGC API - Records qui restent référencement pur). Aucune migration
Alembic (aucune nouvelle colonne `harvest_records` — `copy_filename` vit
uniquement dans le dataclass Python, pas en base).

**Tech Stack:** Python/FastAPI (`core/`), `httpx` (client HTTP gardé),
React/TypeScript (`shell/`), Playwright (E2E, mode mock).

## Global Constraints

- `supports_copy = True` pour `CkanConnector` (seul connecteur v1 qui n'est
  ni STAC ni ArcGIS à l'accepter) — dans `COPY_TYPES` côté shell, accepté en
  mode `copy` côté API (`connector.supports_copy`, déjà branché dans
  `routes.py::_check_copy_support`).
- Découverte via `package_search` uniquement — pas de `package_show` en N+1.
- Filtrage : aucun nouveau champ dans le dialogue d'ajout de source ; l'admin
  encode les paramètres CKAN (`q`, `fq`, `tags`, `organization`...)
  directement dans l'URL fournie, fusionnés proprement avec la pagination
  (`start`/`rows` ajoutés/écrasés, jamais dupliqués).
- Formats copiables v1, dans cet ordre de préférence : GeoJSON
  (`copy_filename="harvest.geojson"`), GPKG/GEOPACKAGE
  (`copy_filename="harvest.gpkg"`), SHP/SHAPEFILE zippé
  (`copy_filename="harvest.zip"`). CSV exclu de la copie (mapping lat/lon non
  fourni pour la copie moissonnée). Un paquet sans resource géo reconnue reste
  moissonné en référencement pur (`items_url = None` → comportement de repli
  déjà existant).
- Bbox : extra `spatial` (GeoJSON, convention `ckanext-spatial`) si présent et
  valide, sinon bbox monde `[-180, -90, 180, 90]` — même tolérance que
  `StacConnector`.
- Bornes : `_MAX_CKAN_DATASETS = 500` (total émis), `_MAX_CKAN_PAGES = 50`,
  page size `rows=100`, timeout 10 s par requête.
- Toutes les requêtes passent par le client d'egress gardé
  (`build_guarded_client`), construit en interne par le connecteur ; la copie
  (`fetch_copy_geojson` → `http_get`) utilise le `http_get` injecté par le
  moteur.
- Contrat harvest : un connecteur ne lève **jamais** — toute erreur
  réseau/JSON est loggée et donne un résultat vide ou partiel, jamais une
  exception qui fuite.
- Un paquet sans `id` est ignoré (pas d'upsert idempotent possible sans
  identifiant stable).
- Aucune migration Alembic dans SP-12g.

---

## Task 1: `HarvestedRecord` gagne `copy_filename`

**Files:**
- Modify: `core/app/harvest/connectors/base.py`
- Create: `core/tests/test_harvest_base.py`

**Interfaces:**
- Produces : `HarvestedRecord.copy_filename: str | None = None` (nouveau
  champ, dernier de la dataclass), consommé par la Task 2 (`service.py`) et
  la Task 3 (`CkanConnector`). Pour les 6 connecteurs existants (STAC,
  ArcGIS, WMS, WFS, WMTS, CSW, OGC API - Records — 7 en tout), ce champ n'est
  jamais renseigné explicitement → défaut `None`, comportement inchangé.

- [ ] **Step 1: Écrire le fichier de tests (RED)**

Créer `core/tests/test_harvest_base.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.base import HarvestedRecord


def test_copy_filename_defaults_to_none():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url=None,
    )
    assert rec.copy_filename is None


def test_copy_filename_can_be_set():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://x", items_url="https://x/data.gpkg",
        copy_filename="harvest.gpkg",
    )
    assert rec.copy_filename == "harvest.gpkg"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_base.py -v`
Expected: FAIL avec `TypeError: HarvestedRecord.__init__() got an unexpected
keyword argument 'copy_filename'`

- [ ] **Step 3: Ajouter le champ**

Modifier `core/app/harvest/connectors/base.py` (remplacer les lignes 9-18) :

```python
@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None
    raster_tiles_url: str | None = None
    copy_filename: str | None = None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_base.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lancer la suite harvest complète (non-régression)**

Run: `cd core && uv run pytest tests/ -k harvest -v`
Expected: PASS (tous les tests des 7 connecteurs existants, inchangés — le
nouveau champ a un défaut).

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/base.py core/tests/test_harvest_base.py
git commit -m "feat(core): HarvestedRecord.copy_filename (SP-12g)"
```

---

## Task 2: `service.py` — extension du pipeline de copie partagé

**Files:**
- Modify: `core/app/harvest/service.py`
- Modify: `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes : `HarvestedRecord.copy_filename` (Task 1).
- Produces : `_upsert_copy` transmet `rec.copy_filename or "harvest.geojson"`
  à `run_import(..., filename=...)`, consommé par la Task 3 (`CkanConnector`,
  via le moteur de moissonnage réel).

- [ ] **Step 1: Ajouter les tests (RED)**

Ajouter à `core/tests/test_harvest_service.py`, après l'import existant
`from app.harvest.connectors.base import HarvestedRecord` (ligne 10) :

```python
from app.ingestion.importer import ImportResult
```

Ajouter à la fin du fichier :

```python
def test_upsert_copy_passes_copy_filename_to_run_import(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c1", item_id="i1"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="ckan",
        url="https://data.example.com", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    rec = HarvestedRecord(
        external_id="pkg-1", title="Sentiers", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://data.example.com/dataset/pkg-1",
        items_url="https://data.example.com/dataset/pkg-1/resource/x.gpkg",
        copy_filename="harvest.gpkg",
    )
    connector = _fake_connector([rec], copy_bytes=b"gpkg-bytes")
    service._upsert_copy(
        session, source, rec, existing=None, digest="d1", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.gpkg"


def test_upsert_copy_defaults_filename_when_copy_filename_is_none(session, tenant_and_user, monkeypatch):
    # Régression : STAC/ArcGIS ne renseignent jamais copy_filename (défaut
    # None) — le littéral "harvest.geojson" doit rester inchangé pour eux.
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c2", item_id="i2"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    connector = _fake_connector([RECORD_A], copy_bytes=b"geojson-bytes")
    service._upsert_copy(
        session, source, RECORD_A, existing=None, digest="d2", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.geojson"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "copy_filename" -v`
Expected: `test_upsert_copy_passes_copy_filename_to_run_import` FAIL (le code
actuel appelle toujours `run_import` avec `filename="harvest.geojson"` codé
en dur, jamais `"harvest.gpkg"`) ; `test_upsert_copy_defaults_filename_when_copy_filename_is_none`
PASS déjà (comportement actuel = comportement attendu pour ce cas).

- [ ] **Step 3: Modifier `_upsert_copy`**

Dans `core/app/harvest/service.py`, remplacer (ligne 183-187) :

```python
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename="harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
```

par :

```python
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename=rec.copy_filename or "harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_service.py -v`
Expected: PASS (tous les tests service, y compris les 2 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/service.py core/tests/test_harvest_service.py
git commit -m "feat(core): _upsert_copy respecte HarvestedRecord.copy_filename (SP-12g)"
```

---

## Task 3: Connecteur CKAN (`CkanConnector`), registre, schémas et openapi.json

**Files:**
- Create: `core/app/harvest/connectors/ckan.py`
- Create: `core/tests/test_harvest_ckan_connector.py`
- Modify: `core/app/harvest/connectors/__init__.py`
- Modify: `core/app/harvest/schemas.py`
- Modify: `core/tests/test_harvest_routes.py`
- Modify: `core/openapi.json` (régénéré)

**Interfaces:**
- Consumes : `app.harvest.connectors.base.HarvestedRecord` (Task 1) ;
  `app.harvest.egress.build_guarded_client` (import différé, comme les 6
  autres connecteurs).
- Produces : classe `CkanConnector` (`type = "ckan"`, `supports_copy = True`,
  `fetch(url) -> Iterable[HarvestedRecord]`,
  `fetch_copy_geojson(record, *, http_get) -> bytes | None`) ; `get_connector("ckan")`
  fonctionnel ; `HarvestSourceCreate.type` accepte `"ckan"` — consommé par la
  Task 4 (shell) et la Task 5 (E2E).

- [ ] **Step 1: Écrire le fichier de tests (RED)**

Créer `core/tests/test_harvest_ckan_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import json

import httpx

from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.ckan import CkanConnector

PORTAL = "https://demo.data.gouv.fr"
SEARCH = f"{PORTAL}/api/3/action/package_search"


def _search_response(results, *, count=None):
    return {"success": True, "result": {"count": count if count is not None else len(results), "results": results}}


def _pkg(**overrides):
    pkg = {
        "id": "pkg-1", "name": "batiments-ville", "title": "Bâtiments de la ville",
        "notes": "Empreintes de bâtiments", "tags": [{"name": "bati"}, {"name": "urbain"}],
        "resources": [],
    }
    pkg.update(overrides)
    return pkg


def _connector(handler) -> CkanConnector:
    return CkanConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_single_page_extracts_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(SEARCH)
        return httpx.Response(200, json=_search_response([_pkg()]))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "pkg-1"
    assert rec.title == "Bâtiments de la ville"
    assert rec.abstract == "Empreintes de bâtiments"
    assert rec.keywords == ["bati", "urbain"]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec.external_url == f"{PORTAL}/dataset/batiments-ville"
    assert rec.items_url is None
    assert rec.copy_filename is None
    assert rec.raster_tiles_url is None


def test_title_falls_back_to_name_and_external_url_to_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([
            _pkg(title=None, name=None, id="pkg-2"),
        ]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.title == "pkg-2"
    assert rec.external_url == f"{PORTAL}/dataset/pkg-2"


def test_package_without_id_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([_pkg(id=None)]))

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_pagination_merges_query_params_and_advances_start():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        calls.append(qs)
        assert qs["organization"] == "ville-x"
        assert qs["tags"] == "geo"
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg(id="p1", name="p1")], count=2))
        return httpx.Response(200, json=_search_response([_pkg(id="p2", name="p2")], count=2))

    records = list(_connector(handler).fetch(f"{PORTAL}?organization=ville-x&tags=geo"))
    assert [r.external_id for r in records] == ["p1", "p2"]
    assert [c["start"] for c in calls] == ["0", "1"]
    assert all(c["rows"] == "100" for c in calls)


def test_admin_url_start_and_rows_are_overridden_not_duplicated():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = request.url.params.multi_items()
        keys = [k for k, _ in qs]
        assert keys.count("start") == 1
        assert keys.count("rows") == 1
        return httpx.Response(200, json=_search_response([_pkg()]))

    list(_connector(handler).fetch(f"{PORTAL}?start=999&rows=5"))


def test_pagination_stops_when_count_exhausted():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_search_response([_pkg(id="only", name="only")], count=1))

    records = list(_connector(handler).fetch(PORTAL))
    assert calls["n"] == 1
    assert [r.external_id for r in records] == ["only"]


def test_pagination_stops_on_empty_page():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg()], count=999))
        return httpx.Response(200, json=_search_response([]))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == 1


def test_datasets_capped_at_max():
    from app.harvest.connectors.ckan import _MAX_CKAN_DATASETS

    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        start = int(qs["start"])
        page = [_pkg(id=f"p{start + i}", name=f"p{start + i}") for i in range(100)]
        return httpx.Response(200, json=_search_response(page, count=10_000))

    records = list(_connector(handler).fetch(PORTAL))
    assert len(records) == _MAX_CKAN_DATASETS


def test_pages_capped_at_max_when_page_barely_advances():
    from app.harvest.connectors.ckan import _MAX_CKAN_PAGES

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        qs = dict(request.url.params)
        start = int(qs["start"])
        return httpx.Response(200, json=_search_response([_pkg(id=f"p{start}", name=f"p{start}")], count=10_000))

    records = list(_connector(handler).fetch(PORTAL))
    assert calls["n"] <= _MAX_CKAN_PAGES
    assert len(records) == _MAX_CKAN_PAGES


def test_bbox_from_valid_spatial_extra():
    pkg = _pkg(extras=[{"key": "spatial", "value": json.dumps({
        "type": "Polygon",
        "coordinates": [[[1.0, 45.0], [2.0, 45.0], [2.0, 46.0], [1.0, 46.0], [1.0, 45.0]]],
    })}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [1.0, 45.0, 2.0, 46.0]


def test_bbox_defaults_to_world_when_extras_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([_pkg()]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_bbox_defaults_to_world_when_spatial_extra_is_malformed_json():
    pkg = _pkg(extras=[{"key": "spatial", "value": "not json"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_copy_resource_selection_prefers_geojson_over_gpkg_over_shp():
    pkg = _pkg(resources=[
        {"format": "SHP", "url": f"{PORTAL}/r/a.zip"},
        {"format": "GPKG", "url": f"{PORTAL}/r/a.gpkg"},
        {"format": "GeoJSON", "url": f"{PORTAL}/r/a.geojson"},
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.geojson"
    assert rec.copy_filename == "harvest.geojson"


def test_copy_resource_selection_gpkg_only():
    pkg = _pkg(resources=[{"format": "GEOPACKAGE", "url": f"{PORTAL}/r/a.gpkg"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.gpkg"
    assert rec.copy_filename == "harvest.gpkg"


def test_copy_resource_selection_shapefile_zipped_only():
    pkg = _pkg(resources=[{"format": "Shapefile", "url": f"{PORTAL}/r/a.zip"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url == f"{PORTAL}/r/a.zip"
    assert rec.copy_filename == "harvest.zip"


def test_copy_resource_selection_csv_only_is_reference_only():
    pkg = _pkg(resources=[{"format": "CSV", "url": f"{PORTAL}/r/a.csv"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url is None
    assert rec.copy_filename is None


def test_copy_resource_without_url_is_ignored():
    pkg = _pkg(resources=[{"format": "GeoJSON"}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.items_url is None
    assert rec.copy_filename is None


def test_tolerant_to_malformed_package_fields():
    pkg = _pkg(tags="not-a-list", extras="not-a-list", resources="not-a-list")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response([pkg]))

    rec = list(_connector(handler).fetch(PORTAL))[0]
    assert rec.keywords == []
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec.items_url is None


def test_non_dict_package_is_ignored():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_response(["not-a-dict", _pkg()]))

    records = list(_connector(handler).fetch(PORTAL))
    assert [r.external_id for r in records] == ["pkg-1"]


def test_missing_result_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_invalid_json_page_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_http_error_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert list(_connector(handler).fetch(PORTAL)) == []


def test_next_page_failure_keeps_partial_results():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = dict(request.url.params)
        if qs["start"] == "0":
            return httpx.Response(200, json=_search_response([_pkg()], count=999))
        return httpx.Response(500)

    records = list(_connector(handler).fetch(PORTAL))
    assert [r.external_id for r in records] == ["pkg-1"]


def test_fetch_copy_geojson_calls_http_get_on_items_url():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{PORTAL}/r/a.gpkg", copy_filename="harvest.gpkg",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, content=b"gpkg-bytes")

    content = CkanConnector().fetch_copy_geojson(rec, http_get=http_get)
    assert content == b"gpkg-bytes"
    assert calls == [f"{PORTAL}/r/a.gpkg"]


def test_fetch_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=None,
    )
    assert CkanConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_get_connector_returns_ckan():
    from app.harvest.connectors import get_connector

    c = get_connector("ckan")
    assert c.type == "ckan"
    assert c.supports_copy is True
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_ckan_connector.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.connectors.ckan'`

- [ ] **Step 3: Implémenter `CkanConnector`**

Créer `core/app/harvest/connectors/ckan.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur CKAN / data.gouv.fr (SP-12g) — cinquième et dernier connecteur
d'A22. package_search JSON REST paginé, pas de package_show en N+1 (§3.1 de
la spec). Seul connecteur non-STAC/ArcGIS avec supports_copy=True : une
resource géo reconnue (GeoJSON/GPKG/SHP zippé) est copiable, CSV exclu (pas
de mapping lat/lon pour la copie moissonnée). HTTP uniquement, zéro I/O DB,
parsing tolérant et borné (même philosophie que StacConnector)."""
import json
import logging
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_CKAN_DATASETS = 500
_MAX_CKAN_PAGES = 50
_PAGE_SIZE = 100
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]

# Ordre de préférence des formats copiables (rang croissant = priorité
# décroissante) : GeoJSON > GPKG/GEOPACKAGE > SHP/SHAPEFILE (zippé). CSV
# volontairement absent (hors périmètre v1, §4 décision de cadrage 4).
_FORMAT_RANK = {"GEOJSON": 0, "GPKG": 1, "GEOPACKAGE": 1, "SHP": 2, "SHAPEFILE": 2}
_FORMAT_FILENAME = {
    "GEOJSON": "harvest.geojson", "GPKG": "harvest.gpkg", "GEOPACKAGE": "harvest.gpkg",
    "SHP": "harvest.zip", "SHAPEFILE": "harvest.zip",
}


class CkanConnector:
    type = "ckan"
    supports_copy = True

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url)
        finally:
            if owns_client:
                client.close()

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        if record.items_url is None:
            return None
        return http_get(record.items_url).content

    def _fetch(self, client, admin_url: str) -> list[HarvestedRecord]:
        split = urlsplit(admin_url)
        endpoint = f"{split.scheme}://{split.netloc}/api/3/action/package_search"
        base_params = [(k, v) for k, v in parse_qsl(split.query) if k not in ("start", "rows")]

        records: list[HarvestedRecord] = []
        start = 0
        pages = 0
        while True:
            pages += 1
            if pages > _MAX_CKAN_PAGES:
                logger.warning(
                    "ckan harvest: plafond de %d pages pour %s, tronqué", _MAX_CKAN_PAGES, admin_url,
                )
                break
            params = [*base_params, ("start", str(start)), ("rows", str(_PAGE_SIZE))]
            page_url = f"{endpoint}?{urlencode(params)}"
            doc = _get_json(client, page_url)
            result = doc.get("result") if isinstance(doc, dict) else None
            if not isinstance(result, dict):
                break
            packages = result.get("results")
            if not isinstance(packages, list) or not packages:
                break
            for pkg in packages:
                if len(records) >= _MAX_CKAN_DATASETS:
                    break
                rec = _package_to_record(pkg, split.scheme, split.netloc)
                if rec is not None:
                    records.append(rec)
            if len(records) >= _MAX_CKAN_DATASETS:
                break
            start += len(packages)
            count = result.get("count")
            if isinstance(count, int) and start >= count:
                break
        return records[:_MAX_CKAN_DATASETS]


def _get_json(client, url: str):
    try:
        response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ckan harvest: échec de récupération de %s : %s", url, exc)
        return None


def _package_to_record(pkg: object, scheme: str, netloc: str) -> HarvestedRecord | None:
    if not isinstance(pkg, dict):
        logger.warning("ckan harvest: paquet non-objet ignoré")
        return None
    try:
        external_id = pkg.get("id")
        if not external_id:
            return None
        name = pkg.get("name")
        title = pkg.get("title") or name or str(external_id)
        abstract = pkg.get("notes") or ""
        tags_raw = pkg.get("tags")
        keywords = [
            t["name"] for t in tags_raw
            if isinstance(t, dict) and isinstance(t.get("name"), str)
        ] if isinstance(tags_raw, list) else []
        bbox = _extract_bbox(pkg.get("extras"))
        external_url = f"{scheme}://{netloc}/dataset/{name or external_id}"
        items_url, copy_filename = _pick_copy_resource(pkg.get("resources"))
        return HarvestedRecord(
            external_id=str(external_id), title=title, abstract=abstract, keywords=keywords,
            bbox=bbox, external_url=external_url, items_url=items_url, copy_filename=copy_filename,
        )
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        logger.warning("ckan harvest: paquet malformé ignoré : %s", exc)
        return None


def _pick_copy_resource(resources: object) -> tuple[str | None, str | None]:
    if not isinstance(resources, list):
        return None, None
    best: tuple[int, str, str] | None = None
    for res in resources:
        if not isinstance(res, dict):
            continue
        fmt = res.get("format")
        if not isinstance(fmt, str):
            continue
        rank = _FORMAT_RANK.get(fmt.upper().strip())
        if rank is None:
            continue
        url = res.get("url")
        if not url:
            continue
        if best is None or rank < best[0]:
            best = (rank, url, _FORMAT_FILENAME[fmt.upper().strip()])
    if best is None:
        return None, None
    return best[1], best[2]


def _extract_bbox(extras: object) -> list[float]:
    if not isinstance(extras, list):
        return list(_WORLD_BBOX)
    for extra in extras:
        if not isinstance(extra, dict) or extra.get("key") != "spatial":
            continue
        value = extra.get("value")
        if not isinstance(value, str):
            return list(_WORLD_BBOX)
        try:
            geom = json.loads(value)
        except ValueError:
            return list(_WORLD_BBOX)
        return _geojson_envelope(geom) or list(_WORLD_BBOX)
    return list(_WORLD_BBOX)


def _geojson_envelope(geom: object) -> list[float] | None:
    if not isinstance(geom, dict):
        return None
    xs: list[float] = []
    ys: list[float] = []

    def walk(node: object) -> None:
        if not isinstance(node, list):
            return
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
        ):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
            return
        for child in node:
            walk(child)

    try:
        walk(geom.get("coordinates"))
    except (TypeError, ValueError):
        return None
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]
```

- [ ] **Step 4: Lancer les tests du connecteur, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_ckan_connector.py -v`
Expected: FAIL uniquement sur `test_get_connector_returns_ckan` (pas encore
enregistré) — tous les autres PASS.

- [ ] **Step 5: Enregistrer le connecteur**

Modifier `core/app/harvest/connectors/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.ckan import CkanConnector
from app.harvest.connectors.csw import CswConnector
from app.harvest.connectors.ogc_records import OgcRecordsConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wfs import WfsConnector
from app.harvest.connectors.wms import WmsConnector
from app.harvest.connectors.wmts import WmtsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
    "wfs": WfsConnector(),
    "wmts": WmtsConnector(),
    "csw": CswConnector(),
    "ogc-records": OgcRecordsConnector(),
    "ckan": CkanConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 6: Étendre le schéma Pydantic**

Modifier `core/app/harvest/schemas.py` ligne 8 :

```python
class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts", "csw", "ogc-records", "ckan"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)
```

- [ ] **Step 7: Ajouter les tests de routes (RED)**

Ajouter à la fin de `core/tests/test_harvest_routes.py` :

```python
def test_create_ckan_source_is_accepted(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": "ckan", "url": "https://demo.data.gouv.fr", "mode": "reference",
    })
    assert resp.status_code == 201
    assert resp.json()["type"] == "ckan"


def test_copy_mode_accepted_for_ckan(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": "ckan", "url": "https://demo.data.gouv.fr", "mode": "copy",
    })
    assert resp.status_code == 201
```

- [ ] **Step 8: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_ckan_connector.py tests/test_harvest_routes.py -v`
Expected: PASS (tous les tests, y compris `test_get_connector_returns_ckan`)

- [ ] **Step 9: Lancer la suite harvest complète**

Run: `cd core && uv run pytest tests/ -k harvest -v`
Expected: PASS (tous les tests harvest, connecteurs existants inclus)

- [ ] **Step 10: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: le fichier `core/openapi.json` est réécrit — `git diff core/openapi.json`
montre `"ckan"` ajouté à l'énumération du type de `HarvestSourceCreate`.

- [ ] **Step 11: Commit**

```bash
git add core/app/harvest/connectors/ckan.py core/tests/test_harvest_ckan_connector.py \
  core/app/harvest/connectors/__init__.py core/app/harvest/schemas.py \
  core/tests/test_harvest_routes.py core/openapi.json
git commit -m "feat(core): connecteur de moissonnage CKAN/data.gouv.fr, copie opt-in (SP-12g)"
```

---

## Task 4: Shell — types, dialogue de création, tests

**Files:**
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Modify: `shell/src/shell/CreateHarvestSourceDialog.test.tsx`

**Interfaces:**
- Consumes : `core/openapi.json` régénéré (Task 3).
- Produces : `HarvestSourceType` inclut `"ckan"` ; `COPY_TYPES` du dialogue
  inclut `"ckan"` — consommé par les E2E de la Task 5.

- [ ] **Step 1: Régénérer les types OpenAPI du shell**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` réécrit — `git diff`
montre `"ckan"` ajouté au type de `HarvestSourceCreate`.

- [ ] **Step 2: Étendre `HarvestSourceType`**

Modifier `shell/src/api/types.ts` ligne 264 :

```typescript
export type HarvestSourceType = "stac" | "arcgis" | "wms" | "wfs" | "wmts" | "csw" | "ogc-records" | "ckan";
```

- [ ] **Step 3: Écrire les tests du dialogue (RED)**

Ajouter à la fin de `shell/src/shell/CreateHarvestSourceDialog.test.tsx` :

```tsx
test("envoie le type CKAN en mode copie", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "ckan",
          url: "https://demo.data.gouv.fr",
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );

  render(<Harness onClose={() => {}} />);
  await userEvent.type(screen.getByLabelText("URL"), "https://demo.data.gouv.fr");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "ckan");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(body).toEqual({
      type: "ckan",
      url: "https://demo.data.gouv.fr",
      mode: "copy",
      enabled: true,
    }),
  );
});

test("garde le mode copie disponible pour CKAN", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })));
  render(<Harness onClose={() => {}} />);
  await userEvent.selectOptions(screen.getByLabelText("Type"), "ckan");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});
```

- [ ] **Step 4: Lancer les tests, vérifier l'échec**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: FAIL — l'option `<option value="ckan">` n'existe pas encore dans le
`<select>`, `selectOptions` échoue ; `COPY_TYPES` ne contient pas `"ckan"`.

- [ ] **Step 5: Ajouter l'option au dialogue et l'inclure dans `COPY_TYPES`**

Modifier `shell/src/shell/CreateHarvestSourceDialog.tsx` ligne 16 :

```tsx
  const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs", "ckan"];
```

Modifier lignes 53-59 (ajouter l'option après `ogc-records`) :

```tsx
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
            <option value="wmts">WMTS</option>
            <option value="csw">CSW</option>
            <option value="ogc-records">OGC API - Records</option>
            <option value="ckan">CKAN</option>
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: PASS (7 tests)

- [ ] **Step 7: Lancer la suite Vitest complète et la vérification de types**

Run: `cd shell && npm test && npm run build`
Expected: PASS ; `tsc --noEmit` sans erreur.

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts \
  shell/src/shell/CreateHarvestSourceDialog.tsx shell/src/shell/CreateHarvestSourceDialog.test.tsx
git commit -m "feat(shell): option CKAN (mode copie disponible) dans le dialogue de moissonnage (SP-12g)"
```

---

## Task 5: E2E Playwright et documentation

**Files:**
- Create: `shell/e2e/harvest-ckan.spec.ts`
- Modify: `CLAUDE.md`
- Modify: `docs/vision/2026-07-04-feuille-de-route-geostudio.md`

**Interfaces:**
- Consumes : `CreateHarvestSourceDialog` avec l'option `ckan` (Task 4) ;
  `mockCore` (`shell/e2e/mocks.ts`, inchangé).

- [ ] **Step 1: Écrire le spec E2E (référencement + copie)**

Créer `shell/e2e/harvest-ckan.spec.ts` :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const PORTAL = "https://demo.data.gouv.fr";

test("un admin déclare une source CKAN en référencement, la moissonne, et l'item apparaît au catalogue, cherchable", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "ckan", url: PORTAL, mode: "reference", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "ckan", url: PORTAL, mode: "reference", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("pkg-tableur", {
      pk: "ext-ckan-1", resourceType: "external", title: "Recensement des commerces (CKAN distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "ckan", url: PORTAL, mode: "reference", enabled: true,
  });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Recensement des commerces (CKAN distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  const request = page.waitForRequest((req) => req.url().includes("/items?") && req.url().includes("q=commerces"));
  await page.getByRole("textbox", { name: "Rechercher" }).fill("commerces");
  await request;
  await expect(page.getByText("Recensement des commerces (CKAN distant)")).toBeVisible();
});

test("un admin déclare une source CKAN en copie, la moissonne, et la collection importée est cherchable avec sa couche", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "ckan", url: PORTAL, mode: "copy", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "ckan", url: PORTAL, mode: "copy", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("pkg-sentiers", {
      pk: "col-item-1", resourceType: "map", title: "Sentiers de randonnée (CKAN, copie)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: "cfg-col-1", isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/items/col-item-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "col-item-1", resourceType: "map", title: "Sentiers de randonnée (CKAN, copie)",
        abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
        configId: "cfg-col-1", isPublished: false,
      },
    });
  });

  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/col-item-1") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-col-1", itemId: "col-item-1", kind: "map",
        config: {
          kind: "map", theme: {}, dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [2.3, 48.8], zoom: 10 },
            layers: [{
              id: "l1", title: "Sentiers de randonnée (CKAN, copie)", visible: true, kind: "feature",
              url: "https://core.test/collections/ingest_ckan/items",
            }],
          },
        },
      },
    });
  });

  // 1) Déclarer et moissonner la source CKAN en mode copie
  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
  await dialog.getByLabel("Mode").selectOption("copy");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "ckan", url: PORTAL, mode: "copy", enabled: true,
  });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  // 2) La collection importée est cherchable au catalogue
  await page.goto("/");
  await expect(page.getByText("Sentiers de randonnée (CKAN, copie)")).toBeVisible();

  const request = page.waitForRequest((req) => req.url().includes("/items?") && req.url().includes("q=randonn"));
  await page.getByRole("textbox", { name: "Rechercher" }).fill("randonn");
  await request;
  await page.getByRole("button", { name: "Ouvrir" }).click();

  // 3) La carte s'ouvre avec la couche de la collection importée (features accessibles)
  await expect(page).toHaveURL(/\/maps\/col-item-1$/);
  await expect(page.getByRole("button", { name: "Retirer Sentiers de randonnée (CKAN, copie)" })).toBeVisible();
});
```

- [ ] **Step 2: Lancer le spec E2E**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test harvest-ckan`
Expected: PASS (2 tests)

- [ ] **Step 3: Lancer la suite E2E complète (non-régression)**

Run: `cd shell && npm run e2e`
Expected: PASS (toutes les specs existantes + les 2 nouvelles)

- [ ] **Step 4: Mettre à jour `CLAUDE.md`**

Dans `CLAUDE.md`, remplacer le bloc SP-12 de la section « Fait » (dernière
ligne du bloc) :

```markdown
- **SP-12** (a→g) — fédération STAC/DCAT : API STAC native (lecture seule),
  export DCAT-AP (JSON-LD), moteur de moissonnage + connecteur STAC externe,
  connecteur ArcGIS FS + garde d'egress SSRF, connecteurs GetCapabilities
  WMS/WFS/WMTS + affichage raster (LayerPicker → `GET /harvest/layers`),
  connecteurs métadonnées CSW 2.0.2 + OGC API - Records (référencement pur,
  parser XML tolérant partagé avec WMS/WFS/WMTS), connecteur CKAN/data.gouv.fr
  (copie opt-in, `package_search` paginé). **A22 complet (les cinq
  connecteurs)**.
```

Et retirer le bloc SP-12(g) de la section « À venir » (il devient vide côté
SP-12, plus rien à lister pour ce chantier).

- [ ] **Step 5: Mettre à jour la feuille de route**

Dans `docs/vision/2026-07-04-feuille-de-route-geostudio.md`, remplacer le
paragraphe « Connecteurs » de la section `### SP-12` (autour de la ligne 591) :

```markdown
- **Connecteurs** (A22 — les cinq retenus, amendé 2026-07-09 ; **complet**
  2026-07-24), *chacun livrable séparément* : ① catalogues STAC externes ;
  ArcGIS Feature Services (référencement + copie, inséré en 2ᵉ position) ;
  ② WMS/WFS/WMTS GetCapabilities (référencer un GeoServer existant en
  secondes) ; ③ CSW/ISO 19139 (GeoNetwork/geOrchestra — parser tolérant,
  champs minimaux) **et son protocole successeur OGC API - Records**
  (extension documentée SP-12f, 2026-07-24) ; ④ **CKAN/data.gouv.fr**
  (`package_search` paginé, **copie opt-in** — seul connecteur non-STAC/ArcGIS
  à supporter la copie, SP-12g, 2026-07-24).
```

Dans la section `### A22 — Connecteurs de moissonnage v1 (SP-12)` (autour de
la ligne 1037), ajouter après l'extension du 2026-07-24 (SP-12f) :

```markdown
> **Extension 2026-07-24 (SP-12g)** : le connecteur ④ (CKAN/data.gouv.fr)
> livre `supports_copy = True` — décision de cadrage qui casse l'hypothèse
> implicite du pipeline de copie partagé (`service.py::_upsert_copy` fixé sur
> `"harvest.geojson"`) : `HarvestedRecord` gagne un champ optionnel
> `copy_filename` (défaut `None`, zéro impact sur STAC/ArcGIS). **A22 complet
> après SP-12g** — les cinq connecteurs retenus sont tous livrés ; tout
> connecteur additionnel futur serait un nouvel arbitrage, pas une suite
> implicite (cf.
> `docs/superpowers/specs/2026-07-24-sp12g-connecteur-ckan-design.md` §9).
```

Dans le tableau récapitulatif des arbitrages (autour de la ligne 1246),
remplacer la ligne A22 :

```markdown
| A22 | Connecteurs moissonnage | **Les cinq, complet** (amendé 2026-07-09) — ordre : STAC → **ArcGIS FS** → GetCapabilities → CSW/ISO **+ OGC API - Records** (SP-12f) → **CKAN** (copie opt-in, SP-12g, 2026-07-24) | SP-12 (réf. comme source de dataset dès SP-14) |
```

Dans le tableau des risques (autour de la ligne 1326), remplacer :

```markdown
| Étalement des connecteurs de moissonnage (5 retenus, tous livrés) | SP-12 clos côté connecteurs | Un connecteur = un incrément livrable ; ordre A22 figé ; tous livrés au 2026-07-24 |
```

Dans le jalon M9 (autour de la ligne 1345), remplacer « 4 connecteurs de
moissonnage » par « 5 connecteurs de moissonnage » :

```markdown
| **M9 catalogue ouvert** (SP-12) | STAC conforme, export DCAT-AP, 5 connecteurs de moissonnage | QGIS navigue le catalogue ; data.gouv.fr moissonne ; un GeoServer externe référencé en < 1 min |
```

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/harvest-ckan.spec.ts CLAUDE.md docs/vision/2026-07-04-feuille-de-route-geostudio.md
git commit -m "$(cat <<'EOF'
test(e2e): admin CKAN → moissonnage (référence + copie) → item cherchable (SP-12g)

docs(vision): SP-12g livré, A22 complet (les cinq connecteurs)
EOF
)"
```

---

## Vérification finale

- [ ] **Step 1: Suite complète cœur**

Run: `cd core && uv run pytest`
Expected: PASS (tests précédents + nouveaux : 2 base + 2 service + ~25 CKAN
+ 1 registre + 2 routes — le compte exact peut varier légèrement)

- [ ] **Step 2: Suite complète shell (unitaires + build)**

Run: `cd shell && npm run build && npm test`
Expected: PASS

- [ ] **Step 3: Suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS (toutes les specs existantes + `harvest-ckan.spec.ts`)

- [ ] **Step 4: Relire `CLAUDE.md` et la feuille de route**

Vérifier que la section « À venir » de `CLAUDE.md` ne mentionne plus SP-12(g)
et que A22 est marqué complet dans les deux documents — A22 est le dernier
arbitrage connecteurs, aucune suite implicite n'est promise.
