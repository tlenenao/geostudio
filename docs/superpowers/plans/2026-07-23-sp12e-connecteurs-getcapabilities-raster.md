# SP-12e — Connecteurs GetCapabilities (WMS/WFS/WMTS) + affichage raster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter trois connecteurs de moissonnage OGC XML (WMS, WFS, WMTS) au moteur SP-12c/d, persister le gabarit de tuiles raster sur `harvest_records`, exposer `GET /harvest/layers`, et brancher l'affichage raster dans l'éditeur de carte via le `LayerPicker` existant — critère : « une couche WMS moissonnée s'affiche dans une carte sans copie ».

**Architecture:** Trois connecteurs enregistrés séparément (`type` = `wms`/`wfs`/`wmts`), conformes au `HarvestConnector` (protocole `fetch` → `HarvestedRecord`, + `fetch_copy_geojson`) et à la garde d'egress SSRF (SP-12d). Un module partagé `ows.py` fait le parsing XML **défensif** (`defusedxml`, tolérant et borné, namespace-agnostique par `local-name`). Le champ `HarvestedRecord.raster_tiles_url` porte le gabarit de tuiles ; WMS/WMTS le posent (`supports_copy=False`), WFS pose `items_url` (`supports_copy=True`, copie GeoJSON paginée). La migration 0017 ajoute `external_url`/`tiles_url`/`layer_kind` à `harvest_records` ; `GET /harvest/layers` joint aux `items` et filtre par tenant + `can()`. Côté shell, le fil raster **réutilise** le rendu `kind:"raster"` déjà présent dans `MapView` — aucune nouvelle primitive cartographique.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy / httpx / defusedxml (**nouvelle dép**) / pyproj (existant) / procrastinate ; React / TypeScript / react-query / maplibre-gl / Playwright.

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-23-sp12e-connecteurs-getcapabilities-raster-design.md`.
- **Le moteur `harvest_source` NE LÈVE JAMAIS** (invariant SP-12c/d inchangé) — toute erreur (fetch, parse, import, egress bloqué) → `source.last_status="error"`, `last_error` tronqué à 500 chars, jamais de job zombie. Le contrat des connecteurs est de **ne jamais lever hors du connecteur** : GetCapabilities malformé / cyclique / géant / hostile → `logger.warning`, retour partiel, jamais d'exception qui fuite. La garde d'egress (`EgressBlockedError`) lève **dans** le client/getter, capturée par les `try` déjà en place du moteur.
- **XML défensif** : tout parsing passe par `defusedxml` (neutralise XXE + expansion d'entités / billion-laughs). Bornes partagées `ows._MAX_LAYERS` / `_MAX_DOCUMENTS` / `_MAX_DEPTH` / `_DEFAULT_TIMEOUT_SECONDS` (10 s comme les autres connecteurs) contre un capabilities géant/cyclique.
- **Navigation namespace-agnostique** : lookup par `local-name` (WMS 1.1.1 sans namespace vs 1.3.0/WFS/WMTS avec namespaces `ows`/`wms`/`wfs`/`wmts`/`xlink`), jamais de QName figé.
- **Un connecteur pose SOIT `items_url` (copiable) SOIT `raster_tiles_url` (raster), jamais les deux** en SP-12e.
- **Dégradation gracieuse documentée** : WMS sans EPSG:3857 (ni alias 900913) → `raster_tiles_url=None` (couche cataloguée mais non ajoutable) ; WMTS sans matrice Web Mercator ou à identifiants de TileMatrix non entiers → `raster_tiles_url=None`.
- **Tuiles raster récupérées côté navigateur (maplibre), pas de proxy serveur** : la garde d'egress ne s'y applique pas. Assumé pour services **publics** uniquement (cohérent avec le résiduel ArcGIS v0 — pas de token/OAuth distant).
- **`defusedxml` = nouvelle dépendance du cœur** (`core/pyproject.toml`, section `dependencies`), version `defusedxml>=0.7`. `uv sync` requis avant exécution des tests connecteurs.
- **Frontière import-linter** : `app.harvest` est déjà au-dessus de `app.ingestion` et importe déjà `app.items`/`app.audit`/`app.sharing` via `service.py`/`routes.py`. `defusedxml`/`httpx`/`pyproj` sont des libs tierces, hors contrat. Le contrat `layers` reste **inchangé** — `cd core && uv run lint-imports` doit rester clean (1 kept / 0 broken).
- **En-tête SPDX** `# SPDX-License-Identifier: Apache-2.0` en première ligne de tout nouveau fichier `core/app/**` et `core/tests/**` ; `// SPDX-License-Identifier: Apache-2.0` pour tout nouveau `shell/src/**` et `shell/e2e/**`.
- **Commandes de test.** Core : `cd core && uv run pytest` (SQLite, always-run) ; tests `@pytest.mark.postgis` : `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest -m postgis` contre un PostGIS+pgvector réel. Shell : `cd shell && npm test` (Vitest) ; `npm run e2e` (Playwright) ; `npm run build` (tsc + vite). Lint imports : `cd core && uv run lint-imports`.
- **Régénération OpenAPI/types** (Task 5 uniquement) : `cd core && uv run python scripts/export_openapi.py openapi.json` puis `cd shell && npm run gen:api-types`. Le job CI `api-types-drift` doit rester vert.
- **Migrations** : nouvelle révision Alembic `0017`, `down_revision = "0016"`, réversible (`downgrade` supprime les 3 colonnes). Le modèle SQLAlchemy `HarvestRecord` et la migration restent alignés.
- **Ne pas toucher aux specs E2E existantes** ; en ajouter **une** (`harvest-wms.spec.ts`). Toute route ajoutée à `shell/e2e/mocks.ts` a un défaut inerte pour les specs qui ne la surchargent pas.

---

## File Structure

**Cœur — nouveau :**
- `core/app/harvest/connectors/ows.py` — parsing XML défensif + helpers namespace + bornes partagées.
- `core/app/harvest/connectors/wms.py` — `WmsConnector` (`supports_copy=False`).
- `core/app/harvest/connectors/wfs.py` — `WfsConnector` (`supports_copy=True`).
- `core/app/harvest/connectors/wmts.py` — `WmtsConnector` (`supports_copy=False`).
- `core/alembic/versions/0017_harvest_layer_columns.py` — 3 colonnes sur `harvest_records`.
- `core/tests/test_harvest_ows.py`, `test_harvest_wms_connector.py`, `test_harvest_wfs_connector.py`, `test_harvest_wmts_connector.py`, `test_harvest_layers_endpoint.py`.

**Cœur — modifié :**
- `core/app/harvest/connectors/base.py` — `HarvestedRecord` gagne `raster_tiles_url`.
- `core/app/harvest/connectors/__init__.py` — `_REGISTRY += wms/wfs/wmts`.
- `core/app/harvest/models.py` — `HarvestRecord` gagne `external_url`/`tiles_url`/`layer_kind`.
- `core/app/harvest/repository.py` — `create_record` porte les 3 colonnes ; `list_layer_records` (nouveau).
- `core/app/harvest/service.py` — `_upsert_reference`/`_upsert_copy` renseignent les 3 colonnes.
- `core/app/harvest/routes.py` — `GET /harvest/layers`.
- `core/app/harvest/schemas.py` — `type` accepte `wms`/`wfs`/`wmts`.
- `core/pyproject.toml` — dépendance `defusedxml>=0.7`.
- `core/openapi.json` — régénéré (Task 5).
- `core/tests/test_harvest_service.py` — assertions de persistance des colonnes.

**Shell — modifié :**
- `shell/src/api/types.ts` — `HarvestSourceType` += `wms`/`wfs`/`wmts` ; `LayerSource.service` += `"external"`, `.kind` += `"raster"`.
- `shell/src/api/generated/core-schema.d.ts` — régénéré (Task 5).
- `shell/src/shell/CreateHarvestSourceDialog.tsx` — options WMS/WFS/WMTS + gating du mode copie.
- `shell/src/map/LayerPicker.tsx` — `toMapLayer` branche `raster`.
- `shell/src/api/itemClient.ts` — `fetchExternalRasterSources` + 3ᵉ source dans `listLayerSources`.
- `shell/e2e/mocks.ts` — route `**/harvest/layers*` par défaut inerte.
- `shell/e2e/harvest-wms.spec.ts` — nouveau.

---

## Task 1: Champ `raster_tiles_url` + module `ows.py` (parsing XML défensif partagé)

**Files:**
- Modify: `core/app/harvest/connectors/base.py`
- Modify: `core/pyproject.toml` (dépendance `defusedxml>=0.7`)
- Create: `core/app/harvest/connectors/ows.py`
- Test: `core/tests/test_harvest_ows.py`

**Interfaces:**
- Consumes: `defusedxml.ElementTree` (lib tierce).
- Produces:
  - `HarvestedRecord` gagne `raster_tiles_url: str | None = None` (dernier champ, avec défaut, pour ne pas casser les instanciations positionnelles STAC/ArcGIS existantes).
  - `ows.parse_capabilities(content: bytes) -> xml.etree.ElementTree.Element | None` — parse défensif, `None` sur échec (log warning), jamais d'exception.
  - `ows.local(tag: str) -> str` — nom local (`{ns}Layer` → `Layer`, `Layer` → `Layer`).
  - `ows.children(elem, name) -> list[Element]` — enfants **directs** de local-name `name`.
  - `ows.child(elem, name) -> Element | None` — premier enfant direct de local-name `name`.
  - `ows.child_text(elem, name) -> str | None` — texte (strippé) du premier enfant direct `name`, ou `None`.
  - `ows.descendants(elem, name) -> Iterator[Element]` — tous descendants (elem inclus) de local-name `name`.
  - Constantes `ows._DEFAULT_TIMEOUT_SECONDS = 10.0`, `_MAX_LAYERS = 500`, `_MAX_DOCUMENTS = 1`, `_MAX_DEPTH = 10`, `_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]`.

- [ ] **Step 1: Ajouter `defusedxml` aux dépendances du cœur**

Dans `core/pyproject.toml`, section `dependencies` (après `"pyproj>=3.6",`), ajouter :

```toml
    "defusedxml>=0.7",  # SP-12e : parsing XML sûr (XXE + billion-laughs) des GetCapabilities OGC
```

Puis :

```bash
cd core && uv sync
```

Expected: `defusedxml` installé, `uv.lock` mis à jour.

- [ ] **Step 2: Élargir `HarvestedRecord` (champ `raster_tiles_url`)**

Dans `core/app/harvest/connectors/base.py`, remplacer la dataclass :

```python
@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None          # copie vecteur (WFS/STAC/ArcGIS)
    raster_tiles_url: str | None = None   # gabarit tuiles raster (WMS/WMTS)
```

- [ ] **Step 3: Write the failing test**

`core/tests/test_harvest_ows.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors import ows

WMS_130 = b"""<?xml version="1.0"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <Layer>
        <Name>topp:states</Name>
        <Title>USA</Title>
        <KeywordList><Keyword>census</Keyword></KeywordList>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<WMS_Capabilities>&lol3;</WMS_Capabilities>"""

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<WMS_Capabilities><Title>&xxe;</Title></WMS_Capabilities>"""


def test_parse_capabilities_returns_root_element():
    root = ows.parse_capabilities(WMS_130)
    assert root is not None
    assert ows.local(root.tag) == "WMS_Capabilities"


def test_parse_capabilities_none_on_garbage():
    assert ows.parse_capabilities(b"not xml at all <<<") is None
    assert ows.parse_capabilities(b"") is None


def test_parse_capabilities_neutralises_billion_laughs():
    # Ne doit ni exploser en mémoire ni lever : retour None (entités interdites).
    assert ows.parse_capabilities(BILLION_LAUGHS) is None


def test_parse_capabilities_neutralises_xxe():
    assert ows.parse_capabilities(XXE) is None


def test_local_strips_namespace():
    assert ows.local("{http://www.opengis.net/wms}Layer") == "Layer"
    assert ows.local("Layer") == "Layer"


def test_children_and_child_text_are_namespace_agnostic():
    root = ows.parse_capabilities(WMS_130)
    capability = ows.child(root, "Capability")
    root_layer = ows.child(capability, "Layer")
    named = ows.child(root_layer, "Layer")
    assert ows.child_text(named, "Name") == "topp:states"
    assert ows.child_text(named, "Title") == "USA"
    kw_list = ows.child(named, "KeywordList")
    assert [k.text for k in ows.children(kw_list, "Keyword")] == ["census"]


def test_descendants_finds_all_matching_local_name():
    root = ows.parse_capabilities(WMS_130)
    layers = list(ows.descendants(root, "Layer"))
    assert len(layers) == 2  # racine + nommée
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_ows.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.connectors.ows'`

- [ ] **Step 5: Write minimal implementation**

`core/app/harvest/connectors/ows.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Parsing XML sûr et borné des GetCapabilities OGC (SP-12e). defusedxml
neutralise XXE et l'expansion d'entités (billion-laughs). Navigation
namespace-agnostique (WMS 1.1.1 sans namespace vs 1.3.0/WFS/WMTS avec
namespaces) : lookup par local-name plutôt que par QName figé. Tolérant :
un document malformé/hostile retourne None, jamais d'exception qui fuite."""
import logging
from collections.abc import Iterator
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_LAYERS = 500
_MAX_DOCUMENTS = 1  # GetCapabilities = un seul GET par source
_MAX_DEPTH = 10     # profondeur d'arbre <Layer> WMS
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


def parse_capabilities(content: bytes) -> Element | None:
    try:
        return fromstring(content)
    except Exception as exc:  # ParseError, EntitiesForbidden, DTDForbidden…
        logger.warning("ows harvest: GetCapabilities illisible ou hostile : %s", exc)
        return None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def children(elem: Element, name: str) -> list[Element]:
    return [c for c in elem if local(c.tag) == name]


def child(elem: Element, name: str) -> Element | None:
    for c in elem:
        if local(c.tag) == name:
            return c
    return None


def child_text(elem: Element, name: str) -> str | None:
    c = child(elem, name)
    if c is not None and c.text and c.text.strip():
        return c.text.strip()
    return None


def descendants(elem: Element, name: str) -> Iterator[Element]:
    for c in elem.iter():
        if local(c.tag) == name:
            yield c
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_ows.py -v`
Expected: PASS (tous)

- [ ] **Step 7: Non-régression connecteurs existants + lint imports**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py tests/test_harvest_arcgis_connector.py -k "not postgis" -v && uv run lint-imports`
Expected: PASS (le défaut `raster_tiles_url=None` ne casse aucune instanciation) ; `lint-imports` clean

- [ ] **Step 8: Commit**

```bash
git add core/pyproject.toml core/uv.lock core/app/harvest/connectors/base.py core/app/harvest/connectors/ows.py core/tests/test_harvest_ows.py
git commit -m "feat(core): module ows.py (parsing XML sûr) + champ raster_tiles_url (SP-12e)"
```

---

## Task 2: `WmsConnector` (couche nommée → record raster, GetMap EPSG:3857)

**Files:**
- Create: `core/app/harvest/connectors/wms.py`
- Modify: `core/app/harvest/connectors/__init__.py`
- Test: `core/tests/test_harvest_wms_connector.py`

**Interfaces:**
- Consumes: `ows` (Task 1), `HarvestedRecord` (base), `build_guarded_client` (egress, SP-12d).
- Produces:
  - `class WmsConnector` — `type = "wms"`, `supports_copy = False`, `__init__(*, client=None)`, `fetch(url)`, `fetch_copy_geojson(record, *, http_get) -> None`.
  - `_REGISTRY["wms"] = WmsConnector()`.
  - Gabarit GetMap : `{base}?service=WMS&version=1.3.0&request=GetMap&layers={Name}&styles=&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&format=image/png&transparent=true` où `{base}` = URL du capabilities sans query, et `{bbox-epsg-3857}` est le placeholder littéral substitué par maplibre.

- [ ] **Step 1: Write the failing test**

`core/tests/test_harvest_wms_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors import get_connector
from app.harvest.connectors.wms import WmsConnector

CAPS = "https://ows.example.com/geoserver/wms?service=WMS&request=GetCapabilities"
BASE = "https://ows.example.com/geoserver/wms"

WMS_130 = b"""<?xml version="1.0"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <CRS>EPSG:3857</CRS>
      <Layer>
        <Name>topp:states</Name>
        <Title>USA States</Title>
        <Abstract>Population par etat</Abstract>
        <KeywordList><Keyword>census</Keyword><Keyword>usa</Keyword></KeywordList>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-124.7</westBoundLongitude>
          <eastBoundLongitude>-66.9</eastBoundLongitude>
          <southBoundLatitude>24.9</southBoundLatitude>
          <northBoundLatitude>49.4</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
      <Layer>
        <Name>topp:nomerc</Name>
        <Title>Sans WebMercator</Title>
        <CRS>EPSG:4326</CRS>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

WMS_111 = b"""<?xml version="1.0"?>
<WMT_MS_Capabilities version="1.1.1">
  <Capability>
    <Layer>
      <Title>Racine</Title>
      <SRS>EPSG:3857</SRS>
      <Layer>
        <Name>roads</Name>
        <Title>Routes</Title>
        <LatLonBoundingBox minx="2.0" miny="48.0" maxx="3.0" maxy="49.0"/>
      </Layer>
    </Layer>
  </Capability>
</WMT_MS_Capabilities>"""


def _connector(body: bytes) -> WmsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)
    return WmsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_named_layer_1_3_0_becomes_raster_record():
    records = list(_connector(WMS_130).fetch(CAPS))
    by_name = {r.title: r for r in records}
    # La couche-groupe racine (sans <Name>) n'est pas émise.
    assert "Racine" not in by_name
    states = by_name["USA States"]
    assert states.abstract == "Population par etat"
    assert states.keywords == ["census", "usa"]
    assert states.external_url == CAPS
    assert states.items_url is None
    assert states.raster_tiles_url is not None
    assert states.raster_tiles_url.startswith(
        f"{BASE}?service=WMS&version=1.3.0&request=GetMap&layers=topp:states"
    )
    assert "crs=EPSG:3857" in states.raster_tiles_url
    assert "{bbox-epsg-3857}" in states.raster_tiles_url
    assert -125 < states.bbox[0] < -124 and 24 < states.bbox[1] < 25


def test_layer_without_web_mercator_is_reference_only():
    records = list(_connector(WMS_130).fetch(CAPS))
    nomerc = next(r for r in records if r.title == "Sans WebMercator")
    assert nomerc.raster_tiles_url is None  # cataloguée mais non ajoutable


def test_wms_1_1_1_latlonbbox_and_srs():
    records = list(_connector(WMS_111).fetch(CAPS))
    roads = next(r for r in records if r.title == "Routes")
    assert roads.raster_tiles_url is not None  # EPSG:3857 hérité de la racine
    assert roads.bbox == [2.0, 48.0, 3.0, 49.0]


def test_fetch_copy_geojson_is_none():
    records = list(_connector(WMS_130).fetch(CAPS))
    assert records[0].raster_tiles_url is not None
    assert _connector(WMS_130).fetch_copy_geojson(records[0], http_get=lambda u: None) is None


def test_malformed_capabilities_returns_empty():
    assert list(_connector(b"<broken").fetch(CAPS)) == []


def test_get_connector_returns_wms():
    c = get_connector("wms")
    assert c.type == "wms"
    assert c.supports_copy is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_wms_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.connectors.wms'`

- [ ] **Step 3: Write minimal implementation**

`core/app/harvest/connectors/wms.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur WMS (SP-12e) — GetCapabilities → une couche NOMMÉE = un record
raster. HTTP uniquement, zéro I/O DB. Parsing tolérant et borné (ows.py) : un
service malformé/hostile/géant ne fait jamais tomber le moissonnage."""
import logging
from collections.abc import Iterable

import httpx

from app.harvest.connectors import ows
from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_WEB_MERCATOR_CODES = {"EPSG:3857", "EPSG:900913", "3857", "900913"}


class WmsConnector:
    type = "wms"
    supports_copy = False

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(ows._DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url)
        finally:
            if owns_client:
                client.close()

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        return None  # raster, non copiable

    def _fetch(self, client, caps_url: str) -> list[HarvestedRecord]:
        try:
            response = client.get(caps_url, timeout=ows._DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("wms harvest: échec de récupération de %s : %s", caps_url, exc)
            return []
        root = ows.parse_capabilities(response.content)
        if root is None:
            return []
        capability = ows.child(root, "Capability")
        if capability is None:
            return []
        base = caps_url.split("?")[0]
        records: list[HarvestedRecord] = []
        for top in ows.children(capability, "Layer"):
            self._walk(top, inherited_crs=set(), depth=0, base=base, caps_url=caps_url, out=records)
        return records

    def _walk(self, layer, *, inherited_crs, depth, base, caps_url, out) -> None:
        if depth > ows._MAX_DEPTH or len(out) >= ows._MAX_LAYERS:
            return
        crs = inherited_crs | _layer_crs(layer)
        name = ows.child_text(layer, "Name")
        if name is not None:
            out.append(_layer_to_record(layer, name, crs, base, caps_url))
        for sub in ows.children(layer, "Layer"):
            self._walk(sub, inherited_crs=crs, depth=depth + 1, base=base, caps_url=caps_url, out=out)


def _layer_crs(layer) -> set[str]:
    # WMS 1.3.0 : <CRS> ; 1.1.1 : <SRS>. Enfants directs seulement.
    codes = set()
    for tag in ("CRS", "SRS"):
        for el in ows.children(layer, tag):
            if el.text:
                codes.add(el.text.strip())
    return codes


def _layer_to_record(layer, name, crs, base, caps_url) -> HarvestedRecord:
    title = ows.child_text(layer, "Title") or name
    abstract = ows.child_text(layer, "Abstract") or ""
    kw_list = ows.child(layer, "KeywordList")
    keywords = [k.text.strip() for k in ows.children(kw_list, "Keyword")] if kw_list is not None else []
    keywords = [k for k in keywords if k]
    bbox = _layer_bbox(layer)
    tiles = _getmap_template(base, name) if (crs & _WEB_MERCATOR_CODES) else None
    return HarvestedRecord(
        external_id=f"{base}#{name}",
        title=title, abstract=abstract, keywords=keywords, bbox=bbox,
        external_url=caps_url,  # URL du GetCapabilities telle que fournie (§3.1)
        items_url=None, raster_tiles_url=tiles,
    )


def _layer_bbox(layer) -> list[float]:
    ex = ows.child(layer, "EX_GeographicBoundingBox")
    if ex is not None:
        try:
            return [
                float(ows.child_text(ex, "westBoundLongitude")),
                float(ows.child_text(ex, "southBoundLatitude")),
                float(ows.child_text(ex, "eastBoundLongitude")),
                float(ows.child_text(ex, "northBoundLatitude")),
            ]
        except (TypeError, ValueError):
            pass
    ll = ows.child(layer, "LatLonBoundingBox")
    if ll is not None:
        try:
            return [
                float(ll.get("minx")), float(ll.get("miny")),
                float(ll.get("maxx")), float(ll.get("maxy")),
            ]
        except (TypeError, ValueError):
            pass
    return list(ows._WORLD_BBOX)


def _getmap_template(base: str, name: str) -> str:
    return (
        f"{base}?service=WMS&version=1.3.0&request=GetMap&layers={name}"
        f"&styles=&crs=EPSG:3857&bbox={{bbox-epsg-3857}}"
        f"&width=256&height=256&format=image/png&transparent=true"
    )
```

> **Rappel** : `external_url` porte l'URL de GetCapabilities telle que fournie (`caps_url`, avec sa query) ; le gabarit GetMap, lui, utilise `base` (sans query). Les deux sont threadés jusqu'à `_layer_to_record`.

Enregistrer dans `core/app/harvest/connectors/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wms import WmsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_wms_connector.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Non-régression + lint imports**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py tests/test_harvest_routes.py -k "not postgis" -v && uv run lint-imports`
Expected: PASS ; `lint-imports` clean

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/wms.py core/app/harvest/connectors/__init__.py core/tests/test_harvest_wms_connector.py
git commit -m "feat(core): connecteur WMS — couche nommée → record raster GetMap 3857 (SP-12e)"
```

---

## Task 3: `WfsConnector` (FeatureType → record vecteur, copie GeoJSON paginée)

**Files:**
- Create: `core/app/harvest/connectors/wfs.py`
- Modify: `core/app/harvest/connectors/__init__.py`
- Test: `core/tests/test_harvest_wfs_connector.py`

**Interfaces:**
- Consumes: `ows` (Task 1), `HarvestedRecord`, `build_guarded_client`, `http_get` injecté.
- Produces:
  - `class WfsConnector` — `type = "wfs"`, `supports_copy = True`, `fetch(url)`, `fetch_copy_geojson(record, *, http_get) -> bytes | None`.
  - `_REGISTRY["wfs"] = WfsConnector()`.
  - Constantes `_COPY_PAGE_SIZE = 1000`, `_MAX_COPY_FEATURES = 200000`, `_MAX_COPY_PAGES = 1000`.
  - `items_url` = `{base}?service=WFS&version=2.0.0&request=GetFeature&typeNames={Name}&outputFormat=application/json&srsName=EPSG:4326`.

- [ ] **Step 1: Write the failing test**

`core/tests/test_harvest_wfs_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import json

import httpx

from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.wfs import WfsConnector

CAPS = "https://ows.example.com/geoserver/wfs?service=WFS&request=GetCapabilities"
BASE = "https://ows.example.com/geoserver/wfs"

WFS_200 = b"""<?xml version="1.0"?>
<WFS_Capabilities version="2.0.0"
    xmlns="http://www.opengis.net/wfs/2.0"
    xmlns:ows="http://www.opengis.net/ows/1.1">
  <FeatureTypeList>
    <FeatureType>
      <Name>topp:tasmania_roads</Name>
      <Title>Routes Tasmanie</Title>
      <Abstract>Routes</Abstract>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>145.0 -43.6</ows:LowerCorner>
        <ows:UpperCorner>148.5 -40.5</ows:UpperCorner>
      </ows:WGS84BoundingBox>
    </FeatureType>
  </FeatureTypeList>
</WFS_Capabilities>"""


def _connector(body: bytes) -> WfsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)
    return WfsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_feature_type_becomes_vector_record():
    r = list(_connector(WFS_200).fetch(CAPS))[0]
    assert r.title == "Routes Tasmanie"
    assert r.abstract == "Routes"
    assert r.raster_tiles_url is None
    assert r.external_url == CAPS
    assert r.items_url == (
        f"{BASE}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeNames=topp:tasmania_roads&outputFormat=application/json&srsName=EPSG:4326"
    )
    assert r.bbox == [145.0, -43.6, 148.5, -40.5]


def _feature(i):
    return {"type": "Feature", "properties": {"n": i}, "geometry": {"type": "Point", "coordinates": [float(i), 0.0]}}


def test_copy_geojson_paginates_via_startindex_count():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{BASE}?service=WFS&request=GetFeature&typeNames=t&outputFormat=application/json",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        if "startIndex=0" in url:
            return httpx.Response(200, json={"type": "FeatureCollection", "features": [_feature(0), _feature(1)]})
        if "startIndex=2" in url:
            return httpx.Response(200, json={"type": "FeatureCollection", "features": [_feature(2)]})
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    content = WfsConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert [f["properties"]["n"] for f in fc["features"]] == [0, 1, 2]
    assert all("startIndex=" in c and "count=" in c for c in calls)


def test_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=None,
    )
    assert WfsConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_copy_geojson_stops_cleanly_on_malformed_page():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{BASE}?request=GetFeature",
    )

    def http_get(url: str) -> httpx.Response:
        if "startIndex=0" in url:
            return httpx.Response(200, json={"type": "FeatureCollection", "features": [_feature(0)]})
        return httpx.Response(200, json={"features": "not-a-list"})

    fc = json.loads(WfsConnector().fetch_copy_geojson(rec, http_get=http_get))
    assert [f["properties"]["n"] for f in fc["features"]] == [0]


def test_copy_geojson_bounded_by_max_pages():
    from app.harvest.connectors.wfs import _MAX_COPY_PAGES

    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{BASE}?request=GetFeature",
    )
    seen = {"n": 0}

    def http_get(url: str) -> httpx.Response:
        seen["n"] += 1
        # Toujours une page pleine → sans borne, boucle infinie.
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [_feature(0)] * 1000})

    json.loads(WfsConnector().fetch_copy_geojson(rec, http_get=http_get))
    assert seen["n"] <= _MAX_COPY_PAGES


def test_get_connector_returns_wfs():
    c = get_connector("wfs")
    assert c.type == "wfs"
    assert c.supports_copy is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_wfs_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.connectors.wfs'`

- [ ] **Step 3: Write minimal implementation**

`core/app/harvest/connectors/wfs.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur WFS (SP-12e) — GetCapabilities → un FeatureType = un record
vecteur ; copie GeoJSON paginée (startIndex/count, WFS 2.0.0), bornée et
tolérante. HTTP uniquement, zéro I/O DB."""
import json
import logging
from collections.abc import Iterable

import httpx

from app.harvest.connectors import ows
from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_COPY_PAGE_SIZE = 1000
_MAX_COPY_FEATURES = 200000
_MAX_COPY_PAGES = 1000


class WfsConnector:
    type = "wfs"
    supports_copy = True

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(ows._DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url)
        finally:
            if owns_client:
                client.close()

    def _fetch(self, client, caps_url: str) -> list[HarvestedRecord]:
        try:
            response = client.get(caps_url, timeout=ows._DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("wfs harvest: échec de récupération de %s : %s", caps_url, exc)
            return []
        root = ows.parse_capabilities(response.content)
        if root is None:
            return []
        type_list = ows.child(root, "FeatureTypeList")
        if type_list is None:
            return []
        base = caps_url.split("?")[0]
        records: list[HarvestedRecord] = []
        for ft in ows.children(type_list, "FeatureType"):
            if len(records) >= ows._MAX_LAYERS:
                break
            name = ows.child_text(ft, "Name")
            if name is None:
                continue
            records.append(HarvestedRecord(
                external_id=f"{base}#{name}",
                title=ows.child_text(ft, "Title") or name,
                abstract=ows.child_text(ft, "Abstract") or "",
                keywords=_ft_keywords(ft),
                bbox=_ft_bbox(ft),
                external_url=caps_url,
                items_url=_getfeature_template(base, name),
                raster_tiles_url=None,
            ))
        return records

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        if record.items_url is None:
            return None
        features: list = []
        offset = 0
        pages = 0
        while True:
            pages += 1
            if pages >= _MAX_COPY_PAGES:
                logger.warning("wfs harvest: plafond de %d pages pour %s, tronqué", _MAX_COPY_PAGES, record.external_id)
                break
            page_url = f"{record.items_url}&startIndex={offset}&count={_COPY_PAGE_SIZE}"
            try:
                page = http_get(page_url).json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("wfs harvest: page de copie illisible à %s : %s", page_url, exc)
                break
            if not isinstance(page, dict) or not isinstance(page.get("features"), list):
                logger.warning("wfs harvest: page de copie malformée à %s, arrêt", page_url)
                break
            page_features = page["features"]
            if not page_features:
                break
            features.extend(page_features)
            offset += len(page_features)
            if len(features) >= _MAX_COPY_FEATURES:
                logger.warning("wfs harvest: plafond de %d entités pour %s, tronqué", _MAX_COPY_FEATURES, record.external_id)
                features = features[:_MAX_COPY_FEATURES]
                break
            if len(page_features) < _COPY_PAGE_SIZE:
                break
        return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def _ft_keywords(ft) -> list[str]:
    kws = ows.child(ft, "Keywords")
    if kws is None:
        return []
    return [k.text.strip() for k in ows.children(kws, "Keyword") if k.text and k.text.strip()]


def _ft_bbox(ft) -> list[float]:
    wgs = ows.child(ft, "WGS84BoundingBox")
    if wgs is not None:
        lower = ows.child_text(wgs, "LowerCorner")
        upper = ows.child_text(wgs, "UpperCorner")
        try:
            xmin, ymin = (float(v) for v in lower.split())
            xmax, ymax = (float(v) for v in upper.split())
            return [xmin, ymin, xmax, ymax]
        except (AttributeError, TypeError, ValueError):
            pass
    ll = ows.child(ft, "LatLongBoundingBox")
    if ll is not None:
        try:
            return [float(ll.get("minx")), float(ll.get("miny")), float(ll.get("maxx")), float(ll.get("maxy"))]
        except (TypeError, ValueError):
            pass
    return list(ows._WORLD_BBOX)


def _getfeature_template(base: str, name: str) -> str:
    return (
        f"{base}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeNames={name}&outputFormat=application/json&srsName=EPSG:4326"
    )
```

Enregistrer dans `__init__.py` (ajouter l'import et l'entrée) :

```python
from app.harvest.connectors.wfs import WfsConnector
```
```python
    "wfs": WfsConnector(),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_wfs_connector.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/connectors/wfs.py core/app/harvest/connectors/__init__.py core/tests/test_harvest_wfs_connector.py
git commit -m "feat(core): connecteur WFS — FeatureType→record + copie GeoJSON paginée (SP-12e)"
```

---

## Task 4: `WmtsConnector` (Layer → record raster `{z}/{y}/{x}`)

**Files:**
- Create: `core/app/harvest/connectors/wmts.py`
- Modify: `core/app/harvest/connectors/__init__.py`
- Test: `core/tests/test_harvest_wmts_connector.py`

**Interfaces:**
- Consumes: `ows`, `HarvestedRecord`, `build_guarded_client`.
- Produces:
  - `class WmtsConnector` — `type = "wmts"`, `supports_copy = False`, `fetch(url)`, `fetch_copy_geojson(...) -> None`.
  - `_REGISTRY["wmts"] = WmtsConnector()`.
  - `raster_tiles_url` `{z}/{y}/{x}` : ResourceURL RESTful (substitution `{TileMatrix}`→`{z}`, `{TileRow}`→`{y}`, `{TileCol}`→`{x}`, style/défaut) si présent, sinon gabarit KVP GetTile.

- [ ] **Step 1: Write the failing test**

`core/tests/test_harvest_wmts_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors import get_connector
from app.harvest.connectors.wmts import WmtsConnector

CAPS = "https://ows.example.com/wmts?service=WMTS&request=GetCapabilities"
BASE = "https://ows.example.com/wmts"

# Deux TileMatrixSet : un WebMercator à identifiants entiers, un non-mercator.
WMTS = b"""<?xml version="1.0"?>
<Capabilities version="1.0.0"
    xmlns="http://www.opengis.net/wmts/1.0"
    xmlns:ows="http://www.opengis.net/ows/1.1"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <Contents>
    <Layer>
      <ows:Identifier>orthophoto</ows:Identifier>
      <ows:Title>Orthophoto</ows:Title>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>-5.0 41.0</ows:LowerCorner>
        <ows:UpperCorner>10.0 52.0</ows:UpperCorner>
      </ows:WGS84BoundingBox>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <TileMatrixSetLink><TileMatrixSet>PM</TileMatrixSet></TileMatrixSetLink>
      <ResourceURL format="image/png" resourceType="tile"
        template="https://ows.example.com/wmts/orthophoto/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"/>
    </Layer>
    <Layer>
      <ows:Identifier>plan_lambert</ows:Identifier>
      <ows:Title>Plan Lambert</ows:Title>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>-5.0 41.0</ows:LowerCorner>
        <ows:UpperCorner>10.0 52.0</ows:UpperCorner>
      </ows:WGS84BoundingBox>
      <TileMatrixSetLink><TileMatrixSet>LAMB93</TileMatrixSet></TileMatrixSetLink>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>PM</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>
      <TileMatrix><ows:Identifier>0</ows:Identifier></TileMatrix>
      <TileMatrix><ows:Identifier>1</ows:Identifier></TileMatrix>
    </TileMatrixSet>
    <TileMatrixSet>
      <ows:Identifier>LAMB93</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::2154</ows:SupportedCRS>
      <TileMatrix><ows:Identifier>0</ows:Identifier></TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""

# Variante sans ResourceURL (→ gabarit KVP GetTile).
WMTS_KVP = WMTS.replace(
    b'<ResourceURL format="image/png" resourceType="tile"\n'
    b'        template="https://ows.example.com/wmts/orthophoto/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"/>',
    b"",
)


def _connector(body: bytes) -> WmtsConnector:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)
    return WmtsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_resource_url_template_becomes_zyx():
    records = list(_connector(WMTS).fetch(CAPS))
    ortho = next(r for r in records if r.title == "Orthophoto")
    assert ortho.raster_tiles_url == (
        "https://ows.example.com/wmts/orthophoto/default/PM/{z}/{y}/{x}.png"
    )
    assert ortho.bbox == [-5.0, 41.0, 10.0, 52.0]
    assert ortho.external_url == CAPS
    assert ortho.items_url is None


def test_non_mercator_layer_is_reference_only():
    records = list(_connector(WMTS).fetch(CAPS))
    lamb = next(r for r in records if r.title == "Plan Lambert")
    assert lamb.raster_tiles_url is None


def test_kvp_gettile_template_when_no_resource_url():
    records = list(_connector(WMTS_KVP).fetch(CAPS))
    ortho = next(r for r in records if r.title == "Orthophoto")
    assert ortho.raster_tiles_url is not None
    url = ortho.raster_tiles_url
    assert url.startswith(f"{BASE}?service=WMTS")
    assert "request=GetTile" in url and "layer=orthophoto" in url
    assert "tilematrixset=PM" in url
    assert "tilematrix={z}" in url and "tilerow={y}" in url and "tilecol={x}" in url


def test_fetch_copy_geojson_is_none():
    assert _connector(WMTS).fetch_copy_geojson(
        list(_connector(WMTS).fetch(CAPS))[0], http_get=lambda u: None
    ) is None


def test_malformed_returns_empty():
    assert list(_connector(b"<nope").fetch(CAPS)) == []


def test_get_connector_returns_wmts():
    c = get_connector("wmts")
    assert c.type == "wmts"
    assert c.supports_copy is False
```

> **Note d'exécution** : `WMTS_KVP` retire l'élément `ResourceURL` par un `replace` littéral — si la mise en forme du fixture change (indentation/retours ligne), ajuster la chaîne remplacée pour qu'elle corresponde exactement, ou construire deux fixtures distinctes. L'important est qu'une variante ait un `ResourceURL` et l'autre non.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_wmts_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.connectors.wmts'`

- [ ] **Step 3: Write minimal implementation**

`core/app/harvest/connectors/wmts.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur WMTS (SP-12e) — GetCapabilities → un Layer = un record raster,
gabarit {z}/{y}/{x}. N'ajoute à la carte que les couches offrant une matrice
Web Mercator à identifiants de TileMatrix entiers ; sinon référence-only.
HTTP uniquement, zéro I/O DB, parsing tolérant et borné (ows.py)."""
import logging
from collections.abc import Iterable

import httpx

from app.harvest.connectors import ows
from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_WEB_MERCATOR_IDS = {"GoogleMapsCompatible", "WebMercatorQuad"}
_WEB_MERCATOR_CRS_HINTS = ("3857", "900913")


class WmtsConnector:
    type = "wmts"
    supports_copy = False

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(ows._DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url)
        finally:
            if owns_client:
                client.close()

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        return None

    def _fetch(self, client, caps_url: str) -> list[HarvestedRecord]:
        try:
            response = client.get(caps_url, timeout=ows._DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("wmts harvest: échec de récupération de %s : %s", caps_url, exc)
            return []
        root = ows.parse_capabilities(response.content)
        if root is None:
            return []
        contents = ows.child(root, "Contents")
        if contents is None:
            return []
        mercator_sets = _web_mercator_tile_matrix_sets(contents)
        base = caps_url.split("?")[0]
        records: list[HarvestedRecord] = []
        for layer in ows.children(contents, "Layer"):
            if len(records) >= ows._MAX_LAYERS:
                break
            identifier = ows.child_text(layer, "Identifier")
            if identifier is None:
                continue
            records.append(_layer_to_record(layer, identifier, base, caps_url, mercator_sets))
        return records


def _web_mercator_tile_matrix_sets(contents) -> set[str]:
    # Identifiants des TileMatrixSet en Web Mercator ET à TileMatrix entiers.
    ok: set[str] = set()
    for tms in ows.children(contents, "TileMatrixSet"):
        ident = ows.child_text(tms, "Identifier")
        if ident is None:
            continue
        crs = ows.child_text(tms, "SupportedCRS") or ""
        is_mercator = ident in _WEB_MERCATOR_IDS or any(h in crs for h in _WEB_MERCATOR_CRS_HINTS)
        if not is_mercator:
            continue
        matrix_ids = [ows.child_text(m, "Identifier") for m in ows.children(tms, "TileMatrix")]
        if matrix_ids and all(_is_int(mid) for mid in matrix_ids):
            ok.add(ident)
    return ok


def _is_int(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _layer_to_record(layer, identifier, base, caps_url, mercator_sets) -> HarvestedRecord:
    title = ows.child_text(layer, "Title") or identifier
    abstract = ows.child_text(layer, "Abstract") or ""
    bbox = _wgs84_bbox(layer)
    linked = [ows.child_text(link, "TileMatrixSet") for link in ows.children(layer, "TileMatrixSetLink")]
    tms = next((t for t in linked if t in mercator_sets), None)
    tiles = _tiles_url(layer, identifier, base, tms) if tms is not None else None
    return HarvestedRecord(
        external_id=f"{base}#{identifier}",
        title=title, abstract=abstract, keywords=[], bbox=bbox,
        external_url=caps_url, items_url=None, raster_tiles_url=tiles,
    )


def _wgs84_bbox(layer) -> list[float]:
    wgs = ows.child(layer, "WGS84BoundingBox")
    if wgs is not None:
        lower = ows.child_text(wgs, "LowerCorner")
        upper = ows.child_text(wgs, "UpperCorner")
        try:
            xmin, ymin = (float(v) for v in lower.split())
            xmax, ymax = (float(v) for v in upper.split())
            return [xmin, ymin, xmax, ymax]
        except (AttributeError, TypeError, ValueError):
            pass
    return list(ows._WORLD_BBOX)


def _default_style(layer) -> str:
    styles = ows.children(layer, "Style")
    for style in styles:
        if (style.get("isDefault") or "").lower() == "true":
            return ows.child_text(style, "Identifier") or ""
    if styles:
        return ows.child_text(styles[0], "Identifier") or ""
    return ""


def _tiles_url(layer, identifier, base, tms) -> str:
    style = _default_style(layer)
    resource = _resource_url_template(layer)
    if resource is not None:
        return (
            resource
            .replace("{TileMatrix}", "{z}").replace("{TileRow}", "{y}").replace("{TileCol}", "{x}")
            .replace("{Style}", style).replace("{TileMatrixSet}", tms)
        )
    fmt = ows.child_text(layer, "Format") or "image/png"
    return (
        f"{base}?service=WMTS&request=GetTile&version=1.0.0&layer={identifier}"
        f"&style={style}&format={fmt}&tilematrixset={tms}"
        f"&tilematrix={{z}}&tilerow={{y}}&tilecol={{x}}"
    )


def _resource_url_template(layer) -> str | None:
    for res in ows.children(layer, "ResourceURL"):
        if (res.get("resourceType") or "") == "tile" and res.get("template"):
            return res.get("template")
    return None
```

Enregistrer dans `__init__.py` :

```python
from app.harvest.connectors.wmts import WmtsConnector
```
```python
    "wmts": WmtsConnector(),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_wmts_connector.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Suite connecteurs complète + lint imports**

Run: `cd core && uv run pytest tests/test_harvest_ows.py tests/test_harvest_wms_connector.py tests/test_harvest_wfs_connector.py tests/test_harvest_wmts_connector.py tests/test_harvest_stac_connector.py tests/test_harvest_arcgis_connector.py -k "not postgis" -v && uv run lint-imports`
Expected: PASS ; `lint-imports` clean

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/wmts.py core/app/harvest/connectors/__init__.py core/tests/test_harvest_wmts_connector.py
git commit -m "feat(core): connecteur WMTS — Layer→record raster {z}/{y}/{x} (SP-12e)"
```

---

## Task 5: Schéma accepte `wms`/`wfs`/`wmts` + gating copie serveur + régénération OpenAPI/types

**Files:**
- Modify: `core/app/harvest/schemas.py:8`
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `shell/src/api/types.ts:264`
- Test: `core/tests/test_harvest_routes.py`

**Interfaces:**
- Consumes: registre de connecteurs (Tasks 2-4).
- Produces: `POST /harvest/sources {type ∈ {wms,wfs,wmts}}` accepté (201) ; `{type:"wms", mode:"copy"}` → 400 (`_check_copy_support` : `supports_copy=False`) ; `{type:"wfs", mode:"copy"}` → 201 ; `HarvestSourceType` shell = `"stac" | "arcgis" | "wms" | "wfs" | "wmts"`.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_harvest_routes.py` (réutiliser la fixture d'admin déjà utilisée par les tests existants de ce fichier — repérer son nom réel, ne pas en inventer) :

```python
import pytest


@pytest.mark.parametrize("type_", ["wms", "wfs", "wmts"])
def test_create_ows_source_is_accepted(client_admin, type_):
    resp = client_admin.post("/harvest/sources", json={
        "type": type_, "url": "https://ows.example.com/x?request=GetCapabilities",
        "mode": "reference",
    })
    assert resp.status_code == 201
    assert resp.json()["type"] == type_


@pytest.mark.parametrize("type_", ["wms", "wmts"])
def test_copy_mode_rejected_for_raster_connectors(client_admin, type_):
    resp = client_admin.post("/harvest/sources", json={
        "type": type_, "url": "https://ows.example.com/x", "mode": "copy",
    })
    assert resp.status_code == 400


def test_copy_mode_accepted_for_wfs(client_admin):
    resp = client_admin.post("/harvest/sources", json={
        "type": "wfs", "url": "https://ows.example.com/wfs", "mode": "copy",
    })
    assert resp.status_code == 201
```

> **Note** : aligner `client_admin` sur la fixture réelle du fichier (cf. les tests `test_create_arcgis_source_is_accepted` livrés par SP-12d dans ce même fichier).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -k "ows_source or copy_mode" -v`
Expected: FAIL (`wms/wfs/wmts` rejetés 422 par le `Literal["stac","arcgis"]`)

- [ ] **Step 3: Élargir le `Literal` dans `schemas.py`**

```python
class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -k "ows_source or copy_mode" -v`
Expected: PASS (le 400 copie vient de `_check_copy_support`, déjà en place)

- [ ] **Step 5: Régénérer OpenAPI + types shell**

```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Éditer `shell/src/api/types.ts:264` :

```typescript
export type HarvestSourceType = "stac" | "arcgis" | "wms" | "wfs" | "wmts";
```

- [ ] **Step 6: Vérifier l'absence de drift résiduel + build shell**

Run: `cd core && git diff --stat openapi.json && cd ../shell && npm run build`
Expected: `openapi.json` ne diffère que par l'enum `type` de `HarvestSourceCreate` ; `npm run build` clean

- [ ] **Step 7: Commit**

```bash
git add core/app/harvest/schemas.py core/openapi.json core/tests/test_harvest_routes.py shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts
git commit -m "feat(core): POST /harvest/sources accepte wms/wfs/wmts + régénération OpenAPI/types (SP-12e)"
```

---

## Task 6: Migration 0017 + persistance `external_url`/`tiles_url`/`layer_kind`

**Files:**
- Create: `core/alembic/versions/0017_harvest_layer_columns.py`
- Modify: `core/app/harvest/models.py:50` (fin de `HarvestRecord`)
- Modify: `core/app/harvest/repository.py:79-90` (`create_record`)
- Modify: `core/app/harvest/service.py` (`_upsert_reference`, `_upsert_copy`)
- Test: `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes: `HarvestedRecord.raster_tiles_url`/`external_url`/`items_url` (Tasks 1-4).
- Produces:
  - `HarvestRecord.external_url: str | None`, `HarvestRecord.tiles_url: str | None`, `HarvestRecord.layer_kind: str | None`.
  - `repository.create_record(..., external_url=None, tiles_url=None, layer_kind=None)` — 3 kwargs optionnels persistés.
  - `service._layer_kind(rec) -> str | None` : `"raster"` si `rec.raster_tiles_url`, sinon `"feature"` si `rec.items_url`, sinon `None`.
  - `_upsert_reference`/`_upsert_copy` renseignent les 3 colonnes à la création et les rafraîchissent sur changement de contenu.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_harvest_service.py` (réutiliser fixtures + `_fake_connector` du fichier ; ces tests sont **always-run** SQLite — mode reference, aucun `run_import`) :

```python
from app.harvest.connectors.base import HarvestedRecord

RASTER_REC = HarvestedRecord(
    external_id="wms#topp:states", title="USA", abstract="", keywords=[],
    bbox=[-124.7, 24.9, -66.9, 49.4],
    external_url="https://ows.example.com/wms?request=GetCapabilities",
    items_url=None,
    raster_tiles_url="https://ows.example.com/wms?service=WMS&request=GetMap&layers=topp:states&bbox={bbox-epsg-3857}",
)


def test_reference_persists_tiles_url_and_layer_kind(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RASTER_REC]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="wms",
        url="https://ows.example.com/wms", mode="reference", enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="wms#topp:states")
    assert rec.tiles_url == RASTER_REC.raster_tiles_url
    assert rec.layer_kind == "raster"
    assert rec.external_url == RASTER_REC.external_url
```

> **Note** : `_fake_connector` (livré par SP-12d dans ce fichier) porte `fetch` + `fetch_copy_geojson` ; ici seul `fetch` est utilisé (mode reference).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "persists_tiles_url" -v`
Expected: FAIL (`HarvestRecord` n'a pas `tiles_url`/`layer_kind`/`external_url` ; `create_record` ne les accepte pas)

- [ ] **Step 3: Ajouter les colonnes au modèle**

Dans `core/app/harvest/models.py`, à la fin de `HarvestRecord` (après `is_stale`) :

```python
    external_url: Mapped[str | None] = mapped_column(String, nullable=True)
    tiles_url: Mapped[str | None] = mapped_column(String, nullable=True)
    layer_kind: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Écrire la migration 0017**

`core/alembic/versions/0017_harvest_layer_columns.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""harvest_records : external_url + tiles_url + layer_kind (SP-12e)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("harvest_records", sa.Column("external_url", sa.String(), nullable=True))
    op.add_column("harvest_records", sa.Column("tiles_url", sa.String(), nullable=True))
    op.add_column("harvest_records", sa.Column("layer_kind", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("harvest_records", "layer_kind")
    op.drop_column("harvest_records", "tiles_url")
    op.drop_column("harvest_records", "external_url")
```

- [ ] **Step 5: Étendre `create_record` (repository)**

Dans `core/app/harvest/repository.py`, remplacer `create_record` :

```python
def create_record(
    session: Session, *, tenant_id: str, source_id: str, external_id: str,
    item_id: str | None, collection_id: str | None, content_hash: str | None,
    external_url: str | None = None, tiles_url: str | None = None,
    layer_kind: str | None = None,
) -> HarvestRecord:
    record = HarvestRecord(
        id=uuid.uuid4().hex, tenant_id=tenant_id, source_id=source_id,
        external_id=external_id, item_id=item_id, collection_id=collection_id,
        content_hash=content_hash, external_url=external_url, tiles_url=tiles_url,
        layer_kind=layer_kind,
    )
    session.add(record)
    session.flush()
    return record
```

- [ ] **Step 6: Renseigner les colonnes dans `service.py`**

Ajouter le helper (après `_content_hash`) :

```python
def _layer_kind(rec: HarvestedRecord) -> str | None:
    if rec.raster_tiles_url is not None:
        return "raster"
    if rec.items_url is not None:
        return "feature"
    return None
```

Dans `_upsert_reference`, au `create_record` (branche `existing is None`), ajouter les kwargs :

```python
        harvest_repo.create_record(
            session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
            item_id=item.id, collection_id=None, content_hash=digest,
            external_url=rec.external_url, tiles_url=rec.raster_tiles_url, layer_kind=_layer_kind(rec),
        )
```

Et dans la branche « contenu changé » (`existing.content_hash != digest`), rafraîchir aussi les colonnes en passant par `update_record` (qui accepte déjà `**fields`) :

```python
    if existing.content_hash != digest:
        items_repo.update_item(
            session, tenant_id=source.tenant_id, item_id=existing.item_id,
            title=rec.title, abstract=rec.abstract, keywords=rec.keywords, is_published=None,
        )
    harvest_repo.update_record(
        session, existing, content_hash=digest, harvested_at=_now(), is_stale=False,
        external_url=rec.external_url, tiles_url=rec.raster_tiles_url, layer_kind=_layer_kind(rec),
    )
```

Dans `_upsert_copy`, au `create_record` (mode copy, WFS) ajouter `external_url`/`layer_kind` (tiles_url reste `None` en copie) :

```python
    harvest_repo.create_record(
        session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
        item_id=result.item_id, collection_id=result.collection_id, content_hash=digest,
        external_url=rec.external_url, tiles_url=None, layer_kind=_layer_kind(rec),
    )
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "persists_tiles_url" -v`
Expected: PASS

- [ ] **Step 8: Non-régression service + repository (SQLite always-run)**

Run: `cd core && uv run pytest tests/test_harvest_service.py tests/test_harvest_repository.py -k "not postgis" -v`
Expected: PASS (aucune régression ; `Base.metadata.create_all` en test crée les nouvelles colonnes)

- [ ] **Step 9: Vérifier la migration à blanc (upgrade/downgrade head)**

Run: `cd core && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (contre une base jetable ; à défaut, `uv run alembic history | head` doit montrer `0017 -> 0016`)
Expected: `0017` s'applique et se rétracte sans erreur

- [ ] **Step 10: Commit**

```bash
git add core/alembic/versions/0017_harvest_layer_columns.py core/app/harvest/models.py core/app/harvest/repository.py core/app/harvest/service.py core/tests/test_harvest_service.py
git commit -m "feat(core): persistance external_url/tiles_url/layer_kind sur harvest_records (SP-12e)"
```

---

## Task 7: Endpoint `GET /harvest/layers` (couches raster affichables, filtrées tenant + can())

**Files:**
- Modify: `core/app/harvest/repository.py` (nouvelle `list_layer_records`)
- Modify: `core/app/harvest/routes.py` (route `GET /harvest/layers`)
- Test: `core/tests/test_harvest_layers_endpoint.py`

**Interfaces:**
- Consumes: `HarvestRecord.tiles_url`/`item_id` (Task 6), `Item` (jointure titre), `items_repo.get_access_facts` + `can` (gating, patron `GET /items/{id}`).
- Produces:
  - `repository.list_layer_records(session, *, tenant_id, q=None) -> list[Row]` — lignes `(item_id, title, tiles_url, layer_kind)` où `tiles_url IS NOT NULL`, filtrées tenant + `q` (ILIKE titre).
  - `GET /harvest/layers?q=<opt>` (auth requise, pas admin) → `{ "layers": [ { "id", "title", "kind": "raster", "tilesUrl" } ] }`, chaque ligne filtrée par `can(read)`.

- [ ] **Step 1: Write the failing test**

`core/tests/test_harvest_layers_endpoint.py` (suivre le harnais `client`/fixtures de `test_harvest_routes.py` ; ici un item raster **appartenant** à l'utilisateur courant est visible, un item raster d'un autre owner non publié ne l'est pas) :

```python
# SPDX-License-Identifier: Apache-2.0
# Réutiliser exactement le harnais (app, fixtures client/utilisateur, override
# de get_current_user) de tests/test_harvest_routes.py. Le pseudo-code ci-dessous
# nomme les helpers de façon générique — les aligner sur ceux du fichier voisin.


def test_layers_returns_only_raster_records_of_visible_items(client, seed):
    # seed crée : (a) un harvest_record raster tiles_url non-null pour un item
    # possédé par l'utilisateur courant ; (b) un harvest_record sans tiles_url
    # (WFS référence) ; (c) un raster tiles_url non-null pour un item d'un autre
    # owner, non publié, non partagé.
    resp = client.get("/harvest/layers")
    assert resp.status_code == 200
    layers = resp.json()["layers"]
    ids = {l["id"] for l in layers}
    assert seed.visible_raster_item_id in ids           # (a) visible
    assert seed.feature_item_id not in ids              # (b) tiles_url null → exclu
    assert seed.hidden_raster_item_id not in ids        # (c) can(read) → exclu
    layer = next(l for l in layers if l["id"] == seed.visible_raster_item_id)
    assert layer["kind"] == "raster"
    assert layer["tilesUrl"].startswith("https://ows.example.com/")


def test_layers_filters_by_q(client, seed):
    resp = client.get("/harvest/layers", params={"q": "zzz-nomatch"})
    assert resp.status_code == 200
    assert resp.json()["layers"] == []
```

> **Note d'exécution (importante)** : ce test a besoin d'un `seed` qui insère des `items` + `harvest_records` réels via `items_repo.create_item` et `harvest_repo.create_record(..., tiles_url=..., item_id=...)`. Construire ce `seed` en s'appuyant sur les fixtures existantes de `test_harvest_routes.py` (tenant/user/admin, session). Un item « possédé par l'utilisateur courant » = `owner_id = user.id` (visible via `can(read)` par ownership) ; un item « caché » = `owner_id` d'un second utilisateur, `is_published=False`, `is_public=False`, non partagé. Ne pas inventer d'API : `create_item(session, tenant_id=, owner_id=, resource_type="external", title=)` puis `update_item(...)` si besoin, exactement comme `service._upsert_reference`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_layers_endpoint.py -v`
Expected: FAIL (404/405 : route `/harvest/layers` inexistante)

- [ ] **Step 3: Ajouter `list_layer_records` (repository)**

Dans `core/app/harvest/repository.py`, ajouter l'import `Item` en tête :

```python
from app.items.models import Item
```

Et la fonction (après `mark_missing_as_stale`) :

```python
def list_layer_records(session: Session, *, tenant_id: str, q: str | None = None):
    stmt = (
        select(HarvestRecord.item_id, Item.title, HarvestRecord.tiles_url, HarvestRecord.layer_kind)
        .join(Item, Item.id == HarvestRecord.item_id)
        .where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.tiles_url.is_not(None),
        )
    )
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    return list(session.execute(stmt).all())
```

- [ ] **Step 4: Ajouter la route `GET /harvest/layers`**

Dans `core/app/harvest/routes.py`, ajouter les imports :

```python
from app.items import repository as items_repo
from app.sharing.authorization import can
```

Et la route (après `list_sources`, avant `get_source` pour que `/harvest/layers` ne soit pas capté par `/harvest/sources/{source_id}` — routes distinctes, ordre sans ambiguïté ; la placer où c'est lisible) :

```python
@router.get("/harvest/layers")
def list_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, tiles_url, _layer_kind in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title, "kind": "raster", "tilesUrl": tiles_url})
    return {"layers": layers}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_layers_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: Non-régression routes harvest + lint imports**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -k "not postgis" -v && uv run lint-imports`
Expected: PASS ; `lint-imports` clean (`app.harvest` importe déjà `app.items`/`app.sharing`)

- [ ] **Step 7: Commit**

```bash
git add core/app/harvest/repository.py core/app/harvest/routes.py core/tests/test_harvest_layers_endpoint.py
git commit -m "feat(core): GET /harvest/layers — couches raster affichables filtrées can() (SP-12e)"
```

---

## Task 8: Shell — dialogue (options WMS/WFS/WMTS + gating du mode copie)

**Files:**
- Modify: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Test: `shell/src/shell/CreateHarvestSourceDialog.test.tsx`

**Interfaces:**
- Consumes: `HarvestSourceType` (Task 5), `useCreateHarvestSource`, `useInstanceInfo`.
- Produces:
  - `<select aria-label="Type">` a 5 options : STAC, ArcGIS Feature Service, WMS, WFS, WMTS.
  - Le mode « Copie » est **désactivé** (option grisée) sauf pour `{stac, arcgis, wfs}` ; passer à `wms`/`wmts` alors que `mode="copy"` réinitialise `mode` à `reference`.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/shell/CreateHarvestSourceDialog.test.tsx` (suivre le harnais réel du fichier — `renderWithProviders`/serveur MSW ; s'aligner sur les tests existants) :

```typescript
it("envoie le type WMS et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "s1", type: "wms", url: "https://ows/x", mode: "reference",
        enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
      }, { status: 201 });
    }),
  );

  renderWithProviders(<CreateHarvestSourceDialog open={true} onClose={() => {}} />);
  await userEvent.type(screen.getByLabelText("URL"), "https://ows/x");
  // Passer d'abord en copie (autorisé pour STAC), puis basculer en WMS :
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wms");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(body).toEqual({
    type: "wms", url: "https://ows/x", mode: "reference", enabled: true,
  }));
});

it("garde le mode copie disponible pour WFS", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })));
  renderWithProviders(<CreateHarvestSourceDialog open={true} onClose={() => {}} />);
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wfs");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: FAIL (pas d'options WMS/WFS/WMTS ; pas de gating copie)

- [ ] **Step 3: Ajouter options + gating**

Dans `CreateHarvestSourceDialog.tsx`, définir la règle de copie et l'appliquer. Ajouter après les `useState` :

```typescript
  const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs"];
  const copyAllowed = COPY_TYPES.includes(type);
```

Remplacer le `onChange` du `<select aria-label="Type">` pour forcer le mode :

```tsx
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={type}
            onChange={(e) => {
              const next = e.target.value as HarvestSourceType;
              setType(next);
              if (!["stac", "arcgis", "wfs"].includes(next)) setMode("reference");
            }}
          >
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
            <option value="wmts">WMTS</option>
          </select>
```

Dans le `<select aria-label="Mode">`, désactiver l'option Copie quand non autorisée :

```tsx
          <select
            aria-label="Mode"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">Référence</option>
            <option value="copy" disabled={!copyAllowed}>Copie</option>
          </select>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: PASS (ancien + nouveaux)

- [ ] **Step 5: Build shell**

Run: `cd shell && npm run build`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/CreateHarvestSourceDialog.tsx shell/src/shell/CreateHarvestSourceDialog.test.tsx
git commit -m "feat(shell): options WMS/WFS/WMTS + gating du mode copie (SP-12e)"
```

---

## Task 9: Shell — `LayerSource` raster + `toMapLayer` + agrégation `itemClient` + mock E2E

**Files:**
- Modify: `shell/src/api/types.ts:66-75` (`LayerSource`)
- Modify: `shell/src/map/LayerPicker.tsx` (`toMapLayer`)
- Modify: `shell/src/api/itemClient.ts` (`fetchExternalRasterSources` + `listLayerSources`)
- Modify: `shell/e2e/mocks.ts` (route par défaut `**/harvest/layers*`)
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `GET /harvest/layers` (Task 7).
- Produces:
  - `LayerSource.service: "martin" | "core" | "external"` ; `LayerSource.kind: "vector" | "feature" | "raster"`.
  - `LayerPicker.toMapLayer` : `raster` → `{ id, title, visible:true, kind:"raster", tilesUrl, opacity:1 }`.
  - `itemClient.fetchExternalRasterSources(q?) -> LayerSource[]` sur `GET /harvest/layers` ; ajoutée en 3ᵉ source du `Promise.allSettled` de `listLayerSources` (panne tolérée).

- [ ] **Step 1: Élargir `LayerSource` (types.ts)**

Remplacer :

```typescript
export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "core" | "external";
  kind: "vector" | "feature" | "raster";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
};
```

- [ ] **Step 2: Write the failing test (LayerPicker raster)**

Ajouter à `shell/src/map/LayerPicker.test.tsx` une source raster dans le tableau `sources` :

```typescript
  { id: "ext-ortho", title: "Orthophoto (WMS)", service: "external", kind: "raster",
    tilesUrl: "https://ows.example.com/wms?...&bbox={bbox-epsg-3857}" },
```

Et un test :

```typescript
test("emits a raster MapLayer for an external source", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.click(await screen.findByRole("button", { name: /Orthophoto \(WMS\)/ }));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "raster",
    title: "Orthophoto (WMS)",
    visible: true,
    tilesUrl: "https://ows.example.com/wms?...&bbox={bbox-epsg-3857}",
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd shell && npm test -- LayerPicker`
Expected: FAIL (`toMapLayer` traite le raster comme `feature`, pas de `tilesUrl`/`kind:"raster"`)

- [ ] **Step 4: Brancher `raster` dans `toMapLayer`**

Dans `shell/src/map/LayerPicker.tsx`, dans `toMapLayer`, avant le `return` feature final :

```typescript
  if (source.kind === "raster") {
    return {
      id, title: source.title, visible: true, kind: "raster",
      tilesUrl: source.tilesUrl ?? "", opacity: 1,
    };
  }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd shell && npm test -- LayerPicker`
Expected: PASS (vector + feature + raster)

- [ ] **Step 6: Agréger la 3ᵉ source dans `itemClient`**

Dans `shell/src/api/itemClient.ts`, ajouter (à côté de `fetchCoreCollections`) :

```typescript
  async function fetchExternalRasterSources(q?: string): Promise<LayerSource[]> {
    const token = getToken();
    const query = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await fetch(`${coreUrl}/harvest/layers${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /harvest/layers`);
    const data = (await res.json()) as {
      layers?: { id: string; title: string; kind: "raster"; tilesUrl: string }[];
    };
    return (data.layers ?? []).map((l) => ({
      id: l.id, title: l.title, service: "external" as const, kind: "raster" as const,
      tilesUrl: l.tilesUrl,
    }));
  }
```

Et dans `listLayerSources`, ajouter la 3ᵉ promesse :

```typescript
    async listLayerSources(params?: { q?: string }): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(params?.q),
        fetchCoreCollections(params?.q),
        fetchExternalRasterSources(params?.q),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },
```

- [ ] **Step 7: Route par défaut inerte dans les mocks E2E**

Dans `shell/e2e/mocks.ts`, à côté de la route `https://core.test/collections*`, ajouter une route par défaut renvoyant `[]` (les specs qui testent le raster la surchargent) :

```typescript
  // Cœur couches raster externes (SP-12e) — LayerPicker 3ᵉ source. Défaut vide :
  // toute spec pré-existante (qui ne moissonne aucune couche raster) se comporte
  // comme avant. La spec harvest-wms surcharge cette route.
  await page.route("https://core.test/harvest/layers*", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const all = [] as { id: string; title: string; kind: "raster"; tilesUrl: string }[];
    const layers = q ? all.filter((l) => l.title.toLowerCase().includes(q.toLowerCase())) : all;
    await route.fulfill({ json: { layers } });
  });
```

- [ ] **Step 8: Vérifier build + Vitest + non-régression E2E existante**

Run: `cd shell && npm run build && npm test && npm run e2e`
Expected: build clean ; Vitest vert ; toutes les specs E2E existantes vertes (la nouvelle route par défaut ne modifie aucun comportement)

- [ ] **Step 9: Commit**

```bash
git add shell/src/api/types.ts shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx shell/src/api/itemClient.ts shell/e2e/mocks.ts
git commit -m "feat(shell): source raster externe dans LayerPicker + agrégation /harvest/layers (SP-12e)"
```

---

## Task 10: E2E `harvest-wms.spec.ts` + mise à jour docs/feuille de route

**Files:**
- Create: `shell/e2e/harvest-wms.spec.ts`
- Modify: `CLAUDE.md` (feuille de route : SP-12e livré, reste SP-12f/g)

**Interfaces:**
- Consumes: dialogue (Task 8), `LayerPicker` raster (Task 9), routes `/harvest/*` + `/harvest/layers` + création de carte mockées.
- Produces: parcours admin → source WMS → moissonnage (mock) → item raster externe au catalogue → éditeur de carte → recherche `LayerPicker` → ajout de la couche → **assertion qu'une couche raster est ajoutée à la carte** (présente dans le `LayersPanel`). Miroir de l'E2E SP-12d.

- [ ] **Step 1: Écrire la spec E2E**

`shell/e2e/harvest-wms.spec.ts` :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const CAPS = "https://ows.example.com/geoserver/wms?service=WMS&request=GetCapabilities";
const TILES = "https://ows.example.com/geoserver/wms?service=WMS&version=1.3.0&request=GetMap&layers=topp:states&styles=&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&format=image/png&transparent=true";

test("un admin déclare une source WMS, la moissonne, et affiche la couche raster dans une carte", async ({ page }) => {
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
  // Couches raster exposées par /harvest/layers après moissonnage.
  const rasterLayers: { id: string; title: string; kind: "raster"; tilesUrl: string }[] = [];

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "wms", url: CAPS, mode: "reference", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "wms", url: CAPS, mode: "reference", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-23T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set(`${CAPS}#topp:states`, {
      pk: "ext-wms-1", resourceType: "external", title: "USA States (WMS distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    });
    rasterLayers.length = 0;
    rasterLayers.push({ id: "ext-wms-1", title: "USA States (WMS distant)", kind: "raster", tilesUrl: TILES });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/harvest/layers*", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const layers = q
      ? rasterLayers.filter((l) => l.title.toLowerCase().includes(q.toLowerCase()))
      : rasterLayers;
    await route.fulfill({ json: { layers } });
  });

  // 1) Déclarer et moissonner la source WMS
  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(CAPS);
  await dialog.getByLabel("Type").selectOption("wms");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "wms", url: CAPS, mode: "reference", enabled: true,
  });
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  // 2) L'item raster externe apparaît au catalogue
  await page.goto("/");
  await expect(page.getByText("USA States (WMS distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  // 3) Créer une carte, chercher la couche, l'ajouter
  await page.getByRole("button", { name: "Nouveau" }).click();
  const newDialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await newDialog.getByLabel("Type").selectOption("map");
  await newDialog.getByLabel("Titre").fill("Carte WMS");
  await newDialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  const search = page.getByRole("searchbox", { name: /rechercher une source de couche/i });
  await search.fill("USA");
  await page.getByRole("button", { name: /USA States \(WMS distant\)/ }).click();

  // 4) Assertion : une couche raster est ajoutée à la carte (LayersPanel).
  await expect(page.getByRole("button", { name: "Retirer USA States (WMS distant)" })).toBeVisible();
});
```

> **Note d'exécution** : vérifier dans l'éditeur de carte (`/maps/:id`) le libellé exact du panneau et du bouton « Nouveau »/« Créer »/« Type »/« Titre » via la spec voisine `shell/e2e/layer-picker-search.spec.ts` et `map-editor.spec.ts` — les réutiliser tels quels. Le bouton « Retirer <titre> » est le `aria-label` produit par `LayersPanel.tsx` : c'est la preuve visible qu'un `MapLayer` a bien été ajouté à la config.

- [ ] **Step 2: Run E2E to verify it passes**

Run: `cd shell && npm run e2e -- harvest-wms`
Expected: PASS

- [ ] **Step 3: Mettre à jour `CLAUDE.md`**

Dans la section « Fait », remplacer la ligne SP-12 :

```markdown
- **SP-12** (a→e) — fédération STAC/DCAT : API STAC native (lecture seule),
  export DCAT-AP (JSON-LD), moteur de moissonnage + connecteur STAC externe,
  connecteur ArcGIS FS + garde d'egress SSRF, connecteurs GetCapabilities
  WMS/WFS/WMTS + affichage raster (LayerPicker → `GET /harvest/layers`).
```

Dans la section « À venir », remplacer la ligne SP-12 (e→g) :

```markdown
- **SP-12** (f→g) — connecteurs de moissonnage restants : CSW/ISO 19139 (f) →
  CKAN (g) (abstraction `HarvestConnector` déjà dimensionnée).
```

- [ ] **Step 4: Non-régression suite E2E complète + Vitest + build**

Run: `cd shell && npm run e2e && npm test && npm run build`
Expected: toutes les specs E2E vertes (existantes + `harvest-wms`) ; Vitest vert ; build clean

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/harvest-wms.spec.ts CLAUDE.md
git commit -m "test(e2e): admin WMS → moissonnage → couche raster dans une carte (SP-12e)"
```

---

## Vérification finale de branche

- [ ] **Step 1: Suite cœur complète (SQLite, always-run) + lint imports**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS ; `lint-imports` 1 kept / 0 broken

- [ ] **Step 2: Suite postgis réelle**

Run: `cd core && CORE_TEST_DATABASE_URL=<dsn-postgis-pgvector> uv run pytest -m postgis`
Expected: PASS (dont les tests copy WFS/service si marqués postgis). Sans DB disponible : démarrer un conteneur jetable via `deploy/postgis/Dockerfile` (patron SP-6b/SP-11) et exporter son DSN — ne pas déclarer terminé sur un simple skip.

- [ ] **Step 3: Shell complet**

Run: `cd shell && npm test && npm run e2e && npm run build`
Expected: Vitest vert ; E2E toutes vertes (existantes + `harvest-wms`) ; build clean

- [ ] **Step 4: Pas de drift OpenAPI résiduel**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json && git diff --exit-code openapi.json`
Expected: aucun diff (déjà régénéré en Task 5)

- [ ] **Step 5: Revue finale de branche**

Dispatcher une revue (`superpowers:requesting-code-review`, modèle opus) sur toute la branche. Vérifier les propriétés bout-en-bout :
- **XML sûr** : `defusedxml` neutralise XXE + billion-laughs (`test_harvest_ows.py`) ; aucun connecteur ne lève hors de lui-même sur capabilities malformé/géant/cyclique.
- **Garde d'egress dans le chemin** : WMS/WFS/WMTS construisent leur client gardé par défaut (comme STAC/ArcGIS) ; la copie WFS passe par `http_get` gardé injecté.
- **Séparation raster/vecteur** : un record pose soit `items_url` soit `raster_tiles_url`, jamais les deux ; `_layer_kind` cohérent avec les colonnes persistées.
- **Dégradation** : WMS sans EPSG:3857 et WMTS sans matrice Web Mercator entière → `raster_tiles_url=None`, couche cataloguée mais absente de `/harvest/layers`.
- **`/harvest/layers`** : ne renvoie que `tiles_url IS NOT NULL`, filtré tenant + `can(read)` + `q` (`test_harvest_layers_endpoint.py`).
- **Bornes dures** : `_MAX_LAYERS`, `_MAX_DEPTH`, `_MAX_COPY_PAGES`, `_MAX_COPY_FEATURES` — pas de boucle infinie ni de worker bloqué.
- **Aucune régression** des specs E2E existantes ; drift OpenAPI borné à l'enum `type`.
- **Frontière carte** : le fil raster réutilise le rendu `kind:"raster"` de `MapView` sans nouvelle primitive.

---

## Self-Review (rempli par l'auteur du plan)

**Couverture du spec :**
- §2 archi (3 connecteurs + `ows.py` + réutilisation `MapView`) : Tasks 1-4, 9. §2.1 `ows.py` (parse défensif, helpers namespace, bornes) : Task 1. §2.2 champ `raster_tiles_url` : Task 1.
- §3.1 WMS (couche nommée→record, bbox 1.3.0/1.1.1, GetMap 3857, dégradation sans 3857, copy=None) : Task 2. §3.2 WFS (FeatureType→record, GetFeature, copie paginée startIndex/count bornée/tolérante, raster=None) : Task 3. §3.3 WMTS (Layer→record, TileMatrixSet WebMercator, ResourceURL/KVP, dégradation non-entiers) : Task 4.
- §4.1 migration 0017 (3 colonnes) + persistance service : Task 6. §4.2 `GET /harvest/layers` (tenant + can() + q, forme JSON) : Task 7.
- §5 shell (schémas Literal : Task 5 ; `HarvestSourceType`+types : Tasks 5, 9 ; dialogue + gating copie : Task 8 ; `LayerSource`/`toMapLayer` raster : Task 9 ; agrégation `itemClient` tolérante : Task 9) ; `MapView` sait déjà rendre `raster` (vérifié : `shell/src/map/MapView.tsx:48-55`).
- §6 sécurité (SSRF egress + XML défensif + tuiles navigateur) : Tasks 1-4 + Global Constraints. §7 plan de tests (unitaires connecteurs, service/repo, shell, E2E) : chaque task + Task 10. §8 découpage 4 phases : Tasks 1-4 (phase 1) / 5-7 (phase 2) / 8-9 (phase 3) / 10 (phase 4). §9 résiduels documentés : Global Constraints + revue finale.

**Écart documenté vs spec §5.1** : le spec anticipe `Literal[...]` élargi ; le code réel part de `Literal["stac","arcgis"]` (SP-12d). Task 5 élargit à 5 valeurs et régénère OpenAPI/types (drift attendu et borné à l'enum `type`). Le gating copie serveur (`_check_copy_support`) est **déjà** en place (SP-12d) et rejette automatiquement `wms`/`wmts` en copie via `supports_copy=False` — aucune modif de route nécessaire pour ce contrôle.

**Placeholders signalés (non des trous)** : fixtures/harnais de test (`client_admin`, `renderWithProviders`/`server`, `seed` de `test_harvest_layers_endpoint`, libellés exacts de l'éditeur de carte) sont explicitement à aligner sur les fichiers voisins cités (`test_harvest_routes.py`, `HarvestSourcesAdminPage.test.tsx`, `layer-picker-search.spec.ts`, `map-editor.spec.ts`). La correction `external_url == CAPS` du connecteur WMS (Task 2) est signalée en note d'exécution.

**Cohérence des types :** `HarvestedRecord.raster_tiles_url` (défaut `None`) identique sur base/WMS/WFS/WMTS ; `fetch_copy_geojson(record, *, http_get) -> bytes | None` uniforme (WMS/WMTS → `None`) ; `create_record(..., external_url, tiles_url, layer_kind)` et `_layer_kind(rec)` cohérents entre repository/service/tests ; `list_layer_records` renvoie `(item_id, title, tiles_url, layer_kind)` consommé colonne par colonne dans la route ; `LayerSource.service:"external"` + `.kind:"raster"` cohérents entre types.ts / itemClient / LayerPicker / mocks ; gabarits d'URL (`{bbox-epsg-3857}`, `{z}/{y}/{x}`) identiques entre connecteur, test et E2E.
```

