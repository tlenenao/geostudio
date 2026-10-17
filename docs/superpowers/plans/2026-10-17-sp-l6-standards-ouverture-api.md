# SP-L6 « Standards et ouverture API » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fermer le lot L6 de l'audit `docs/revue/audit-2026-10-16/99-synthese.md` (+ `complement/ADDENDUM.md`) — moissonnage data.gouv.fr (udata), découverte OGC API (queryables, Tiles/TMS, pagination de `/collections`), identifiants filtrés en SQL (Features/STAC/WFS), WMS 1.1.1 + GetLegendGraphic + CRS France/outre-mer + grille NTF, contrat OpenAPI, métadonnées INSPIRE/DCAT, OGC API Records + ISO 19139, fonds de carte souverains.

**Architecture:** aucun nouveau moteur. Chaque standard est une projection supplémentaire des portes existantes : `get_collection_for_read` / `rls_scope` / masquage GAP-22 / `select_features` pour Features-WFS-STAC-Tiles, `list_items` / `list_published_items` (`can()`) pour Records, `_resolve_bbox_degrading` (DCAT) pour ISO 19139. Un seul nouveau module (`app/records/`), une seule migration (0095, deux colonnes de `collections`).

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pyproj/PROJ (grille `fr_ign_gr3df97a.tif`), Pillow, httpx, pytest (`postgis` réel), React/TS + vitest + MSW + Playwright.

**AUD couverts :** AUD-128 (T1, en premier : connecteur udata), AUD-041/042/044 (T2), AUD-043 + AUD-140 volet STAC/WFS (T3), AUD-045 + AUD-127 (T4), AUD-046 (T5), AUD-047 partiel + AUD-140 volet DCAT (T6), AUD-048 + AUD-047 volet ISO (T7), AUD-122 (T8). Décisions appliquées : **D10** (OGC sans imiter FeatureServer), **D11** (OGC API Records + export ISO 19139 ; CSW seulement si demandé → non fait).

**Dépendances :** AUD-020 (livré en L0 : export cohérent) — rien d'autre. Aucun lot parallèle n'est prérequis.

**Plage de migrations réservée : 0095-0098.** Ce plan n'en consomme qu'une : `0095_collection_keywords_inspire.py` (T6). 0096-0098 restent libres.

**Fichiers/zones touchés (détection de collisions avec les lots parallèles) :**

| Zone | Tâches | Lots susceptibles d'y toucher |
|---|---|---|
| `core/app/main.py` (OpenAPI, `app.state`, inclusion du routeur records) | T2, T5, T7 | L1a/L3 (lifespan, observabilité) |
| `core/Dockerfile` (grille PROJ) | T4 | L1a/L3 (image, exec) |
| `core/app/ows/{routes,wms,wms_routes,render,wfs}.py` | T2, T3, T4 | L2 (AUD-155 rate-limit OWS) |
| `core/app/features/{routes,repository}.py` | T2, T3 | L4 (lecture/agrégats) |
| `core/app/collections/{routes,repository,schemas,models}.py` | T2, T6 | L4/L5 |
| `core/app/items/repository.py` (`list_published_items`, `_bbox_clause`) | T7 | L5 (catalogue) |
| `core/app/stac/*`, `core/app/dcat/*`, `core/app/catalog/*`, `core/app/harvest/*` | T1, T3, T6, T7 | — |
| `core/app/ingestion/{parsers,importer}.py` | T4, T8 | L5 (ETL/import) |
| `core/pyproject.toml` (contrat de couches : `app.records`) | T7 | tout lot qui ajoute un module |
| `docker-compose.yml`, `.env.example`, `deploy/helm/geostudio/values.yaml` | T8 | L1a/L2/L3 |
| `shell/src/map/basemaps.ts`, `useBasemaps.ts`, `builder/widgets/mapWidget.tsx`, `builder/ExplorerDrawer.tsx`, `pages/CatalogSpatialFilter.tsx`, `api/domains/layers.ts` | T8 | L5 (widget carte) ; **`builder/pipeline/PipelinePreviewMap.tsx` laissé à L7 (AUD-161)** |
| `shell/src/shell/EditCollectionPanel.tsx`, `CreateHarvestSourcePanel.tsx`, `api/types.ts`, i18n `admin.ts`/`automation.ts` | T1, T6, T8 | L5 |
| `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` | T1-T8 | **tous** (régénérer après rebase, jamais fusionner à la main) |
| `docs/revue/inventaire-fonctionnalites.jsonl` | T9 | tous |

## Global Constraints

- Lire `CLAUDE.md` (§ Pièges récurrents) avant de commencer. L'addendum de l'audit prime sur la synthèse.
- `CORE_TEST_DATABASE_URL` pointe un postgis-test réel en `postgresql+psycopg://…` — **base jetable dédiée à ce lot** (d'autres agents tournent en parallèle, piège SP-49) ; sans elle les tests `postgis` skippent silencieusement.
- Le conteneur `postgis-test` n'est pas tracké par Alembic : après T6, `ALTER TABLE collections ADD COLUMN keywords json NOT NULL DEFAULT '[]', ADD COLUMN inspire_theme varchar NOT NULL DEFAULT ''` manuel sur la base de test partagée si les tests postgis sont lancés dessus.
- Toute route ou tout modèle exposé modifié → régénérer OpenAPI + types TS **dans le même commit** que la tâche :
  `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json`
  puis `cd ../shell && npm run gen:api-types`. Diff vide légitime pour une surface derrière un flag éteint (OWS/WMS).
- Toute surface nouvelle (route REST, outil MCP, route shell) → ligne dans `docs/revue/inventaire-fonctionnalites.jsonl` (**seule exception autorisée dans `docs/revue/`** : c'est une porte CI, `core/tests/test_feature_inventory.py`) ; fait en T9 pour tout le lot.
- Migration Alembic testée sur base **non vide**, upgrade → downgrade → upgrade (piège n°8), sur une base créée/détruite par le test.
- Jumelles listées avant de clore chaque tâche (piège n°14) — chaque tâche a sa liste « Jumelles ».
- `docker-compose.yml` / `.env.example` / Helm : modifications localisées (une ligne par service/variable), jamais de réordonnancement.
- Commits conventional en français, petits, un sujet, trailer exact :
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- **Interdit** : toucher `CLAUDE.md`, `docs/revue/*` (sauf l'inventaire), `docs/superpowers/2026-08-27-historique-execution-continu.md` (clôture documentaire par le contrôleur).
- Portes à garder vertes : `uv run ruff check . && uv run ruff format --check .`, `uv run lint-imports`, `uv run pytest`, `npm run lint && npm run format:check`, `npm run test`, `npm run build`, `npm run e2e`.

---

## Faits vérifiés / écarts à l'audit

Vérifiés contre le code de `dev` (8b09c207) et, pour les services tiers, par `curl` le 2026-10-17 (piège n°3) :

1. **AUD-128** — data.gouv.fr ne sert **pas** l'API CKAN : `GET https://www.data.gouv.fr/api/3/action/package_search` → 404. L'API udata `GET /api/1/datasets/?page_size=…` répond `{data, next_page, page, page_size, previous_page, total}` ; chaque dataset porte `id, slug, title, description, tags[] (chaînes), page, spatial.geom (GeoJSON ou null), resources[{format, url, title}]` (format en minuscules : `geojson`, `shp`…). `_pick_copy_resource` de `ckan.py` passe déjà le format en majuscules → réutilisable tel quel.
2. **AUD-041** — `CONFORMANCE_CLASSES` (`core/app/features/routes.py:106`) annonce `features-3 filter/features-filter` mais **aucune** route `/queryables` n'existe : non-conformité réelle (le filtre CQL2 exige `queryables` en Part 3 §7). L'addendum demande `cql2-json` : **non revendiqué** ici (seul `cql2-text` est implémenté par `app/features/cql2.py`) — pas de fausse classe.
3. **AUD-042** — Classes OGC API Tiles 1.0 / TMS 2.0 vérifiées sur docs.ogc.org : `http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/{core,tileset,tilesets-list,geodata-tilesets,mvt}` et `http://www.opengis.net/spec/tms/2.0/conf/{tilematrixset,json-tilematrixset}`. **Écart non signalé par l'audit** : la route `GET /collections/{id}/tiles/{tms}/{z}/{x}/{y}` (`core/app/ows/routes.py:300`) annonce le gabarit `{tileMatrix}/{tileCol}/{tileRow}` (ordre col/row) alors qu'OGC API Tiles impose `{tileMatrix}/{tileRow}/{tileCol}` → corrigé en T2 (la route garde son chemin, seuls l'ordre et les noms des paramètres changent ; `/0/0/0` et `/0/5/0`→400 restent vrais).
4. **AUD-044** — `GET /collections` (`core/app/collections/routes.py:546`) charge **toutes** les collections visibles en Python puis découpe ; aucun lien `next/prev`, pas d'`itemType` ni de `links` par collection (présents seulement dans `GET /collections/{id}`).
5. **AUD-043** — `select_features` n'a pas de filtre d'identifiants ; `stac/routes.py:422` filtre `ids` **après** la pagination SQL (pages vides, `next` incohérent). `STAC` revendique encore `ogcapi-features-1/1.0/conf/oas30` (`stac/serializers.py:17`) alors que la REV-364 b l'a retiré côté Features (document servi en OpenAPI 3.1).
6. **AUD-140** — STAC `/search` : paramètres inconnus ignorés silencieusement, `intersects` absent ; WFS `GetFeature` ignore `RESOURCEID` ; DCAT `catalog` sans `hydra:` pour la pagination.
7. **AUD-045** — `wms_routes.py:250` refuse toute version ≠ 1.3.0 (test `{"version": "1.1.1"}` dans la liste des requêtes invalides de `tests/test_ows_wms.py` — **à remplacer** par `1.0.0`) ; aucune `GetLegendGraphic`.
8. **AUD-127** — `SUPPORTED_EPSG = (4326, 3857, 2154)` (`core/app/ogc_crs.py:7`), `wms.CRS_TABLE` idem : aucune projection CC 42-50 (3942-3950) ni outre-mer (2972 Guyane, 2975 Réunion, 4471 Mayotte, 5490 Antilles). **Grille NTF** : l'audit cite `ntf_r93.gsb` ; la grille réellement consommée par PROJ 9 pour NTF→RGF93 est **`fr_ign_gr3df97a.tif`**. Hors réseau, `27572→4326` reste `best_available=True` (Helmert ~2 m) alors que `27572→4171` vaut `best_available=False` (repli « ballpark ») → le contrôle doit porter sur la transformation vers **4171** puis enchaîner 4171→4326. Point de référence : (600000, 2428000) EPSG:27572 → (2.3365241427675185, 48.85034948131713) avec grille, (2.336505662635834, 48.85034659272486) en Helmert (~1,4 m d'écart).
9. **AUD-046** — `FastAPI(title=…, version="0.1.0")` en dur (`core/app/main.py:184`), pas de `description`, pas de `securitySchemes`, opérations sans `tags`. `importlib.metadata.version("geostudio-core")` lève `PackageNotFoundError` (paquet non installé, `uv export --no-emit-project`) → la version se lit dans `pyproject.toml` (copié dans l'image en `/app/pyproject.toml`, `core/Dockerfile:40`). **La v0.2.0 n'est pas taguée** : le numéro reste `0.1.0` (montée = décision de release, reportée).
10. **AUD-047** — `Collection` n'a ni mots-clés ni thème INSPIRE ; DCAT n'émet ni `dcat:keyword` ni `dcat:theme`. `dct:conformsTo` CRS par dataset exigerait une introspection par collection dans `get_catalog` (coût N) : seul `dct:conformsTo` OGC API Features sur la distribution GeoJSON est posé ; l'export **par format** (CSV/GPKG) n'est pas une distribution publique (export authentifié) → reporté.
11. **AUD-048** — OGC API Records Part 1 (OGC 20-004r1) : la norme écrit `record-api` dans le texte et `records-api` dans l'annexe A.3 ; on annonce `http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/records-api` (URI de l'annexe). `get_published_item` (`items/repository.py:810`) **ne filtre pas** `content_status = 'deprecated'` alors que `list_published_items` le fait — Records s'aligne sur la liste (filtre appliqué côté Records), la divergence de `/public/items/{id}` est consignée comme jumelle, pas corrigée ici (comportement public existant).
12. **AUD-122** — fonds par défaut `demotiles.maplibre.org` et `cartocdn` en dur (`shell/src/map/basemaps.ts`, `mapWidget.tsx:35`, `ExplorerDrawer.tsx:15`, `core/app/ingestion/importer.py:59`). Gabarit Géoplateforme vérifié (HTTP 200) : `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&FORMAT=image/png` (et `ORTHOIMAGERY.ORTHOPHOTOS` / `image/jpeg`). Le style vectoriel PLAN.IGN n'a pas répondu (timeout) → fonds IGN en raster `xyz:`.

## Reporté (avec raison)

- **WFS-T + FES XML** (AUD-140 addendum) : parseur d'entrée XML non fiable à écrire (surface d'attaque, taille L) ; l'écriture standard existe déjà via OGC API Features Part 4. Lot dédié si demandé.
- **ExtendedCapabilities INSPIRE** (WMS/WFS) : exige une métadonnée de **service** (fiche ISO du service, point de contact juridique) — décision produit/conformité.
- **CSW** : D11 (« seulement si demandé »).
- **Distributions DCAT par format** (CSV/GPKG) : l'export exige une authentification ; publier une URL anonyme = décision sécurité (L2).
- **Thème « EU data-theme »** (vocabulaire `data-theme` de l'Office des publications) : mapping INSPIRE→data-theme non normatif, décision produit.
- **Pack Cadastre/INSEE/BD TOPO** (AUD-127 addendum) : données externes, licences et volumétrie hors lot.
- **Grilles PROJ côté PostGIS/DuckDB** : `ST_Transform` PostGIS et DuckDB spatial ont leur propre PROJ ; l'ingestion (seul point d'entrée des données NTF) passe par pyproj (T4). Reporté jusqu'à un cas d'usage de reprojection NTF côté base.
- **`PipelinePreviewMap.tsx`** fond par défaut : lot L7 (AUD-161) le réécrit.
- **Gabarit « swipe »** (`builder_templates.json:758`, `templates.data.json`) : styles cartocdn figés dans des gabarits déclaratifs livrés ; à régénérer quand la galerie de gabarits sera revue (limite consignée).
- **Négociation de version WMS** (GetCapabilities 1.1.1) : la 1.1.1 est acceptée pour GetMap/GetFeatureInfo/GetLegendGraphic ; le document de capacités reste 1.3.0 (les clients 1.1.1 courants — QGIS, OpenLayers — l'acceptent).
- **Montée de version 0.2.0** : décision de release.
- **Records `record-core-query-parameters`** (q en ET/OU exact, `externalIds`…) : non revendiqué ; `q` est une recherche plein texte simple.

---

### Task 1: AUD-128 — connecteur de moissonnage udata (data.gouv.fr)

**Files:**
- Create: `core/app/harvest/connectors/udata.py`
- Modify: `core/app/harvest/connectors/__init__.py` (registre)
- Modify: `core/app/harvest/schemas.py:34` (`Literal` du type)
- Create: `core/tests/test_harvest_udata_connector.py`
- Modify: `shell/src/api/types.ts:1497` (`HarvestSourceType`)
- Modify: `shell/src/shell/CreateHarvestSourcePanel.tsx:11,62`
- Modify: `shell/src/i18n/domains/automation.ts:122`
- Modify: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`
- Create: `shell/e2e/harvest-udata.spec.ts`

**Interfaces:**
- Consumes: `HarvestedRecord`, `HarvestFetchError` (`app/harvest/connectors/base.py`) ; `_pick_copy_resource(resources) -> tuple[str|None, str|None]` et `_geojson_envelope(geom) -> list[float]|None` (`app/harvest/connectors/ckan.py`) ; `build_guarded_client(timeout)` (`app/harvest/egress.py`).
- Produces: `UdataConnector` (`type = "udata"`, `supports_copy = True`, `fetch(url) -> list[HarvestedRecord]`, `fetch_copy_geojson(record, *, http_get) -> bytes | None`) ; type de source `"udata"` côté API et shell.

**Jumelles (piège n°14) :** `reader.ckan` dans `core/app/pipelines/ops/cloudfiles.py:691-746` (même erreur d'API sur data.gouv.fr) — **hors périmètre** (op de pipeline marquée expérimentale), à signaler au contrôleur ; la garde d'egress est partagée via `build_guarded_client` (rien à reporter).

- [ ] **Step 1: Test qui échoue** — créer `core/tests/test_harvest_udata_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-128 : connecteur udata (data.gouv.fr ne sert pas l'API CKAN, /api/3 -> 404)."""

import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.base import HarvestFetchError
from app.harvest.connectors.udata import UdataConnector

PORTAL = "https://www.data.gouv.fr"
API = f"{PORTAL}/api/1/datasets/"


def _ds(**overrides):
    ds = {
        "id": "ds-1",
        "slug": "batiments-ville",
        "title": "Bâtiments de la ville",
        "description": "Empreintes",
        "tags": ["bati", "urbain"],
        "page": f"{PORTAL}/fr/datasets/batiments-ville/",
        "spatial": {"geom": {"type": "Point", "coordinates": [2.0, 48.0]}},
        "resources": [
            {"format": "csv", "url": "https://x.test/a.csv"},
            {"format": "geojson", "url": "https://x.test/a.geojson"},
        ],
    }
    ds.update(overrides)
    return ds


def _page(data, next_page=None):
    return {"data": data, "next_page": next_page, "page": 1, "page_size": 100, "total": len(data)}


def _connector(handler) -> UdataConnector:
    return UdataConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_maps_dataset_fields_and_keeps_admin_filters():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=_page([_ds()]))

    recs = _connector(handler).fetch(f"{PORTAL}/?organization=abc&page=7")
    assert seen[0].path == "/api/1/datasets/"
    assert seen[0].params["organization"] == "abc"
    assert "page" not in seen[0].params and seen[0].params["page_size"] == "100"
    [r] = recs
    assert (r.external_id, r.title, r.abstract) == ("ds-1", "Bâtiments de la ville", "Empreintes")
    assert r.keywords == ["bati", "urbain"]
    assert r.bbox == [2.0, 48.0, 2.0, 48.0]
    assert r.external_url == f"{PORTAL}/fr/datasets/batiments-ville/"
    assert (r.items_url, r.copy_filename) == ("https://x.test/a.geojson", "harvest.geojson")


def test_follows_next_page_on_same_host_only():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=_page([_ds(id="ds-2")], "https://evil.test/api/1/datasets/?page=3"))
        return httpx.Response(200, json=_page([_ds()], f"{API}?page=2&page_size=100"))

    recs = _connector(handler).fetch(PORTAL)
    assert [r.external_id for r in recs] == ["ds-1", "ds-2"]


def test_missing_spatial_and_page_fall_back():
    def handler(request):
        return httpx.Response(200, json=_page([_ds(spatial=None, page=None, resources=[])]))

    [r] = _connector(handler).fetch(PORTAL)
    assert r.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert r.external_url == f"{PORTAL}/datasets/batiments-ville"
    assert r.items_url is None


def test_root_failure_is_reported():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(HarvestFetchError):
        _connector(handler).fetch(PORTAL)


def test_registered_and_copy_capable():
    c = get_connector("udata")
    assert c.type == "udata" and c.supports_copy is True
```

- [ ] **Step 2:** `cd core && uv run pytest tests/test_harvest_udata_connector.py -v` → FAIL (`ModuleNotFoundError: app.harvest.connectors.udata`).

- [ ] **Step 3: Implémenter** `core/app/harvest/connectors/udata.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur udata (AUD-128) : data.gouv.fr et portails udata. L'API CKAN
(`/api/3/action/package_search`) n'existe pas sur data.gouv.fr (404) ; l'API
udata v1 pagine par `next_page` (URL absolue). Même plafonds et même règle
racine/pages suivantes que le connecteur CKAN."""

import logging
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from app.harvest.connectors.base import HarvestedRecord, HarvestFetchError
from app.harvest.connectors.ckan import _geojson_envelope, _pick_copy_resource

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_DATASETS = 500
_MAX_PAGES = 50
_PAGE_SIZE = 100
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


class UdataConnector:
    type = "udata"
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
        params = [(k, v) for k, v in parse_qsl(split.query) if k not in ("page", "page_size")]
        params.append(("page_size", str(_PAGE_SIZE)))
        page_url: str | None = (
            f"{split.scheme}://{split.netloc}/api/1/datasets/?{urlencode(params)}"
        )
        records: list[HarvestedRecord] = []
        for n in range(_MAX_PAGES):
            doc = _get_json(client, page_url, root=(n == 0))
            data = doc.get("data") if isinstance(doc, dict) else None
            if not isinstance(data, list) or not data:
                break
            for ds in data:
                rec = _dataset_to_record(ds, split.scheme, split.netloc)
                if rec is not None:
                    records.append(rec)
            if len(records) >= _MAX_DATASETS:
                break
            nxt = doc.get("next_page")
            nsplit = urlsplit(nxt) if isinstance(nxt, str) else None
            # next_page est une URL absolue fournie par le portail : ne jamais la
            # suivre hors de l'hôte déclaré par l'admin (egress déjà gardé, mais
            # une source ne doit pas en moissonner une autre).
            if nsplit is None or (nsplit.scheme, nsplit.netloc) != (split.scheme, split.netloc):
                break
            page_url = nxt
        else:
            logger.warning("udata harvest: plafond de %d pages pour %s, tronqué", _MAX_PAGES, admin_url)
        return records[:_MAX_DATASETS]


def _get_json(client, url: str, *, root: bool):
    try:
        response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if root:
            raise HarvestFetchError(
                f"document racine udata injoignable ou illisible : {url} ({exc})"
            ) from exc
        logger.warning("udata harvest: échec de récupération de %s : %s", url, exc)
        return None


def _dataset_to_record(ds: object, scheme: str, netloc: str) -> HarvestedRecord | None:
    if not isinstance(ds, dict) or not ds.get("id"):
        return None
    ident = str(ds["id"])
    slug = ds.get("slug") or ident
    spatial = ds.get("spatial")
    bbox = _geojson_envelope(spatial.get("geom")) if isinstance(spatial, dict) else None
    tags = ds.get("tags")
    items_url, copy_filename = _pick_copy_resource(ds.get("resources"))
    return HarvestedRecord(
        external_id=ident,
        title=str(ds.get("title") or slug),
        abstract=str(ds.get("description") or ""),
        keywords=[t for t in tags if isinstance(t, str)] if isinstance(tags, list) else [],
        bbox=bbox or list(_WORLD_BBOX),
        external_url=str(ds.get("page") or f"{scheme}://{netloc}/datasets/{slug}"),
        items_url=items_url,
        copy_filename=copy_filename,
    )
```

Registre (`core/app/harvest/connectors/__init__.py`) : ajouter `from app.harvest.connectors.udata import UdataConnector` (ordre alphabétique des imports) et `"udata": UdataConnector(),` après `"ckan": CkanConnector(),`.
Schéma (`core/app/harvest/schemas.py:34`) :

```python
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts", "csw", "ogc-records", "ckan", "udata"]
```

Vérifier par `grep -rn '"ckan"' core/app` qu'aucun autre `Literal`/liste de types (ex. réponse `HarvestSourceRead`) n'énumère les types : sinon y ajouter `"udata"` aussi.

- [ ] **Step 4:** `uv run pytest tests/test_harvest_udata_connector.py tests/test_harvest_ckan_connector.py tests/test_harvest_routes.py -v` → PASS.

- [ ] **Step 5: Shell** — `shell/src/api/types.ts:1497` :

```ts
export type HarvestSourceType =
  "stac" | "arcgis" | "wms" | "wfs" | "wmts" | "csw" | "ogc-records" | "ckan" | "udata";
```

`CreateHarvestSourcePanel.tsx` : `const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs", "ckan", "udata"];` et, juste après la ligne 62 :

```tsx
            <option value="udata">{t("harvest.typeUdata")}</option>
```

`automation.ts`, après `"harvest.typeCkan": "CKAN",` : `"harvest.typeUdata": "data.gouv.fr (udata)",`.

Test vitest, à ajouter dans `shell/src/pages/HarvestSourcesAdminPage.test.tsx` après le test CKAN « copie » (même `Harness`, même `server`) :

```tsx
test("déclare une source data.gouv.fr (udata) en mode copie", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/v1/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/v1/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "src-u",
          type: "udata",
          url: "https://www.data.gouv.fr",
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
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://www.data.gouv.fr");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "udata");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "udata",
      url: "https://www.data.gouv.fr",
      mode: "copy",
      enabled: true,
    }),
  );
});
```

E2E `shell/e2e/harvest-udata.spec.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME } from "./mocks";

const PORTAL = "https://www.data.gouv.fr";

test("un admin déclare une source data.gouv.fr (udata) en copie", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let created: unknown = null;
  await page.route("https://core.test/v1/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-u",
          type: "udata",
          url: PORTAL,
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({ json: { sources: [] } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(PORTAL);
  await panel.getByLabel("Type").selectOption("udata");
  await panel.getByLabel("Mode").selectOption("copy");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({ type: "udata", url: PORTAL, mode: "copy", enabled: true });
});
```

- [ ] **Step 6:** `cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx && npx playwright test e2e/harvest-udata.spec.ts` → PASS. Régénérer OpenAPI + types TS (incantation des Global Constraints) ; le `Literal` change `core-schema.d.ts`. `npm run build` → OK.

- [ ] **Step 7: Commit**

```bash
git add core/app/harvest core/tests/test_harvest_udata_connector.py core/openapi.json \
  shell/src/api shell/src/shell/CreateHarvestSourcePanel.tsx shell/src/i18n/domains/automation.ts \
  shell/src/pages/HarvestSourcesAdminPage.test.tsx shell/e2e/harvest-udata.spec.ts
git commit -m "feat(core): connecteur de moissonnage udata pour data.gouv.fr (AUD-128)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: AUD-041/042/044 — découverte OGC API (queryables, Tiles/TMS, `/collections` paginé)

**Files:**
- Modify: `core/app/features/routes.py:106-151` (conformance, landing, nouvelle route queryables)
- Modify: `core/app/ows/routes.py:263-330` (tilesets, tileset, TMS, ordre row/col)
- Modify: `core/app/ows/wms.py` (`tile_matrix_set_json`)
- Modify: `core/app/main.py:463` (`app.state.ogc_tiles_enabled`)
- Modify: `core/app/collections/repository.py:124-170` (`_visible_collections_stmt`, `page_visible_collections`)
- Modify: `core/app/collections/routes.py:546-600, 642-697` (`list_collections`, `get_collection`, `_ogc_links`)
- Test: `core/tests/test_ogc_discovery.py`, `core/tests/test_ows_wfs.py`

**Interfaces:**
- Consumes: `get_collection_for_read(session, user, collection_id, *, guest=None)`, `unmask_for_owner`, `hide_sensitive_columns`, `_property_columns(info) -> list[ColumnInfo]` (`app/features/repository.py:73`), `get_collection_tile(...)` (`app/features/tiles.py`), `wms.tile_matrix(z) -> (size_m, n)`, `wms.TMS_ORIGIN`, `wms.MAX_ZOOM`, `wms._SCALE0`.
- Produces: `GET /v1/collections/{collection_id}/queryables` (JSON Schema, `application/schema+json`) ; `TILES_CONFORMANCE_CLASSES: list[str]` (`app/features/routes.py`) ; `GET /v1/tileMatrixSets`, `GET /v1/tileMatrixSets/{tms_id}`, `GET /v1/collections/{collection_id}/tiles/{tms}` (si `CORE_OWS_ENABLED`) ; route de tuile `GET /v1/collections/{collection_id}/tiles/{tms}/{tile_matrix}/{tile_row}/{tile_col}` ; `wms.tile_matrix_set_json() -> dict` ; `page_visible_collections(session, *, tenant_id, user_id, can_see_all, q, limit, offset) -> tuple[list[Collection], int]` ; `_ogc_links(base: str, cid: str) -> list[dict]` (`app/collections/routes.py`).

**Jumelles :** `GET /collections/{id}` (reçoit aussi le lien `queryables` via `_ogc_links`) ; `stac/routes.py` et `dcat/routes.py` listent les collections via `list_visible_collections` (inchangé, leur pagination propre est déjà bornée — SP-50) ; `list_tilesets` et la nouvelle route tileset partagent `_tileset()`.

- [ ] **Step 1: Tests qui échouent** — dans `core/tests/test_ogc_discovery.py` : ajouter à la copie locale `CONFORMANCE_CLASSES` (après `features-filter`) la ligne `"http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/queryables",` puis ajouter :

```python
import dataclasses


def test_queryables_json_schema(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=True)
    r = client.get("/v1/collections/incidents/queryables")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/schema+json")
    body = r.json()
    assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert body["type"] == "object"
    assert body["properties"]["titre"] == {"title": "titre", "type": "string"}
    assert body["properties"]["geometry"]["x-ogc-role"] == "primary-geometry"
    assert body["$id"].endswith("/v1/collections/incidents/queryables")


def test_queryables_404_for_unknown(env):
    _app, client, *_ = env
    assert client.get("/v1/collections/nope/queryables").status_code == 404


def test_collections_list_is_ogc_and_paginated(env):
    app, client, admin, _r, _repo = env
    app.dependency_overrides[collections_routes.get_introspector] = lambda: (
        lambda session, table: dataclasses.replace(INFO, table_name=table)
    )
    _as(app, admin)
    for tn in ("incidents", "zones"):
        assert client.post("/v1/collections", json={"tableName": tn, "isPublic": True}).status_code == 201
    body = client.get("/v1/collections?limit=1").json()
    assert body["numberMatched"] == 2 and body["numberReturned"] == 1
    rels = {link["rel"]: link["href"] for link in body["links"]}
    assert "offset=1" in rels["next"] and "prev" not in rels
    col = body["collections"][0]
    assert col["itemType"] == "feature"
    assert {link["rel"] for link in col["links"]} >= {
        "self",
        "items",
        "http://www.opengis.net/def/rel/ogc/1.0/queryables",
    }
    second = client.get("/v1/collections?limit=1&offset=1").json()
    rels2 = {link["rel"]: link["href"] for link in second["links"]}
    assert "offset=0" in rels2["prev"] and "next" not in rels2
```

Dans `core/tests/test_ows_wfs.py`, ajouter :

```python
TILES_CORE = "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core"


def test_tiles_conformance_and_tms_discovery(env):
    c, _login, _admin = env
    _enable(c)
    assert TILES_CORE in c.get("/v1/conformance").json()["conformsTo"]
    assert c.get("/v1/tileMatrixSets").json()["tileMatrixSets"][0]["id"] == "WebMercatorQuad"
    tms = c.get("/v1/tileMatrixSets/WebMercatorQuad").json()
    assert tms["crs"] == "http://www.opengis.net/def/crs/EPSG/0/3857"
    assert len(tms["tileMatrices"]) == 23
    assert tms["tileMatrices"][1]["matrixWidth"] == 2
    assert c.get("/v1/tileMatrixSets/Nope").status_code == 404
    ts = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad").json()
    item = next(link for link in ts["links"] if link["rel"] == "item")
    assert item["href"].endswith("/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}")


def test_ogc_tile_path_is_matrix_row_col(env):
    c, _login, _admin = env
    _enable(c)
    # alpha (lon 1, lat 45) au zoom 1 : colonne 1 (est), ligne 0 (nord)
    ogc = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/1/0/1")
    legacy = c.get("/v1/collections/demo_ows/tiles/1/1/0.mvt")
    assert legacy.status_code == 200 and legacy.content
    assert ogc.status_code == 200 and ogc.content == legacy.content


def test_tiles_conformance_absent_when_ows_off(pg_engine, monkeypatch):
    monkeypatch.delenv("CORE_OWS_ENABLED", raising=False)
    c, _login, _admin = _build(pg_engine)
    assert TILES_CORE not in c.get("/v1/conformance").json()["conformsTo"]
```

Le test existant `test_ogc_tiles_same_bytes_and_rules_as_mvt_route` (`/0/0/0`, `/0/5/0` → 400) reste valide sans modification : vérifier qu'il passe toujours.

- [ ] **Step 2:** `cd core && uv run pytest tests/test_ogc_discovery.py -v` → FAIL (`queryables` 404, `links` absent) ; `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_ows_wfs.py -k "tiles or tile_path" -v` → FAIL.

- [ ] **Step 3: Queryables + conformance** — `core/app/features/routes.py` : ajouter `"http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/queryables",` dans `CONFORMANCE_CLASSES` juste après `features-filter`, puis remplacer `conformance()` et ajouter la route :

```python
# AUD-042 : annoncées seulement quand les routes Tiles/TMS sont montées (CORE_OWS_ENABLED,
# lu une fois par create_app -> app.state.ogc_tiles_enabled ; app.ows est au-dessus de
# app.features dans le contrat de couches, d'où l'état plutôt qu'un import).
TILES_CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/tileset",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/tilesets-list",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/geodata-tilesets",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/mvt",
    "http://www.opengis.net/spec/tms/2.0/conf/tilematrixset",
    "http://www.opengis.net/spec/tms/2.0/conf/json-tilematrixset",
]


@router.get("/conformance")
def conformance(request: Request):
    tiles = getattr(request.app.state, "ogc_tiles_enabled", False)
    return {"conformsTo": CONFORMANCE_CLASSES + (TILES_CONFORMANCE_CLASSES if tiles else [])}


_QUERYABLE_TYPES = {
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "datetime": {"type": "string", "format": "date-time"},
    "enum": {"type": "string"},
}


@router.get("/collections/{collection_id}/queryables")
def get_queryables(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    masked=Depends(get_masked_for_user),
):
    """OGC API Features Part 3 (AUD-041) : propriétés filtrables (CQL2 / filtres simples),
    même porte de lecture et même masquage que /items. Les colonnes list/unsupported
    ne sont pas filtrables (_where les refuse) donc absentes."""
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    props: dict[str, dict] = {}
    for c in _property_columns(info):
        if c.type not in _QUERYABLE_TYPES:
            continue
        schema = {"title": c.name, **_QUERYABLE_TYPES[c.type]}
        if c.type == "enum" and c.enum_values:
            schema["enum"] = list(c.enum_values)
        if c.max_length:
            schema["maxLength"] = c.max_length
        props[c.name] = schema
    if info.geometry_column:
        # alias « geometry » accepté par app/features/cql2.py pour la colonne géométrique
        props["geometry"] = {"format": "geometry-any", "x-ogc-role": "primary-geometry"}
    v1 = str(request.base_url).rstrip("/") + "/v1"
    body = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{v1}/collections/{col.id}/queryables",
        "type": "object",
        "title": col.title,
        "properties": props,
        "additionalProperties": False,
    }
    return JSONResponse(content=body, media_type="application/schema+json")
```

Ajouter `_property_columns` à l'import `from app.features.repository import CursorError, FilterError` (ligne 63) ; `get_collection_for_read`, `unmask_for_owner`, `get_share_link_actor`, `GuestActor`, `JSONResponse` sont déjà importés dans ce module (le vérifier par `grep -n` ; sinon les ajouter). Dans `landing_page`, ajouter aux `links` :

```python
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-schemes",
                "type": "application/json",
                "href": f"{v1}/tileMatrixSets",
            },
```

`core/app/main.py`, juste avant `if ows_routes.is_ows_enabled():` (l.463) :

```python
    app.state.ogc_tiles_enabled = ows_routes.is_ows_enabled()  # AUD-042 : /conformance
```

- [ ] **Step 4: TMS + tileset + ordre row/col** — `core/app/ows/wms.py`, après `tile_bbox` :

```python
def tile_matrix_set_json() -> dict:
    """WebMercatorQuad au format TMS 2.0 JSON (AUD-042)."""
    matrices = []
    for z in range(MAX_ZOOM + 1):
        size, n = tile_matrix(z)
        matrices.append(
            {
                "id": str(z),
                "scaleDenominator": _SCALE0 / n,
                "cellSize": size / 256,
                "cornerOfOrigin": "topLeft",
                "pointOfOrigin": [-TMS_ORIGIN, TMS_ORIGIN],
                "tileWidth": 256,
                "tileHeight": 256,
                "matrixWidth": n,
                "matrixHeight": n,
            }
        )
    return {
        "id": TMS,
        "title": "Google Maps Compatible for the World",
        "uri": "http://www.opengis.net/def/tilematrixset/OGC/1.0/WebMercatorQuad",
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "orderedAxes": ["E", "N"],
        "wellKnownScaleSet": "http://www.opengis.net/def/wkss/OGC/1.0/GoogleMapsCompatible",
        "tileMatrices": matrices,
    }
```

`core/app/ows/routes.py` : remplacer `list_tilesets` et `get_ogc_tile` par :

```python
def _tileset(request: Request, col) -> dict:
    base = f"{str(request.base_url).rstrip('/')}/v1"
    tiles = f"{base}/collections/{col.id}/tiles/{TMS}"
    return {
        "title": col.title,
        "dataType": "vector",
        "tileMatrixSetURI": TMS_URI,
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "links": [
            {"rel": "self", "type": "application/json", "href": tiles},
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-scheme",
                "type": "application/json",
                "href": f"{base}/tileMatrixSets/{TMS}",
            },
            {
                "rel": "item",
                "type": "application/vnd.mapbox-vector-tile",
                "templated": True,
                "href": f"{tiles}/{{tileMatrix}}/{{tileRow}}/{{tileCol}}",
            },
        ],
    }


@router.get("/tileMatrixSets")
def list_tile_matrix_sets(request: Request):
    base = f"{str(request.base_url).rstrip('/')}/v1"
    return {
        "tileMatrixSets": [
            {
                "id": TMS,
                "title": "Google Maps Compatible for the World",
                "uri": TMS_URI,
                "links": [{"rel": "self", "href": f"{base}/tileMatrixSets/{TMS}"}],
            }
        ]
    }


@router.get("/tileMatrixSets/{tms_id}")
def get_tile_matrix_set(tms_id: str):
    if tms_id != TMS:
        raise HTTPException(status_code=404, detail="unknown tile matrix set")
    return wms.tile_matrix_set_json()


@router.get("/collections/{collection_id}/tiles")
def list_tilesets(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
):
    col = _tiles_collection(session, user, guest, collection_id)
    return {"tilesets": [_tileset(request, col)]}


@router.get("/collections/{collection_id}/tiles/{tms}")
def get_tileset(
    collection_id: str,
    tms: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
):
    col = _tiles_collection(session, user, guest, collection_id)
    if tms != TMS:
        raise HTTPException(status_code=404, detail="unknown tile matrix set")
    return _tileset(request, col)
```

Puis, dans `get_ogc_tile`, changer le décorateur en `@router.get("/collections/{collection_id}/tiles/{tms}/{tile_matrix}/{tile_row}/{tile_col}")`, les paramètres `z: int, x: int, y: int` en `tile_matrix: int, tile_row: int, tile_col: int`, et l'appel en :

```python
    return get_collection_tile(
        collection_id,
        tile_matrix,
        tile_col,  # x
        tile_row,  # y
        request,
        bin=None,  # le binning ARC-22 reste propre à la route `.mvt`
        stat="count",
        field=None,
        bins=16,
        user=user,
        guest=guest,
        session=session,
        introspect=introspect,
        rls=rls,
        masked=masked,
    )
```

`wms` est importé dans `ows/routes.py` sous `from app.ows import wfs` seulement : ajouter `from app.ows import wfs, wms`. Vérifier par `grep -rn '"/collections/{collection_id}/tiles' core/app` qu'aucune route de `app/features/tiles.py` ne capture `/tiles/{tms}` (la route legacy est `/tiles/{z}/{x}/{y}.mvt`, 3 segments + suffixe : pas de conflit).

- [ ] **Step 5: `/collections` paginé en SQL** — `core/app/collections/repository.py` : extraire le filtre de visibilité et ajouter la page :

```python
def _visible_collections_stmt(*, tenant_id: str, user_id: str | None, can_see_all: bool):
    stmt = select(Collection).where(Collection.tenant_id == tenant_id)
    if not can_see_all:
        if user_id is None:
            stmt = stmt.where(Collection.is_public.is_(True))
        else:
            shared_ids = (
                select(CollectionShare.collection_id)
                .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
                .where(GroupMember.user_id == user_id, CollectionShare.tenant_id == tenant_id)
            )
            stmt = stmt.where(
                Collection.is_public.is_(True)
                | (Collection.owner_id == user_id)
                | Collection.id.in_(shared_ids)
            )
    return stmt
```

`list_visible_collections` commence désormais par `stmt = _visible_collections_stmt(tenant_id=tenant_id, user_id=user_id, can_see_all=can_see_all)` (le reste — recherche hybride, ILIKE, tri — inchangé). Ajouter :

```python
def page_visible_collections(
    session: Session,
    *,
    tenant_id: str,
    user_id: str | None,
    can_see_all: bool,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Collection], int]:
    """Page + total en SQL (AUD-044). Avec `q`, la recherche hybride est déjà bornée
    à _RRF_CANDIDATE_LIMIT candidats : découpage en Python sur cette liste bornée."""
    if q:
        cols = list_visible_collections(
            session, tenant_id=tenant_id, user_id=user_id, can_see_all=can_see_all, q=q
        )
        return cols[offset : offset + limit], len(cols)
    stmt = _visible_collections_stmt(tenant_id=tenant_id, user_id=user_id, can_see_all=can_see_all)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = session.scalars(
        stmt.order_by(Collection.title, Collection.id).offset(offset).limit(limit)
    ).all()
    return list(page), total
```

(ajouter `func` à l'import `sqlalchemy` du module s'il manque.)

`core/app/collections/routes.py` : helper partagé, placé au-dessus de `list_collections` :

```python
def _ogc_links(base: str, cid: str) -> list[dict]:
    """Liens OGC d'une collection (AUD-044), partagés liste/détail."""
    return [
        {"rel": "self", "type": "application/json", "href": f"{base}/collections/{cid}"},
        {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{cid}/items"},
        {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/queryables",
            "type": "application/schema+json",
            "href": f"{base}/collections/{cid}/queryables",
        },
    ]
```

`list_collections` : ajouter le paramètre `request: Request` (première position après `q`), remplacer le bloc `cols = repo.list_visible_collections(...)` … `cols_page = cols[offset : offset + limit]` par :

```python
    limit = min(limit, MAX_LIMIT)
    cols_page, total = repo.page_visible_collections(
        session,
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        can_see_all=can_manage_collections,
        q=q,
        limit=limit,
        offset=offset,
    )
```

et le `return` par :

```python
    base = str(request.base_url).rstrip("/") + "/v1"
    links = [{"rel": "self", "type": "application/json", "href": str(request.url)}]
    if offset + len(cols_page) < total:
        links.append(
            {
                "rel": "next",
                "type": "application/json",
                "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
            }
        )
    if offset > 0:
        links.append(
            {
                "rel": "prev",
                "type": "application/json",
                "href": str(
                    request.url.include_query_params(limit=limit, offset=max(offset - limit, 0))
                ),
            }
        )
    reveal_sensitive = _may_see_sensitive(session, user)
    collections = []
    for c in cols_page:
        body = _collection_json(
            c,
            permissions_by_id[c.id],
            owner=owners.get(c.owner_id),
            reveal_sensitive=reveal_sensitive or is_owner(user, c),
            geo_limited=c.table_name in geo_limits,
        )
        body["itemType"] = "feature"
        body["links"] = _ogc_links(base, c.id)
        collections.append(body)
    return {
        "collections": collections,
        "links": links,
        "numberMatched": total,
        "numberReturned": len(cols_page),
    }
```

Dans `get_collection`, remplacer l'affectation `body["links"] = [...]` par `body["links"] = _ogc_links(base, col.id)`.

- [ ] **Step 6:** `uv run pytest tests/test_ogc_discovery.py tests/test_collections_routes.py -v` puis `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_ows_wfs.py tests/test_ows_wms.py -v` → PASS. `grep -rln '"/v1/collections"' core/tests shell/src` : tout test qui compare le corps exact de `GET /collections` (clé `links` nouvelle) est mis à jour. Côté shell, `CollectionsAdminPage` lit `collections`/`numberMatched` : le champ `links` en plus ne casse rien (vérifier `npm run test -- CollectionsAdmin`).

- [ ] **Step 7:** Régénérer OpenAPI + types TS (route queryables publique ; routes Tiles derrière flag → absentes du document en CI, diff attendu pour queryables seulement). `uv run lint-imports` → OK.

- [ ] **Step 8: Commit**

```bash
git add core/app/features/routes.py core/app/ows core/app/main.py core/app/collections \
  core/tests/test_ogc_discovery.py core/tests/test_ows_wfs.py core/openapi.json shell/src/api/generated
git commit -m "feat(core): queryables, découverte OGC API Tiles/TMS et /collections paginé (AUD-041/042/044)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: AUD-043 + AUD-140 (STAC/WFS) — identifiants filtrés en SQL, STAC strict, WFS RESOURCEID

**Files:**
- Modify: `core/app/features/repository.py:167-180, 310-345` (`_where`, `_select_features` : kwarg `ids`)
- Modify: `core/app/stac/routes.py:302-510` (`SearchBody`, `_run_search`, `search_get`, `search_post`)
- Modify: `core/app/stac/serializers.py:17` (retrait `oas30`)
- Modify: `core/app/ows/routes.py:196-235` (`_get_feature`, `_type_name` inchangé)
- Test: `core/tests/test_features_repository.py`, `core/tests/test_stac_search.py`, `core/tests/test_stac_serializers.py:14`, `core/tests/test_ows_wfs.py`

**Interfaces:**
- Consumes: `_coerce_fid(info, fid) -> int | str | None` (`features/repository.py:403`) ; `_parse_geom_intersects(raw) -> dict | None` (`features/routes.py:267`).
- Produces: `select_features(session, info, *, …, ids: list[str] | None = None)` — `ids` vide/invalide ⇒ aucune ligne ; STAC `/search` GET/POST : `intersects` (GeoJSON), 400 sur paramètre/champ inconnu, `bbox`+`intersects` ⇒ 400, plus de `MAX_LIMIT` ids ⇒ 400 ; WFS `GetFeature` : `RESOURCEID`/`FEATUREID` (`<collection>.<fid>`, préfixe `gs:` toléré).

**Jumelles :** les deux formes de STAC `/search` (GET et POST) passent par `_run_search` (correctif unique) ; le lien `next` doit porter `intersects` ; WFS `hits` + `RESOURCEID` (même kwarg) ; `GET /collections/{id}/items/{fid}` (déjà par PK, rien à faire).

- [ ] **Step 1: Tests qui échouent** — `core/tests/test_features_repository.py` :

```python
def test_ids_filter_is_sql_and_paginates(info, pg_session_factory):
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=1, offset=0, ids=["2", "1", "x", "99"])
        assert page.number_matched == 2  # "x" ignoré (pk entière), 99 absent
        assert [f["id"] for f in page.features] == [1]
        none = select_features(session, info, limit=10, offset=0, ids=["x"])
        assert none.number_matched == 0 and none.features == []
```

`core/tests/test_stac_search.py` : remplacer `make_repo()` par une version qui honore `ids` (les autres tests restent inchangés) :

```python
def make_repo():
    # Chaque collection a 2 features (ids 1,2). matched=2 par collection.
    def select_features(
        session, info, *, limit, offset, bbox=None, filters=None, ids=None, geom_intersects=None
    ):
        rows = [feat(1), feat(2)]
        if ids is not None:
            rows = [f for f in rows if str(f["id"]) in ids]
        page = rows[offset : offset + limit]
        return FeaturePage(features=page, number_matched=len(rows), number_returned=len(page))

    def get_feature(session, info, *, fid):
        return None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature)
```

et ajouter :

```python
def test_search_ids_filtered_before_pagination(env):
    _app, client = env
    body = client.get("/v1/stac/search?collections=roads&ids=2&limit=1").json()
    assert [f["id"] for f in body["features"]] == ["2"]
    assert not any(link["rel"] == "next" for link in body["links"])


def test_search_rejects_unknown_parameters(env):
    _app, client = env
    assert client.get("/v1/stac/search?filter=x").status_code == 400
    assert client.post("/v1/stac/search", json={"query": {}}).status_code in (400, 422)


def test_search_intersects(env):
    _app, client = env
    geom = '{"type":"Point","coordinates":[1,44]}'
    r = client.get("/v1/stac/search", params={"intersects": geom, "limit": 100})
    assert r.status_code == 200 and len(r.json()["features"]) == 4
    both = client.get("/v1/stac/search", params={"intersects": geom, "bbox": "0,0,1,1"})
    assert both.status_code == 400
    post = client.post("/v1/stac/search", json={"intersects": {"type": "Point", "coordinates": [1, 44]}})
    assert post.status_code == 200
```

(`serializers.item` sérialise `id` en `str(feature["id"])`, d'où `"2"`.)

`core/tests/test_stac_serializers.py:14` : retirer la ligne `oas30` de la liste attendue. `core/tests/test_ows_wfs.py` :

```python
def test_getfeature_resourceid(env):
    c, _login, _admin = env
    _enable(c)
    q = _kvp(request="GetFeature", resourceid="demo_ows.2", outputformat="application/json")
    body = c.get(BASE, params=q).json()
    assert [f["properties"]["nom"] for f in body["features"]] == ["bravo"]
    q2 = _kvp(request="GetFeature", resourceid="gs:demo_ows.2", bbox="0,0,1,1", outputformat="application/json")
    assert c.get(BASE, params=q2).status_code == 400
```

- [ ] **Step 2:** lancer les quatre fichiers → FAIL (`unexpected keyword argument 'ids'`, 200 au lieu de 400, `oas30`).

- [ ] **Step 3: `ids` dans le dépôt** — `features/repository.py`, signature de `_where` : ajouter `ids: list[str] | None = None,` après `cql2_srid: int = 4326,` ; en fin de fonction, juste avant le `return` :

```python
    if ids is not None:
        # AUD-043 : filtre d'identifiants EN SQL (avant pagination/comptage) ; un id
        # non convertible au type de la PK ne peut correspondre à aucune ligne.
        values = [v for v in (_coerce_fid(info, i) for i in ids) if v is not None]
        if not values:
            clauses.append("FALSE")
        else:
            keys = []
            for j, v in enumerate(values):
                params[f"__id{j}"] = v
                keys.append(f":__id{j}")
            clauses.append(f"{quote_ident(session, info.pk_column)} IN ({', '.join(keys)})")
```

`_select_features` : ajouter `ids: list[str] | None = None,` dans les kwargs (après `cql2_srid`) et `ids=ids,` dans l'appel à `_where`. Chercher par `grep -n "_where(" core/app/features/*.py` les autres appelants (comptage, agrégats, tuiles) : ils n'ont pas besoin du kwarg (défaut `None`).

- [ ] **Step 4: STAC** — `stac/routes.py` : `from pydantic import BaseModel, ConfigDict, Field` (ajouter `ConfigDict`) ; `from app.features.routes import _parse_geom_intersects` (le module importe déjà depuis `app.features.routes` : l'ajouter à cet import) ;

```python
class SearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")  # AUD-140 : champ inconnu = 422, pas ignoré

    bbox: list[float] | None = None
    intersects: dict | None = None
    datetime: str | None = None
    collections: list[str] | None = None
    ids: list[str] | None = None
    limit: int = Field(DEFAULT_LIMIT, ge=1)
    token: str | None = None


_SEARCH_PARAMS = {"bbox", "intersects", "datetime", "collections", "ids", "limit", "token"}


def _check_search(bbox, intersects, ids) -> None:
    if bbox is not None and intersects is not None:
        raise HTTPException(status_code=400, detail="bbox and intersects are mutually exclusive")
    if ids is not None and len(ids) > MAX_LIMIT:
        raise HTTPException(status_code=400, detail=f"at most {MAX_LIMIT} ids")
```

`_run_search` : nouveau kwarg `intersects` (après `bbox`) ; remplacer l'appel `repo.select_features(...)` par :

```python
        extra: dict = {}
        if ids:
            extra["ids"] = ids
        if intersects is not None:
            extra["geom_intersects"] = intersects
        with rls(session, col.tenant_id, masked=col_masked):
            page = repo.select_features(
                session, info, limit=remaining, offset=offset, bbox=bbox, filters=None, **extra
            )
```

supprimer les deux lignes `if ids and str(f["id"]) not in ids: continue`, et dans le bloc `next_token` ajouter `if intersects is not None: params["intersects"] = json.dumps(intersects)`. `search_get` : ajouter `intersects: str | None = None` aux paramètres, et en tête du corps :

```python
    unknown = set(request.query_params) - _SEARCH_PARAMS
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unsupported parameter(s): {', '.join(sorted(unknown))}"
        )
    parsed_intersects = _parse_geom_intersects(intersects)
    id_list = ids.split(",") if ids else None
    _check_search(bbox, parsed_intersects, id_list)
```

puis passer `intersects=parsed_intersects, ids=id_list` à `_run_search`. `search_post` : `_check_search(body.bbox, body.intersects, body.ids)` après le contrôle de `bbox`, et `intersects=body.intersects`. `stac/serializers.py:17` : supprimer la ligne `oas30` et ajouter au-dessus le commentaire `# Pas de conf/oas30 : document OpenAPI 3.1 (REV-364 b, AUD-043).`

- [ ] **Step 5: WFS RESOURCEID** — `ows/routes.py::_get_feature`, remplacer les trois premières lignes (`names = _type_name(q)` … `col = _readable(...)`) par :

```python
    rid = q.get("resourceid") or q.get("featureid")
    ids: list[str] | None = None
    names = _type_name(q) if (q.get("typenames") or q.get("typename")) else []
    if rid:
        if q.get("bbox") or q.get("cql_filter"):
            raise _bad("resourceId", "RESOURCEID is mutually exclusive with BBOX and CQL_FILTER")
        parsed = [r.strip().removeprefix("gs:").rpartition(".") for r in rid.split(",") if r.strip()]
        types = {p[0] for p in parsed}
        if len(types) != 1 or "" in types or any(not p[2] for p in parsed):
            raise _bad("resourceId", "RESOURCEID must be <type>.<id> on a single feature type")
        names = names or [types.pop()]
        ids = [p[2] for p in parsed]
    if len(names) != 1:
        raise _bad("typeNames", "exactly one feature type per GetFeature is supported")
    col = _readable(session, user, guest, names[0], "typeNames")
```

`_type_name` (l.75) lit `typenames`/`typename` et retire `gs:` : la condition ci-dessus s'y aligne. Après `kwargs: dict = {}` ajouter `if ids is not None: kwargs["ids"] = ids`.

- [ ] **Step 6:** `uv run pytest tests/test_stac_search.py tests/test_stac_serializers.py tests/test_stac_routes.py -v` + `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_features_repository.py tests/test_ows_wfs.py -v` → PASS. Régénérer OpenAPI + types (paramètre `intersects`, champ de `SearchBody`).

- [ ] **Step 7: Commit**

```bash
git add core/app/features/repository.py core/app/stac core/app/ows/routes.py core/tests core/openapi.json shell/src/api/generated
git commit -m "fix(core): identifiants filtrés en SQL, recherche STAC stricte avec intersects, RESOURCEID WFS (AUD-043/140)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 4: AUD-045 + AUD-127 — WMS 1.1.1, GetLegendGraphic, CRS France/outre-mer, grille NTF

**Files:**
- Modify: `core/app/ogc_crs.py:7`
- Modify: `core/app/ows/wms.py:17-21, 47-76` (`CRS_TABLE`, `LegendURL` des capacités)
- Modify: `core/app/ows/wfs.py:92-93` (`OtherCRS` générés)
- Modify: `core/app/ows/wms_routes.py:102-114, 228-310` (`_query_bbox`, version, `_common`, `_get_legend`)
- Modify: `core/app/ows/render.py` (`legend_png`)
- Modify: `core/app/ingestion/parsers.py:432-444` (`_crs_transform`, `_ntf_transform`)
- Modify: `core/Dockerfile:60` (grille PROJ dans l'image)
- Test: `core/tests/test_ows_wms.py`, Create: `core/tests/test_ingestion_ntf_grid.py`, Create: `core/tests/test_dockerfile_proj_grid.py`

**Interfaces:**
- Consumes: `_layer_ctx(session, user, guest, introspect, masked_dep, name, locator) -> (col, info, masked)`, `_resolve_style(session, user, col, name) -> Style` (`wms_routes.py`) ; `Style(geometry_kind, rules)`, `Rule(title, test, fill, fill_opacity, stroke, stroke_width, dash, radius)` (`app/styles/model.py`) ; `render._rgba(hex, alpha)`.
- Produces: `FRANCE_EPSG: tuple[int, ...]`, `SUPPORTED_EPSG` élargi (`app/ogc_crs.py`) ; `render.legend_png(style: Style) -> bytes` ; `REQUEST=GetLegendGraphic` (WMS) ; `VERSION=1.1.1` accepté (paramètre `SRS`, ordre x/y toujours) ; `parsers._ntf_transform(src: pyproj.CRS)` ; image `core` embarquant `fr_ign_gr3df97a.tif`.

**Jumelles :** `SUPPORTED_EPSG` est lu par OGC Features (`crs`, `bbox-crs`, `Content-Crs`, `collection_crs_fields`) et par WFS (`srsName`) : l'élargissement s'applique aux trois d'un coup (voulu) ; `wms.CRS_TABLE` sert WMS et le `<CRS>` des capacités ; `_query_bbox` sert GetMap **et** GetFeatureInfo ; la grille NTF concerne tout chemin pyproj d'ingestion (`_crs_transform` est l'unique point : `grep -n "Transformer.from_crs" core/app/ingestion` pour confirmer) — PostGIS/DuckDB reportés.

- [ ] **Step 1: Tests qui échouent** — `core/tests/test_ows_wms.py` : dans la liste paramétrée de `test_bad_getmap_is_service_exception`, remplacer `{"version": "1.1.1"},` par `{"version": "1.0.0"},`, puis ajouter :

```python
def test_getmap_wms_111_srs_is_xy(env):
    c, _login, _admin = env
    _enable(c)
    ref = _img(c.get(WMS, params=_map()))  # 1.3.0, EPSG:4326 lat,lon
    p = _map(version="1.1.1", bbox="0,44,4,48")  # 1.1.1 : toujours x,y (lon,lat)
    p.pop("crs")
    p["srs"] = "EPSG:4326"
    assert _img(c.get(WMS, params=p)).tobytes() == ref.tobytes()


def test_get_legend_graphic(env):
    c, _login, _admin = env
    _enable(c)
    r = c.get(WMS, params=_q(request="GetLegendGraphic", layer="demo_ows", format="image/png"))
    img = _img(r)
    assert img.getpixel((10, 10)) == FILL
    caps = c.get(WMS, params=_q(request="GetCapabilities")).text
    assert "<LegendURL" in caps and "GetLegendGraphic" in caps
    _schema("wms/1.3.0/capabilities_1_3_0.xsd").validate(caps)
    missing = c.get(WMS, params=_q(request="GetLegendGraphic"))
    assert missing.status_code == 400


@pytest.mark.parametrize("epsg", [3946, 2975])
def test_getmap_france_crs(env, epsg):
    c, _login, _admin = env
    _enable(c)
    tr = pyproj.Transformer.from_crs(4326, epsg, always_xy=True)
    lon, lat = (3.0, 45.5) if epsg == 3946 else (55.5, -21.1)
    x, y = tr.transform(lon, lat)
    r = c.get(
        WMS,
        params=_map(crs=f"EPSG:{epsg}", bbox=f"{x - 1000},{y - 1000},{x + 1000},{y + 1000}"),
    )
    assert _img(r).size == (400, 400)
```

`core/tests/test_ingestion_ntf_grid.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-127 : NTF -> WGS84 exige la grille IGN (sinon Helmert ~2 m silencieux)."""

import warnings

import pyproj
import pytest
from pyproj.transformer import TransformerGroup

from app.ingestion.parsers import IngestionParseError, _crs_transform

WITH_GRID = (2.3365241427675185, 48.85034948131713)  # (600000, 2428000) EPSG:27572


def _grid_available() -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return TransformerGroup(27572, 4171, always_xy=True).best_available


def test_lambert93_unchanged():
    lon, lat = _crs_transform("EPSG:2154")(700000.0, 6600000.0)
    assert (round(lon, 6), round(lat, 6)) == (3.0, 46.5)


@pytest.mark.skipif(_grid_available(), reason="grille installée : branche couverte ci-dessous")
def test_ntf_without_grid_is_refused():
    with pytest.raises(IngestionParseError, match="fr_ign_gr3df97a.tif"):
        _crs_transform("EPSG:27572")


@pytest.mark.skipif(not _grid_available(), reason="grille IGN absente (python -m pyproj sync)")
def test_ntf_with_grid_is_metric():
    lon, lat = _crs_transform("EPSG:27572")(600000.0, 2428000.0)
    assert lon == pytest.approx(WITH_GRID[0], abs=1e-7)
    assert lat == pytest.approx(WITH_GRID[1], abs=1e-7)
```

Pour couvrir **les deux** branches localement : lancer une fois sans grille (`ls ~/.local/share/proj` vide de `fr_ign_gr3df97a.tif`), puis `uv run python -m pyproj sync --file fr_ign_gr3df97a.tif` et relancer. Le script de CI n'installe pas la grille : la branche « refus » y tourne.

`core/tests/test_dockerfile_proj_grid.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-127 : l'image core (et donc worker) embarque la grille NTF->RGF93."""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def test_image_syncs_ntf_grid_before_chown():
    text = DOCKERFILE.read_text()
    sync = text.index("pyproj sync --file fr_ign_gr3df97a.tif")
    assert sync < text.index("chown -R app:app /opt/geostudio-home")
```

- [ ] **Step 2:** `uv run pytest tests/test_ingestion_ntf_grid.py tests/test_dockerfile_proj_grid.py -v` → FAIL ; `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_ows_wms.py -v` → FAIL (1.1.1 refusée, légende absente, `InvalidCRS`).

- [ ] **Step 3: CRS** — `core/app/ogc_crs.py:7` :

```python
# AUD-127 : Lambert-93 + coniques conformes CC42..CC50 + UTM outre-mer (Guyane RGFG95/UTM22N,
# Réunion RGR92/UTM40S, Mayotte RGM04/UTM38S, Antilles RGAF09/UTM20N).
FRANCE_EPSG = (2972, 2975, 4471, 5490, *range(3942, 3951))
SUPPORTED_EPSG = (4326, 3857, 2154, *FRANCE_EPSG)
```

`core/app/ows/wms.py` : après la définition littérale de `CRS_TABLE`, ajouter `CRS_TABLE.update({f"EPSG:{c}": (c, False) for c in FRANCE_EPSG})` et l'import `from app.ogc_crs import FRANCE_EPSG`. `core/app/ows/wfs.py` : remplacer les deux lignes `"<wfs:OtherCRS>…3857…"` / `"…2154…"` par `f"{_OTHER_CRS}"` avec, au niveau module :

```python
from app.ogc_crs import SUPPORTED_EPSG

_OTHER_CRS = "".join(
    f"<wfs:OtherCRS>urn:ogc:def:crs:EPSG::{c}</wfs:OtherCRS>" for c in SUPPORTED_EPSG if c != 4326
)
```

`wms_routes.py::_query_bbox` : `lim = {4326: (180.0, 90.0), 3857: (20037508.34, 20037508.34)}.get(srid, (1e7, 1e7))` (toutes les projections françaises ont |x|,|y| < 1e7 m).

- [ ] **Step 4: WMS 1.1.1 + légende** — `wms_endpoint`, remplacer le bloc version/opérations par :

```python
        version = q.get("version", "1.3.0")
        if version not in ("1.3.0", "1.1.1"):
            raise _err("InvalidParameterValue", "supported WMS versions: 1.3.0, 1.1.1")
        legacy = version == "1.1.1"
        if op == "getmap":
            return _get_map(q, session, user, guest, introspect, repo, rls, masked, legacy)
        if op == "getfeatureinfo":
            return _get_feature_info(
                q, session, user, guest, introspect, repo, rls, masked, legacy
            )
        if op == "getlegendgraphic":
            return _get_legend(q, session, user, guest, introspect, masked)
        raise _err(
            "OperationNotSupported" if op else "MissingParameterValue",
            "supported operations: GetCapabilities, GetMap, GetFeatureInfo, GetLegendGraphic",
        )
```

`_common(q: dict, legacy: bool = False)` : remplacer `srid, latlon = _crs(q.get("crs"))` par

```python
    if legacy:  # WMS 1.1.1 : paramètre SRS, axes toujours x,y (lon,lat en EPSG:4326)
        srid, _ = _crs(q.get("srs"))
        latlon = False
    else:
        srid, latlon = _crs(q.get("crs"))
```

`_get_map(..., masked, legacy=False)` et `_get_feature_info(..., masked_dep, legacy=False)` appellent `_common(q, legacy)`. Ajouter :

```python
def _get_legend(q, session, user, guest, introspect, masked_dep) -> Response:
    """GetLegendGraphic (AUD-045) : même porte de lecture et même résolution de style
    que GetMap ; aucune donnée lue (la légende ne dépend que du style)."""
    name = (q.get("layer") or "").strip()
    if not name:
        raise _err("MissingParameterValue", "LAYER is required")
    if q.get("format", "image/png").lower() not in wms.GETMAP_FORMATS:
        raise _err("InvalidFormat", "FORMAT must be image/png")
    col, _info, _masked = _layer_ctx(session, user, guest, introspect, masked_dep, name, "LAYER")
    style = _resolve_style(session, user, col, q.get("style", ""))
    return Response(render.legend_png(style), media_type="image/png")
```

`core/app/ows/render.py` (ajouter `from app.styles.model import Style` à l'import existant de `Rule, Style, select_rule` si besoin) :

```python
LEGEND_ROW = 20
LEGEND_WIDTH = 200
LEGEND_MAX_ROWS = 100


def legend_png(style: Style) -> bytes:
    """Une ligne de 20 px par règle : pastille selon la géométrie + titre (AUD-045)."""
    rules = style.rules[:LEGEND_MAX_ROWS]
    img = Image.new("RGBA", (LEGEND_WIDTH, LEGEND_ROW * max(len(rules), 1)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, rule in enumerate(rules):
        y = i * LEGEND_ROW
        fill = _rgba(rule.fill, rule.fill_opacity)
        if style.geometry_kind == "point":
            draw.ellipse((4, y + 4, 16, y + 16), fill=fill)
        elif style.geometry_kind == "line":
            draw.line((2, y + 10, 18, y + 10), fill=fill, width=max(int(rule.stroke_width), 1))
        else:
            draw.rectangle((2, y + 3, 18, y + 17), fill=fill)
        # police bitmap par défaut de Pillow : latin-1 seulement
        label = rule.title.encode("latin-1", "replace").decode("latin-1")
        draw.text((24, y + 4), label, fill=(0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
```

`wms.wms_capabilities` : remplacer `"<Style><Name>default</Name><Title>default</Title></Style></Layer>"` par :

```python
        "<Style><Name>default</Name><Title>default</Title>"
        f'<LegendURL width="{LEGEND_WIDTH}" height="{LEGEND_ROW}"><Format>image/png</Format>'
        f'<OnlineResource xlink:type="simple" xlink:href='
        f"{_a(f'{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&LAYER={c.id}&FORMAT=image/png')}"
        "/></LegendURL></Style></Layer>"
```

avec `from app.ows.render import LEGEND_ROW, LEGEND_WIDTH` en tête de `wms.py` (vérifier par `uv run lint-imports` que `render` n'importe pas `wms` : sinon déplacer les deux constantes dans `wms.py` et les importer depuis `render`). `_a` échappe `&` en `&amp;` (quoteattr) : le XML reste valide.

- [ ] **Step 5: Grille NTF** — `core/app/ingestion/parsers.py`, ajouter `from pyproj.transformer import TransformerGroup` aux imports, puis remplacer `_crs_transform` par :

```python
_NTF_GEODETIC = {4275, 4807}  # NTF, NTF (Paris)


def _ntf_transform(src: pyproj.CRS):
    """AUD-127 : NTF -> RGF93 exige la grille IGN fr_ign_gr3df97a.tif. Sans elle, PROJ
    retombe en silence sur un Helmert (~2 m vers 4326) ou un « ballpark » (vers 4171) :
    on exige la grille vers RGF93 v1 (EPSG:4171), puis RGF93 -> WGS84."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pyproj avertit quand une grille manque
        group = TransformerGroup(src, 4171, always_xy=True)
    if not group.best_available or not group.transformers:
        raise IngestionParseError(
            "Données en NTF : grille IGN fr_ign_gr3df97a.tif absente de l'installation PROJ, "
            "transformation métrique impossible (python -m pyproj sync --file fr_ign_gr3df97a.tif)"
        )
    to_rgf93 = group.transformers[0]
    to_wgs84 = pyproj.Transformer.from_crs(4171, _WGS84, always_xy=True)

    def transform(x, y, z=None):
        lon, lat = to_rgf93.transform(x, y)
        return to_wgs84.transform(lon, lat)

    return transform


def _crs_transform(crs: str | None):
    try:
        src = pyproj.CRS.from_user_input(crs)
    except ProjError as exc:
        raise IngestionParseError(f"CRS manquant ou non reconnu : {crs!r}") from exc
    if src == _WGS84:
        return None
    geodetic = src.geodetic_crs
    if geodetic is not None and geodetic.to_epsg() in _NTF_GEODETIC:
        return _ntf_transform(src)
    try:
        transformer = pyproj.Transformer.from_crs(src, _WGS84, always_xy=True)
    except ProjError as exc:
        raise IngestionParseError(f"CRS non transformable vers WGS84 : {crs!r}") from exc
    return transformer.transform
```

(`transform(x, y, z=None)` rend du 2D : l'import force déjà le 2D, REV-349.)

`core/Dockerfile`, juste après la ligne `RUN python -c "import duckdb; …"` (l.60) :

```dockerfile
# AUD-127 : grille IGN NTF -> RGF93 (fr_ign_gr3df97a.tif, cdn.proj.org) dans le répertoire
# utilisateur PROJ de HOME (=/opt/geostudio-home/.local/share/proj, lu par pyproj à
# l'exécution) ; sans elle, l'ingestion d'un fichier NTF est refusée (parsers._ntf_transform).
RUN python -m pyproj sync --file fr_ign_gr3df97a.tif
```

- [ ] **Step 6:** `uv run pytest tests/test_ingestion_ntf_grid.py tests/test_dockerfile_proj_grid.py tests/test_ingestion_parsers.py -v` (les deux branches : sans puis avec grille, cf. Step 1) ; `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_ows_wms.py tests/test_ows_wfs.py tests/test_features_crs_storage_postgis.py -v` → PASS. `grep -rn "EPSG/0/2154\|SUPPORTED_EPSG\|OtherCRS" core/tests` : mettre à jour toute liste attendue exacte de CRS (ex. `collection_crs_fields`). Vérification image (si Docker disponible) : `docker build -t gs-core-l6 core && docker run --rm gs-core-l6 python -c "from pyproj.transformer import TransformerGroup as G; print(G(27572, 4171, always_xy=True).best_available)"` → `True`. Régénérer OpenAPI (diff vide attendu : WMS derrière flag).

- [ ] **Step 7: Commit**

```bash
git add core/app/ogc_crs.py core/app/ows core/app/ingestion/parsers.py core/Dockerfile core/tests
git commit -m "feat(core): WMS 1.1.1 et GetLegendGraphic, CRS France et outre-mer, grille NTF exigée (AUD-045/127)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: AUD-046 — contrat OpenAPI (version, description, sécurité, tags)

**Files:**
- Modify: `core/app/main.py:184`
- Create: `core/tests/test_openapi_contract.py`

**Interfaces:**
- Consumes: `fastapi.openapi.utils.get_openapi`.
- Produces: `_core_version() -> str`, `API_DESCRIPTION: str`, `_tag_for(path: str) -> str` (`app/main.py`) ; `/openapi.json` avec `info.version` = `pyproject.toml`, `info.description`, `components.securitySchemes.bearerAuth`, `security`, un tag sur chaque opération.

**Jumelles :** `GET /v1/auth/me` renvoie `version=request.app.version` (même source → reste cohérent) ; `scripts/export_openapi.py` appelle `app.openapi()` (passe par la surcharge — vérifier par `grep -n "openapi" core/scripts/export_openapi.py`) ; le shell lit `version` du profil (aucune valeur figée côté shell : `grep -rn '"0.1.0"' shell/src --include=*.ts* | grep -v test`).

- [ ] **Step 1: Test qui échoue** — `core/tests/test_openapi_contract.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-046 : le document OpenAPI est un contrat lisible (version réelle, auth, tags)."""

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_openapi_contract():
    schema = TestClient(create_app()).get("/openapi.json").json()
    assert schema["info"]["version"] == tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert "Authentification" in schema["info"]["description"]
    bearer = schema["components"]["securitySchemes"]["bearerAuth"]
    assert (bearer["type"], bearer["scheme"]) == ("http", "bearer")
    assert {"bearerAuth": []} in schema["security"]
    untagged = [
        f"{method.upper()} {path}"
        for path, ops in schema["paths"].items()
        for method, op in ops.items()
        if isinstance(op, dict) and not op.get("tags")
    ]
    assert untagged == []
```

- [ ] **Step 2:** `uv run pytest tests/test_openapi_contract.py -v` → FAIL (`description` absente).

- [ ] **Step 3: Implémenter** — `core/app/main.py`, au niveau module (imports `tomllib`, `from pathlib import Path`, `from fastapi.openapi.utils import get_openapi` ajoutés s'ils manquent) :

```python
def _core_version() -> str:
    """Version unique = pyproject.toml (copié en /app dans l'image). importlib.metadata
    ne marche pas : le projet n'est pas installé comme paquet (uv --no-emit-project)."""
    try:
        path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        return tomllib.loads(path.read_text())["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


API_DESCRIPTION = """\
API du cœur GeoStudio (Apache-2.0).

## Authentification
Jeton `Authorization: Bearer <jeton>` : un jeton OIDC émis par Keycloak, ou une clé
d'API de service `gsk_…` (ADR 0016). Les routes de lecture publiques (catalogue public,
OGC API, STAC, DCAT, Records) acceptent aussi un appel anonyme ; elles ne servent alors
que le contenu public.

## Conventions
- Toutes les routes métier sont sous `/v1` ; `/health` et `/mcp` sont hors version.
- Pagination : `limit`/`offset` (ou `page`/`pageSize` sur le catalogue), liens `next`/`prev`.
- Erreurs au format RFC 7807 (`application/problem+json`).
- Concurrence optimiste : `If-Match` sur les écritures de configuration et d'entités.

## Standards ouverts
OGC API Features (Parts 1-4) sous `/v1/collections`, OGC API Records sous `/v1/records`,
STAC sous `/v1/stac`, DCAT-AP sous `/v1/dcat`, WFS/WMS/WMTS et OGC API Tiles sous `/v1/ows`
quand l'instance les active.
"""


def _tag_for(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "v1":
        parts = parts[1:]
    return parts[0] if parts and not parts[0].startswith("{") else "racine"
```

dans `create_app`, remplacer `app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)` par :

```python
    app = FastAPI(
        title="GeoStudio Builder Service",
        version=_core_version(),
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )

    def _openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT OIDC ou clé d'API gsk_",
        }
        schema["security"] = [{"bearerAuth": []}, {}]  # {} = appel anonyme admis (routes publiques)
        for path, ops in schema.get("paths", {}).items():
            for op in ops.values():
                if isinstance(op, dict) and not op.get("tags"):
                    op["tags"] = [_tag_for(path)]
        app.openapi_schema = schema
        return schema

    app.openapi = _openapi  # type: ignore[method-assign]
```

- [ ] **Step 4:** `uv run pytest tests/test_openapi_contract.py tests/test_export_openapi.py tests/test_auth_me_capabilities.py -v` → PASS. Régénérer OpenAPI + types TS (diff important attendu : tags/description, aucun type modifié côté `core-schema.d.ts` hors commentaires) ; `npm run build` → OK.

- [ ] **Step 5: Commit**

```bash
git add core/app/main.py core/tests/test_openapi_contract.py core/openapi.json shell/src/api/generated
git commit -m "feat(core): contrat OpenAPI versionné, documenté, sécurité Bearer et tags (AUD-046)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: AUD-047 (partiel) + AUD-140 (DCAT) — mots-clés et thème INSPIRE, DCAT enrichi, pagination hydra

**Files:**
- Create: `core/alembic/versions/0095_collection_keywords_inspire.py`
- Create: `core/tests/test_migration_0095_collection_keywords.py`
- Modify: `core/app/collections/models.py:93` (deux colonnes)
- Modify: `core/app/collections/schemas.py:136-158` (`CollectionPatch`)
- Modify: `core/app/collections/routes.py:310-330, 898-930` (`_collection_json`, PATCH)
- Modify: `core/app/catalog/metadata.py` (thèmes INSPIRE, ISO 639-2/B), `core/app/catalog/schemas.py`, `core/app/catalog/routes.py`
- Modify: `core/app/dcat/serializers.py` (`CONTEXT`, `distribution`, `dataset`), `core/app/dcat/routes.py` (`_dataset_doc`, `get_catalog`)
- Test: `core/tests/test_dcat_serializers.py:12`, `core/tests/test_dcat_routes.py`, `core/tests/test_catalog_metadata.py`
- Modify: `shell/src/api/types.ts:102-106, 1478+` + type `CollectionAdmin`, `shell/src/shell/EditCollectionPanel.tsx`, `shell/src/i18n/domains/admin.ts`, `shell/src/shell/EditCollectionPanel.test.tsx`, `shell/src/test/msw/handlers.ts` (`/metadata-catalog`)

**Interfaces:**
- Consumes: `resolve_license`, `resolve_language` (`app/catalog/metadata.py`).
- Produces: colonnes `collections.keywords` (JSON, `[]`) et `collections.inspire_theme` (String, `""`) ; `CollectionPatch.keywords: list[str] | None`, `CollectionPatch.inspireTheme: str | None` ; JSON collection `keywords`, `inspireTheme` ; `InspireTheme(id, label, iso_category)` + propriété `uri`, `INSPIRE_THEMES`, `resolve_inspire_theme(theme_id) -> InspireTheme | None`, `validate_inspire_theme_id(value) -> str | None`, `ISO639_2B: dict[str, str]` ; `MetadataCatalog.inspireThemes: list[InspireThemeCatalogEntry(id, label, uri)]` ; `serializers.dataset(..., keywords=None, inspire_theme="")`, `serializers.distribution(..., conforms_to=None)`. **T7 consomme `INSPIRE_THEMES`, `resolve_inspire_theme`, `ISO639_2B`, `Collection.keywords`, `Collection.inspire_theme`.**

**Jumelles :** `_collection_json` sert liste, détail **et** l'outil MCP de collections (`grep -rn "_collection_json" core/app`) ; `CollectionPatch` n'est consommé que par `PATCH /collections/{id}` (`collections/routes.py:818`, vérifié) : un seul point d'écriture ; STAC `serializers.collection` n'émet pas de `keywords` aujourd'hui : **jumelle notée**, à brancher sur `col.keywords` en suivi (hors critère d'AUD-047, qui vise DCAT/ISO).

- [ ] **Step 1: Migration + test** — `core/alembic/versions/0095_collection_keywords_inspire.py` (fixer `down_revision` à la sortie de `cd core && uv run alembic heads` ; **si plusieurs têtes sont listées, s'arrêter et signaler au contrôleur** — lots parallèles non fusionnés) :

```python
# SPDX-License-Identifier: Apache-2.0
"""collections.keywords + collections.inspire_theme (AUD-047).

Revision ID: 0095
Revises: <tête actuelle, sortie de `alembic heads`>
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0095"
down_revision = "<tête actuelle>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections", sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "collections",
        sa.Column("inspire_theme", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("collections", "inspire_theme")
    op.drop_column("collections", "keywords")
```

`core/tests/test_migration_0095_collection_keywords.py` — reprendre **à l'identique** la fixture `throwaway_database_url` de `core/tests/test_migration_0082_pipeline_heartbeat.py` (préfixe de base `kw_` au lieu de `heartbeat_`), puis :

```python
@pytest.mark.postgis
def test_0095_columns_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_rev = ScriptDirectory.from_config(cfg).get_revision("0095").down_revision
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, previous_rev)
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1', 't1', 'T', now())"
            ))
            conn.execute(sa.text(
                "INSERT INTO roles (id, tenant_id, name, slug, privileges, created_at, "
                "updated_at) VALUES ('ro1', 't1', 'R', 'r', '[]', now(), now())"
            ))
            conn.execute(sa.text(
                "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, last_name, "
                "is_admin, role_id, created_at, updated_at) "
                "VALUES ('u1', 't1', 'u', 'u', '', '', false, 'ro1', now(), now())"
            ))
            conn.execute(sa.text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "pk_column, created_at, updated_at) "
                "VALUES ('c1', 't1', 'u1', 'c1', 'C', 'id', now(), now())"
            ))
        cols = lambda: {c["name"] for c in sa.inspect(engine).get_columns("collections")}  # noqa: E731
        assert {"keywords", "inspire_theme"}.isdisjoint(cols())
        command.upgrade(cfg, "0095")
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT keywords, inspire_theme FROM collections")).one()
        assert (row[0], row[1]) == ([], "")
        command.downgrade(cfg, previous_rev)
        assert {"keywords", "inspire_theme"}.isdisjoint(cols())
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM collections")).scalar() == 1
        command.upgrade(cfg, "0095")
        assert {"keywords", "inspire_theme"} <= cols()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
```

(imports : ceux du test 0082 + `from alembic.script import ScriptDirectory`.) Lancer `CORE_TEST_DATABASE_URL=… uv run pytest tests/test_migration_0095_collection_keywords.py -v` → FAIL avant la migration, PASS après.

- [ ] **Step 2: Modèle** — `core/app/collections/models.py`, après `temporal_end` :

```python
    # AUD-047 : mots-clés libres + thème INSPIRE (code, cf. app.catalog.metadata.INSPIRE_THEMES).
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False, server_default="[]")
    inspire_theme: Mapped[str] = mapped_column(
        String, default="", server_default="", nullable=False
    )
```

`CORE_TEST_DATABASE_URL=… uv run pytest tests/test_model_alembic_parity.py -v` → PASS (après la migration du Step 1).

- [ ] **Step 3: Tests qui échouent (catalogue, PATCH, DCAT)** — `core/tests/test_catalog_metadata.py` :

```python
from app.catalog.metadata import INSPIRE_THEMES, resolve_inspire_theme, validate_inspire_theme_id


def test_inspire_themes_are_the_34_annex_themes():
    assert len(INSPIRE_THEMES) == 34
    assert len({t.id for t in INSPIRE_THEMES}) == 34
    hy = resolve_inspire_theme("hy")
    assert (hy.label, hy.iso_category, hy.uri) == (
        "Hydrographie", "inlandWaters", "http://inspire.ec.europa.eu/theme/hy"
    )
    assert validate_inspire_theme_id("") == ""
    with pytest.raises(ValueError):
        validate_inspire_theme_id("zz")
```

Dans `core/tests/test_dcat_routes.py` (fixture `env` → `(app, client, admin, regular, Session)`, helpers `_register`/`_as` du fichier) :

```python
def test_dataset_carries_keywords_theme_and_conformance(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin)
    _as(app, admin)
    r = client.patch(
        "/v1/collections/incidents",
        json={"keywords": ["voirie", "réseau", "voirie"], "inspireTheme": "tn"},
    )
    assert r.status_code == 200
    assert (r.json()["keywords"], r.json()["inspireTheme"]) == (["voirie", "réseau"], "tn")
    assert client.patch("/v1/collections/incidents", json={"inspireTheme": "zz"}).status_code == 422
    doc = client.get("/v1/dcat/datasets/incidents").json()
    assert doc["dcat:keyword"] == ["voirie", "réseau"]
    assert doc["dcat:theme"] == {"@id": "http://inspire.ec.europa.eu/theme/tn"}
    geojson = doc["dcat:distribution"][0]
    assert geojson["dct:conformsTo"] == {"@id": "http://www.opengis.net/doc/IS/ogcapi-features-1/1.0"}
```

et compléter `test_dcat_catalog_is_paginated` (après la première lecture `body`) :

```python
    assert body["@context"]["hydra"] == "http://www.w3.org/ns/hydra/core#"
    assert body["hydra:view"]["@type"] == "hydra:PartialCollectionView"
    assert "offset=2" in body["hydra:view"]["hydra:next"]
    assert body["hydra:totalItems"] == 3
```

(et après `body2` : `assert "hydra:next" not in body2["hydra:view"] and "offset=0" in body2["hydra:view"]["hydra:previous"]`.) `core/tests/test_dcat_serializers.py:12` : ajouter `"hydra": "http://www.w3.org/ns/hydra/core#"` au dictionnaire `CONTEXT` attendu.

Lancer → FAIL.

- [ ] **Step 4: Catalogue INSPIRE** — `core/app/catalog/metadata.py`, en fin de module :

```python
@dataclass(frozen=True)
class InspireTheme:
    id: str
    label: str
    iso_category: str  # MD_TopicCategoryCode (ISO 19115) associé

    @property
    def uri(self) -> str:
        return f"http://inspire.ec.europa.eu/theme/{self.id}"


# Les 34 thèmes des annexes I-III de la directive INSPIRE (registre inspire.ec.europa.eu).
INSPIRE_THEMES: list[InspireTheme] = [
    InspireTheme("ad", "Adresses", "location"),
    InspireTheme("au", "Unités administratives", "boundaries"),
    InspireTheme("cp", "Parcelles cadastrales", "planningCadastre"),
    InspireTheme("gg", "Systèmes de maillage géographique", "location"),
    InspireTheme("gn", "Dénominations géographiques", "location"),
    InspireTheme("hy", "Hydrographie", "inlandWaters"),
    InspireTheme("ps", "Sites protégés", "environment"),
    InspireTheme("rs", "Référentiels de coordonnées", "location"),
    InspireTheme("tn", "Réseaux de transport", "transportation"),
    InspireTheme("el", "Altitude", "elevation"),
    InspireTheme("ge", "Géologie", "geoscientificInformation"),
    InspireTheme("lc", "Occupation des terres", "imageryBaseMapsEarthCover"),
    InspireTheme("oi", "Ortho-imagerie", "imageryBaseMapsEarthCover"),
    InspireTheme("af", "Installations agricoles et aquacoles", "farming"),
    InspireTheme(
        "am",
        "Zones de gestion, de restriction ou de réglementation et unités de déclaration",
        "planningCadastre",
    ),
    InspireTheme("ac", "Conditions atmosphériques", "climatologyMeteorologyAtmosphere"),
    InspireTheme("br", "Régions biogéographiques", "biota"),
    InspireTheme("bu", "Bâtiments", "structure"),
    InspireTheme("er", "Sources d'énergie", "economy"),
    InspireTheme("ef", "Installations de suivi environnemental", "structure"),
    InspireTheme("hb", "Habitats et biotopes", "biota"),
    InspireTheme("hh", "Santé et sécurité des personnes", "health"),
    InspireTheme("lu", "Usage des sols", "planningCadastre"),
    InspireTheme(
        "mf", "Caractéristiques géographiques météorologiques", "climatologyMeteorologyAtmosphere"
    ),
    InspireTheme("mr", "Ressources minérales", "economy"),
    InspireTheme("nz", "Zones à risque naturel", "geoscientificInformation"),
    InspireTheme("of", "Caractéristiques géographiques océanographiques", "oceans"),
    InspireTheme("pd", "Répartition de la population — démographie", "society"),
    InspireTheme("pf", "Lieux de production et sites industriels", "structure"),
    InspireTheme("sr", "Régions maritimes", "oceans"),
    InspireTheme("so", "Sols", "geoscientificInformation"),
    InspireTheme("sd", "Répartition des espèces", "biota"),
    InspireTheme("su", "Unités statistiques", "boundaries"),
    InspireTheme("us", "Services d'utilité publique et services publics", "utilitiesCommunication"),
]

INSPIRE_THEME_IDS: frozenset[str] = frozenset(t.id for t in INSPIRE_THEMES)
_INSPIRE_BY_ID: dict[str, InspireTheme] = {t.id: t for t in INSPIRE_THEMES}


def resolve_inspire_theme(theme_id: str) -> InspireTheme | None:
    return _INSPIRE_BY_ID.get(theme_id)


def validate_inspire_theme_id(value: str | None) -> str | None:
    if value is not None and value != "" and value not in INSPIRE_THEME_IDS:
        raise ValueError(f"unknown INSPIRE theme id: {value!r}")
    return value


# ISO 639-2/B (gmd:LanguageCode des fiches ISO 19139 INSPIRE) — clés = LANGUAGE_IDS.
ISO639_2B: dict[str, str] = {"fr": "fre", "en": "eng", "de": "ger", "es": "spa", "it": "ita"}
```

`core/app/catalog/schemas.py` :

```python
class InspireThemeCatalogEntry(BaseModel):
    id: str
    label: str
    uri: str
```

et `inspireThemes: list[InspireThemeCatalogEntry] = []` dans `MetadataCatalog`. `core/app/catalog/routes.py` : importer `InspireThemeCatalogEntry`, ajouter à `MetadataCatalog(...)` :

```python
        inspireThemes=[
            InspireThemeCatalogEntry(id=e.id, label=e.label, uri=e.uri)
            for e in metadata.INSPIRE_THEMES
        ],
```

- [ ] **Step 5: PATCH + JSON de collection** — `core/app/collections/schemas.py` : importer `validate_inspire_theme_id` avec les autres validateurs du catalogue, ajouter à `CollectionPatch` (après `temporalEnd`) :

```python
    keywords: list[str] | None = Field(default=None, max_length=50)
    inspireTheme: str | None = None

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [k.strip() for k in v]
        if any(not k or len(k) > 100 for k in cleaned):
            raise ValueError("keywords must be non-empty strings of at most 100 characters")
        return list(dict.fromkeys(cleaned))  # dédoublonné, ordre conservé

    @field_validator("inspireTheme")
    @classmethod
    def _validate_inspire_theme(cls, v: str | None) -> str | None:
        return validate_inspire_theme_id(v)
```

`core/app/collections/routes.py` : dans la boucle `for attr, value in (...)` ajouter `("inspire_theme", body.inspireTheme),` ; après le bloc `temporalEnd` ajouter `if body.keywords is not None: col.keywords = body.keywords` (sur deux lignes) ; dans `_collection_json`, après `"temporalEnd"` : `"keywords": list(col.keywords or []),` et `"inspireTheme": col.inspire_theme,`.

- [ ] **Step 6: DCAT** — `core/app/dcat/serializers.py` : `CONTEXT` reçoit `"hydra": "http://www.w3.org/ns/hydra/core#",` ; `distribution(..., conforms_to: str | None = None)` ajoute `if conforms_to: doc["dct:conformsTo"] = {"@id": conforms_to}` ; `dataset(..., keywords: list[str] | None = None, inspire_theme: str = "")` (importer `resolve_inspire_theme`), la distribution GeoJSON reçoit `conforms_to="http://www.opengis.net/doc/IS/ogcapi-features-1/1.0"`, et avant `return doc` :

```python
    if keywords:
        doc["dcat:keyword"] = list(keywords)
    theme = resolve_inspire_theme(inspire_theme) if inspire_theme else None
    if theme is not None:
        doc["dcat:theme"] = {"@id": theme.uri}
```

`core/app/dcat/routes.py::_dataset_doc` : passer `keywords=col.keywords, inspire_theme=col.inspire_theme`. `get_catalog` : remplacer le bloc `if offset + len(cols_page) < total:` par :

```python
    view: dict = {"@id": str(request.url), "@type": "hydra:PartialCollectionView"}
    if offset + len(cols_page) < total:
        next_href = str(request.url.include_query_params(limit=limit, offset=offset + limit))
        view["hydra:next"] = next_href
        doc["links"] = [{"rel": "next", "href": next_href}]
    if offset > 0:
        view["hydra:previous"] = str(
            request.url.include_query_params(limit=limit, offset=max(offset - limit, 0))
        )
    doc["hydra:view"] = view
    doc["hydra:totalItems"] = total
```

Lancer `uv run pytest tests/test_catalog_metadata.py tests/test_dcat_serializers.py tests/test_dcat_routes.py tests/test_dcat_integration.py tests/test_collections_routes.py -v` (`test_dcat_serializers.py`/`test_dcat_integration.py` valident le JSON-LD par pyshacl) → PASS.

- [ ] **Step 7: Shell** — `shell/src/api/types.ts` : `MetadataCatalog` reçoit `inspireThemes?: { id: string; label: string; uri: string }[];` ; `CollectionAdmin` reçoit `keywords?: string[];` et `inspireTheme?: string;` ; `CollectionPatchInput` reçoit `keywords?: string[];` et `inspireTheme?: string;` (optionnels : les fixtures existantes restent valides). `shell/src/i18n/domains/admin.ts` (près de `editCollection.versionLabel`) :

```ts
  "editCollection.keywordsLabel": "Mots-clés (séparés par des virgules)",
  "editCollection.inspireThemeLabel": "Thème INSPIRE",
  "editCollection.noInspireThemeOption": "Aucun",
```

`shell/src/shell/EditCollectionPanel.tsx` : états

```tsx
  const [keywords, setKeywords] = useState((collection.keywords ?? []).join(", "));
  const [inspireTheme, setInspireTheme] = useState(collection.inspireTheme || UNSET);
```

options

```tsx
  const inspireOptions = [
    { value: UNSET, label: t("editCollection.noInspireThemeOption") },
    ...(catalogQuery.data?.inspireThemes?.map((th) => ({ value: th.id, label: th.label })) ?? []),
  ];
```

dans `mutateAsync({...})`, après `version,` :

```tsx
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        inspireTheme: inspireTheme === UNSET ? "" : inspireTheme,
```

et dans l'onglet « Métadonnées ouvertes », juste après le `<label>` de la version :

```tsx
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    {t("editCollection.keywordsLabel")}
                    <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-ink">
                    {t("editCollection.inspireThemeLabel")}
                    <Select
                      aria-label={t("editCollection.inspireThemeLabel")}
                      value={inspireTheme}
                      onValueChange={setInspireTheme}
                      options={inspireOptions}
                    />
                  </label>
```

Test dans `shell/src/shell/EditCollectionPanel.test.tsx` : ajouter `inspireThemes: [{ id: "hy", label: "Hydrographie", uri: "http://inspire.ec.europa.eu/theme/hy" }],` aux données de `mockUseMetadataCatalog` du `beforeEach`, puis, dans le `describe` de l'onglet « Métadonnées ouvertes » :

```tsx
  it("envoie les mots-clés et le thème INSPIRE", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseUpdateCollection.mockReturnValue({ mutateAsync, isPending: false, isError: false });
    render(<EditCollectionPanel collection={baseCollection} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Métadonnées ouvertes" }));
    await userEvent.type(
      screen.getByLabelText("Mots-clés (séparés par des virgules)"),
      "eau, rivière ,",
    );
    await userEvent.click(screen.getByRole("combobox", { name: "Thème INSPIRE" }));
    await userEvent.click(await screen.findByRole("option", { name: "Hydrographie" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ keywords: ["eau", "rivière"], inspireTheme: "hy" }),
    );
  });
```

Le handler MSW `/metadata-catalog` de `shell/src/test/msw/handlers.ts` reçoit `inspireThemes: []`. `npx vitest run src/shell/EditCollectionPanel.test.tsx` → PASS ; `npm run lint` (détecteur i18n) → OK.

- [ ] **Step 8:** Régénérer OpenAPI + types TS ; `uv run pytest` complet (postgis) ; `npm run test && npm run build`.

- [ ] **Step 9: Commit**

```bash
git add core/alembic/versions/0095_collection_keywords_inspire.py core/app/collections core/app/catalog \
  core/app/dcat core/tests core/openapi.json shell/src
git commit -m "feat(core): mots-clés et thème INSPIRE des collections, DCAT-AP enrichi et paginé hydra (AUD-047/140)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 7: AUD-048 + AUD-047 (ISO) — OGC API Records et fiche ISO 19139 par collection

**Files:**
- Create: `core/app/records/__init__.py` (vide, en-tête SPDX), `core/app/records/serializers.py`, `core/app/records/iso19139.py`, `core/app/records/routes.py`
- Modify: `core/app/items/repository.py:427-500, 653-700` (`_bbox_clause` extrait, `list_published_items(q=, bbox=)`)
- Modify: `core/app/main.py` (inclusion de `records_routes.router` et `records_routes.metadata_router` dans `v1_router`)
- Modify: `core/app/collections/routes.py` (`_ogc_links` : lien `describedby`)
- Modify: `core/pyproject.toml:389` (contrat de couches : `"app.records"` entre `"app.notifications"` et `"app.dcat"`)
- Create: `core/tests/test_records_routes.py`, `core/tests/test_records_iso19139.py`

**Interfaces:**
- Consumes: `list_items(session, *, tenant_id, current_user_id, q, resource_type, scope, page, page_size, …, bbox) -> ItemPage` ; `list_published_items(session, *, tenant_id=…, resource_type, tag, page, page_size)` ; `get_published_item(session, *, item_id, tenant_id) -> ItemRead | None` ; `get_item_service(session, *, item_id, user) -> ItemRead` (`app/items/service.py:54`, 404 sinon) ; `ItemRead` (`pk, resourceType, title, abstract, date, updatedAt, keywords, license, language, contentStatus, bbox`) ; `resolve_license(id).spdx_id` ; T6 : `Collection.keywords`, `Collection.inspire_theme`, `resolve_inspire_theme`, `ISO639_2B` ; DCAT : `get_bbox_provider`, `_resolve_bbox_degrading(session, col, *, introspect, bbox_provider, rls)`, `_resolve_tenant(session, user)` (`app/dcat/routes.py`) ; `get_readable_collection`, `get_introspector` ; `get_rls_scope` ; `parse_bbox_floats` (`app/bbox.py`).
- Produces: `GET /v1/records`, `/v1/records/conformance`, `/v1/records/collections`, `/v1/records/collections/catalog`, `/v1/records/collections/catalog/items`, `/v1/records/collections/catalog/items/{record_id}` ; `GET /v1/collections/{collection_id}/metadata` (XML ISO 19139) ; `records.serializers.record(*, base, item) -> dict` ; `records.iso19139.collection_metadata(*, col, bbox, srid, items_url, publisher) -> str` ; `items.repository._bbox_clause(bbox)`.

**Jumelles :** anonyme (`list_published_items` / `get_published_item`) **et** authentifié (`list_items` / `get_item_service`) — même `can()` que le catalogue ; le détail anonyme filtre `deprecated` comme la liste (la route `/v1/public/items/{id}` garde son comportement : divergence consignée, cf. faits vérifiés n°11) ; ISO 19139 et DCAT partagent `_resolve_bbox_degrading` (collection cassée ⇒ fiche sans emprise, pas 500) ; `_ogc_links` sert liste et détail OGC (T2).

- [ ] **Step 1: Tests qui échouent** — `core/tests/test_records_routes.py` (fixture recopiée de `tests/test_public_items_list.py`, client authentifié + bascule anonyme) :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-048 : OGC API Records Part 1 sur le catalogue d'items, même can() que /items."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

RECORDS = "/v1/records/collections/catalog/items"


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    c = TestClient(app)
    c.anonymous = lambda: app.dependency_overrides.__setitem__(  # type: ignore[attr-defined]
        get_current_user_optional, lambda: None
    )
    yield c
    engine.dispose()


def _create(client, title, kind="app"):
    r = client.post(
        "/v1/configs",
        json={"title": title, "config": {"kind": kind, "layout": {"type": "grid", "items": []}}},
    )
    assert r.status_code == 201, r.text
    return r.json()["itemId"]


def _publish(client, item_id):
    assert client.patch(f"/v1/items/{item_id}", json={"isPublished": True}).status_code == 200


def test_landing_conformance_and_catalog(client):
    links = {link["rel"] for link in client.get("/v1/records").json()["links"]}
    assert {"self", "conformance", "data"} <= links
    conf = client.get("/v1/records/conformance").json()["conformsTo"]
    assert "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/record-core" in conf
    cat = client.get("/v1/records/collections/catalog").json()
    assert (cat["id"], cat["type"], cat["itemType"]) == ("catalog", "Collection", "record")
    assert client.get("/v1/records/collections/nope").status_code == 404


def test_authenticated_sees_own_unpublished_anonymous_only_published(client):
    pub = _create(client, "Carte publiée des rivières")
    _publish(client, pub)
    _create(client, "Brouillon privé")
    r = client.get(RECORDS)
    assert r.headers["content-type"].startswith("application/geo+json")
    assert {f["properties"]["title"] for f in r.json()["features"]} == {
        "Carte publiée des rivières", "Brouillon privé",
    }
    client.anonymous()
    body = client.get(RECORDS, params={"q": "rivières"}).json()
    assert [f["id"] for f in body["features"]] == [pub]
    rec = body["features"][0]
    assert rec["type"] == "Feature" and rec["properties"]["type"] == "app"
    assert rec["conformsTo"] == ["http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/record-core"]
    assert client.get(f"{RECORDS}/{pub}").json()["id"] == pub
    assert client.get(RECORDS, params={"q": "Brouillon"}).json()["features"] == []


def test_unpublished_record_is_404_for_anonymous(client):
    draft = _create(client, "Brouillon")
    client.anonymous()
    assert client.get(f"{RECORDS}/{draft}").status_code == 404


def test_paging_links(client):
    for i in range(3):
        _publish(client, _create(client, f"Item {i}"))
    body = client.get(RECORDS, params={"limit": 2}).json()
    assert body["numberMatched"] == 3 and body["numberReturned"] == 2
    nxt = next(link["href"] for link in body["links"] if link["rel"] == "next")
    assert "page=2" in nxt
```

`core/tests/test_records_iso19139.py` (réutilise l'environnement sqlite de `tests/test_ogc_discovery.py`) :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-047 : fiche ISO 19139 par collection (bien formée, contenu INSPIRE minimal)."""

import xml.etree.ElementTree as ET

from app.dcat import routes as dcat_routes
from tests.test_ogc_discovery import _as, _register, env  # noqa: F401  (fixture)

NS = {"gmd": "http://www.isotc211.org/2005/gmd", "gco": "http://www.isotc211.org/2005/gco"}


def test_iso19139_metadata(env):  # noqa: F811
    app, client, admin, _regular, _repo = env
    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: (
        lambda session, info: [1.0, 45.0, 2.0, 46.0]
    )
    _register(app, client, admin, public=True)
    _as(app, admin)
    client.patch(
        "/v1/collections/incidents",
        json={"keywords": ["sécurité"], "inspireTheme": "hh", "license": "etalab-2.0",
              "contact": "sig@exemple.fr", "lineage": "Saisie terrain"},
    )
    r = client.get("/v1/collections/incidents/metadata")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(r.content)
    assert root.tag == "{http://www.isotc211.org/2005/gmd}MD_Metadata"
    assert root.findtext("gmd:fileIdentifier/gco:CharacterString", namespaces=NS) == "incidents"
    words = [e.text for e in root.iterfind(".//gmd:keyword/gco:CharacterString", NS)]
    assert "sécurité" in words and "Santé et sécurité des personnes" in words
    assert root.findtext(".//gmd:topicCategory/gmd:MD_TopicCategoryCode", namespaces=NS) == "health"
    west = root.findtext(".//gmd:westBoundLongitude/gco:Decimal", namespaces=NS)
    assert float(west) == 1.0
    assert "/v1/collections/incidents/items" in r.text


def test_iso19139_404_and_ogc_link(env):  # noqa: F811
    app, client, admin, _regular, _repo = env
    assert client.get("/v1/collections/nope/metadata").status_code == 404
    _register(app, client, admin, public=True)
    links = client.get("/v1/collections/incidents").json()["links"]
    assert any(link["rel"] == "describedby" and link["href"].endswith("/metadata") for link in links)
```

- [ ] **Step 2:** `uv run pytest tests/test_records_routes.py tests/test_records_iso19139.py -v` → FAIL (404).

- [ ] **Step 3: Dépôt d'items** — `core/app/items/repository.py` : extraire le filtre d'emprise de `list_items` en

```python
def _bbox_clause(bbox: tuple[float, float, float, float]):
    """Intersection de rectangles sur les 4 colonnes persistées (spec §2.4, REV-364 a :
    ouest > est = rectangle à cheval sur l'antiméridien). Un item sans bbox est exclu."""
    minx, miny, maxx, maxy = bbox
    in_x = (
        or_(Item.bbox_max_x >= minx, Item.bbox_min_x <= maxx)
        if minx > maxx
        else and_(Item.bbox_max_x >= minx, Item.bbox_min_x <= maxx)
    )
    return and_(Item.bbox_min_x.isnot(None), in_x, Item.bbox_max_y >= miny, Item.bbox_min_y <= maxy)
```

et, dans `list_items`, remplacer le bloc `if bbox is not None: …` par `if bbox is not None: query = query.where(_bbox_clause(bbox))`. `list_published_items` : nouveaux kwargs `q: str | None = None, bbox: tuple[float, float, float, float] | None = None`, et juste après le filtre `resource_type` :

```python
    if q:
        # Records (AUD-048) : plein texte simple, sans recherche vectorielle (route anonyme,
        # pas d'appel au fournisseur d'embeddings sur une entrée non authentifiée).
        like = f"%{q}%"
        query = query.where(or_(Item.title.ilike(like), Item.abstract.ilike(like)))
    if bbox is not None:
        query = query.where(_bbox_clause(bbox))
```

`uv run pytest tests/test_items_repository.py tests/test_public_items_list.py tests/test_items_bbox.py -v` (noms réels : `grep -rln "bbox" core/tests/test_items*.py`) → PASS (refactor sans changement de comportement).

- [ ] **Step 4: Sérialiseur Records** — `core/app/records/serializers.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""OGC API Records Part 1 (OGC 20-004r1) : un item du catalogue = un record GeoJSON."""

from app.catalog.metadata import resolve_license
from app.items.schemas import ItemRead

SPEC = "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf"
RECORD_CORE = f"{SPEC}/record-core"
CONFORMANCE = [
    RECORD_CORE,
    f"{SPEC}/record-collection",
    f"{SPEC}/records-api",  # libellé de l'annexe A.3 (le texte §8 écrit « record-api »)
    f"{SPEC}/json",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]
CATALOG_ID = "catalog"


def _polygon(bbox: list[float]) -> dict:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def record(*, base: str, item: ItemRead) -> dict:
    props: dict = {
        "type": item.resourceType,
        "title": item.title,
        "description": item.abstract,
        "keywords": list(item.keywords),
        "language": {"code": item.language},
        "created": item.date,
        "updated": item.updatedAt,
    }
    lic = resolve_license(item.license) if item.license else None
    if lic is not None:
        props["license"] = lic.spdx_id
    items = f"{base}/records/collections/{CATALOG_ID}"
    return {
        "id": item.pk,
        "type": "Feature",
        "conformsTo": [RECORD_CORE],
        "time": None,
        "geometry": _polygon(item.bbox) if item.bbox else None,
        "properties": props,
        "links": [
            {"rel": "self", "type": "application/geo+json", "href": f"{items}/items/{item.pk}"},
            {"rel": "collection", "type": "application/json", "href": items},
        ],
    }


def catalog(*, base: str) -> dict:
    href = f"{base}/records/collections/{CATALOG_ID}"
    return {
        "id": CATALOG_ID,
        "type": "Collection",
        "itemType": "record",
        "title": "Catalogue GeoStudio",
        "description": "Cartes, applications, tableaux de bord et jeux de données du catalogue.",
        "links": [
            {"rel": "self", "type": "application/ogc-catalog+json", "href": href},
            {"rel": "items", "type": "application/geo+json", "href": f"{href}/items"},
        ],
    }
```

- [ ] **Step 5: ISO 19139** — `core/app/records/iso19139.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Fiche ISO 19139 (gmd) d'une collection (AUD-047, D11 : export ISO, pas de CSW).
Profil minimal INSPIRE : identifiant, langue, contact, date, SRS, citation, résumé,
mots-clés (libres + thème GEMET-INSPIRE), contraintes, catégorie, emprise, distribution,
généalogie. Toutes les valeurs passent par escape/quoteattr."""

from xml.sax.saxutils import escape, quoteattr

from app.catalog.metadata import ISO639_2B, resolve_inspire_theme, resolve_license

_NS = (
    'xmlns:gmd="http://www.isotc211.org/2005/gmd" '
    'xmlns:gco="http://www.isotc211.org/2005/gco" '
    'xmlns:xlink="http://www.w3.org/1999/xlink"'
)
_CODELIST = "http://standards.iso.org/iso/19139/resources/gmxCodelists.xml"


def _cs(value: str) -> str:
    return f"<gco:CharacterString>{escape(value)}</gco:CharacterString>"


def _code(element: str, value: str) -> str:
    return (
        f"<gmd:{element} codeList={quoteattr(f'{_CODELIST}#{element}')} "
        f"codeListValue={quoteattr(value)}>{escape(value)}</gmd:{element}>"
    )


def _keywords(words: list[str], thesaurus: tuple[str, str] | None = None) -> str:
    kws = "".join(f"<gmd:keyword>{_cs(w)}</gmd:keyword>" for w in words)
    thes = ""
    if thesaurus:
        title, date = thesaurus
        thes = (
            "<gmd:thesaurusName><gmd:CI_Citation>"
            f"<gmd:title>{_cs(title)}</gmd:title><gmd:date><gmd:CI_Date>"
            f"<gmd:date><gco:Date>{date}</gco:Date></gmd:date>"
            f"<gmd:dateType>{_code('CI_DateTypeCode', 'publication')}</gmd:dateType>"
            "</gmd:CI_Date></gmd:date></gmd:CI_Citation></gmd:thesaurusName>"
        )
    return f"<gmd:descriptiveKeywords><gmd:MD_Keywords>{kws}{thes}</gmd:MD_Keywords></gmd:descriptiveKeywords>"


def _party(name: str, contact: str, role: str) -> str:
    email = (
        "<gmd:contactInfo><gmd:CI_Contact><gmd:address><gmd:CI_Address>"
        f"<gmd:electronicMailAddress>{_cs(contact)}</gmd:electronicMailAddress>"
        "</gmd:CI_Address></gmd:address></gmd:CI_Contact></gmd:contactInfo>"
        if "@" in contact
        else ""
    )
    return (
        f"<gmd:CI_ResponsibleParty><gmd:organisationName>{_cs(name)}</gmd:organisationName>"
        f"{email}<gmd:role>{_code('CI_RoleCode', role)}</gmd:role></gmd:CI_ResponsibleParty>"
    )


def collection_metadata(*, col, bbox: list[float] | None, srid: int | None, items_url: str, publisher: str) -> str:
    lang = ISO639_2B.get(col.language, "fre")
    organisation = col.producer or publisher
    theme = resolve_inspire_theme(col.inspire_theme) if col.inspire_theme else None
    lic = resolve_license(col.license) if col.license else None
    licence_text = (lic.label if lic else "") or col.license_uri or "Conditions inconnues"
    keywords = _keywords(list(col.keywords)) if col.keywords else ""
    if theme is not None:
        keywords += _keywords([theme.label], ("GEMET - INSPIRE themes, version 1.0", "2008-06-01"))
    topic = (
        f"<gmd:topicCategory><gmd:MD_TopicCategoryCode>{theme.iso_category}"
        "</gmd:MD_TopicCategoryCode></gmd:topicCategory>"
        if theme is not None
        else ""
    )
    extent = ""
    if bbox:
        w, s, e, n = bbox
        extent = (
            "<gmd:extent><gmd:EX_Extent><gmd:geographicElement><gmd:EX_GeographicBoundingBox>"
            f"<gmd:westBoundLongitude><gco:Decimal>{w}</gco:Decimal></gmd:westBoundLongitude>"
            f"<gmd:eastBoundLongitude><gco:Decimal>{e}</gco:Decimal></gmd:eastBoundLongitude>"
            f"<gmd:southBoundLatitude><gco:Decimal>{s}</gco:Decimal></gmd:southBoundLatitude>"
            f"<gmd:northBoundLatitude><gco:Decimal>{n}</gco:Decimal></gmd:northBoundLatitude>"
            "</gmd:EX_GeographicBoundingBox></gmd:geographicElement></gmd:EX_Extent></gmd:extent>"
        )
    srs = (
        "<gmd:referenceSystemInfo><gmd:MD_ReferenceSystem><gmd:referenceSystemIdentifier>"
        f"<gmd:RS_Identifier><gmd:code>{_cs(f'EPSG:{srid}')}</gmd:code></gmd:RS_Identifier>"
        "</gmd:referenceSystemIdentifier></gmd:MD_ReferenceSystem></gmd:referenceSystemInfo>"
        if srid
        else ""
    )
    lineage = (
        "<gmd:dataQualityInfo><gmd:DQ_DataQuality><gmd:scope><gmd:DQ_Scope>"
        f"<gmd:level>{_code('MD_ScopeCode', 'dataset')}</gmd:level></gmd:DQ_Scope></gmd:scope>"
        f"<gmd:lineage><gmd:LI_Lineage><gmd:statement>{_cs(col.lineage)}</gmd:statement>"
        "</gmd:LI_Lineage></gmd:lineage></gmd:DQ_DataQuality></gmd:dataQualityInfo>"
        if col.lineage
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<gmd:MD_Metadata {_NS}>"
        f"<gmd:fileIdentifier>{_cs(col.id)}</gmd:fileIdentifier>"
        f"<gmd:language>{_code('LanguageCode', lang)}</gmd:language>"
        f"<gmd:hierarchyLevel>{_code('MD_ScopeCode', 'dataset')}</gmd:hierarchyLevel>"
        f"<gmd:contact>{_party(organisation, col.contact, 'pointOfContact')}</gmd:contact>"
        f"<gmd:dateStamp><gco:Date>{col.updated_at.date().isoformat()}</gco:Date></gmd:dateStamp>"
        f"{srs}"
        "<gmd:identificationInfo><gmd:MD_DataIdentification>"
        f"<gmd:citation><gmd:CI_Citation><gmd:title>{_cs(col.title)}</gmd:title>"
        "<gmd:date><gmd:CI_Date>"
        f"<gmd:date><gco:Date>{col.created_at.date().isoformat()}</gco:Date></gmd:date>"
        f"<gmd:dateType>{_code('CI_DateTypeCode', 'creation')}</gmd:dateType>"
        "</gmd:CI_Date></gmd:date>"
        f"<gmd:identifier><gmd:RS_Identifier><gmd:code>{_cs(col.id)}</gmd:code></gmd:RS_Identifier></gmd:identifier>"
        "</gmd:CI_Citation></gmd:citation>"
        f"<gmd:abstract>{_cs(col.description or col.title)}</gmd:abstract>"
        f"<gmd:pointOfContact>{_party(organisation, col.contact, 'owner')}</gmd:pointOfContact>"
        f"{keywords}"
        "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
        f"<gmd:useLimitation>{_cs(licence_text)}</gmd:useLimitation>"
        f"<gmd:accessConstraints>{_code('MD_RestrictionCode', 'otherRestrictions')}</gmd:accessConstraints>"
        f"<gmd:otherConstraints>{_cs(licence_text)}</gmd:otherConstraints>"
        "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        f"<gmd:language>{_code('LanguageCode', lang)}</gmd:language>"
        f"{topic}{extent}"
        "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        "<gmd:distributionInfo><gmd:MD_Distribution><gmd:transferOptions><gmd:MD_DigitalTransferOptions>"
        f"<gmd:onLine><gmd:CI_OnlineResource><gmd:linkage><gmd:URL>{escape(items_url)}</gmd:URL></gmd:linkage>"
        f"<gmd:protocol>{_cs('OGC API Features')}</gmd:protocol></gmd:CI_OnlineResource></gmd:onLine>"
        "</gmd:MD_DigitalTransferOptions></gmd:transferOptions></gmd:MD_Distribution></gmd:distributionInfo>"
        f"{lineage}"
        "</gmd:MD_Metadata>"
    )
```

Lignes longues : `uv run ruff format` les repliera ; si `E501` subsiste dans des chaînes, les couper en concaténations implicites (pas de `noqa`).

- [ ] **Step 6: Routes** — `core/app/records/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""OGC API Records Part 1 (AUD-048, D11) sur le catalogue d'items + fiche ISO 19139 par
collection. Aucun accès SQL propre : liste/détail passent par les mêmes fonctions que
/items (authentifié, can()) et /public/items (anonyme : publié seulement)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.bbox import parse_bbox_floats
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.routes import get_introspector, get_readable_collection
from app.dcat.routes import _resolve_bbox_degrading, _resolve_tenant, get_bbox_provider
from app.db import get_session
from app.features.routes import get_rls_scope
from app.items import repository as items_repo
from app.items.service import get_item_service
from app.records import iso19139, serializers
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.tenants.repository import DEFAULT_TENANT_SLUG

router = APIRouter(prefix="/records", tags=["records"])
metadata_router = APIRouter(tags=["records"])
GEOJSON = "application/geo+json"


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/v1"


def _check_catalog(catalog_id: str) -> None:
    if catalog_id != serializers.CATALOG_ID:
        raise HTTPException(status_code=404, detail="unknown catalog")


@router.get("")
def landing(request: Request):
    b = _base(request)
    return {
        "title": "GeoStudio OGC API Records",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{b}/records"},
            {"rel": "conformance", "type": "application/json", "href": f"{b}/records/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{b}/records/collections"},
        ],
    }


@router.get("/conformance")
def conformance():
    return {"conformsTo": serializers.CONFORMANCE}


@router.get("/collections")
def collections(request: Request):
    b = _base(request)
    return {
        "collections": [serializers.catalog(base=b)],
        "links": [{"rel": "self", "type": "application/json", "href": f"{b}/records/collections"}],
    }


@router.get("/collections/{catalog_id}")
def get_catalog(catalog_id: str, request: Request):
    _check_catalog(catalog_id)
    return JSONResponse(
        serializers.catalog(base=_base(request)), media_type="application/ogc-catalog+json"
    )


@router.get("/collections/{catalog_id}/items")
def list_records(
    catalog_id: str,
    request: Request,
    q: str | None = None,
    bbox: str | None = None,
    type: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    page: int = Query(1, ge=1),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    _check_catalog(catalog_id)
    try:
        box = parse_bbox_floats(bbox)  # None si absent
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid bbox: {exc}") from exc
    if user is None:
        result = items_repo.list_published_items(
            session, tenant_id=DEFAULT_TENANT_SLUG, resource_type=type, q=q, bbox=box,
            page=page, page_size=limit,
        )
    else:
        result = items_repo.list_items(
            session, tenant_id=user.tenant_id, current_user_id=user.id, q=q,
            resource_type=type, scope="all", page=page, page_size=limit, bbox=box,
        )
    b = _base(request)
    links = [{"rel": "self", "type": GEOJSON, "href": str(request.url)}]
    if page * limit < result.total:
        links.append(
            {"rel": "next", "type": GEOJSON, "href": str(request.url.include_query_params(page=page + 1, limit=limit))}
        )
    body = {
        "type": "FeatureCollection",
        "features": [serializers.record(base=b, item=i) for i in result.items],
        "numberMatched": result.total,
        "numberReturned": len(result.items),
        "links": links,
    }
    return JSONResponse(body, media_type=GEOJSON)


@router.get("/collections/{catalog_id}/items/{record_id}")
def get_record(
    catalog_id: str,
    record_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    _check_catalog(catalog_id)
    if user is None:
        item = items_repo.get_published_item(
            session, item_id=record_id, tenant_id=DEFAULT_TENANT_SLUG
        )
        if item is None or item.contentStatus == "deprecated":
            raise HTTPException(status_code=404, detail="record not found")
    else:
        item = get_item_service(session, item_id=record_id, user=user)
    return JSONResponse(serializers.record(base=_base(request), item=item), media_type=GEOJSON)


@metadata_router.get("/collections/{collection_id}/metadata")
def get_iso_metadata(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
) -> Response:
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )  # 404 non-fuyant, même porte que DCAT
    try:
        srid = introspect(session, col.table_name).srid
    except (TableNotFound, UnsupportedTable, DBAPIError):
        srid = None
    bbox = _resolve_bbox_degrading(
        session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls
    )
    xml = iso19139.collection_metadata(
        col=col,
        bbox=bbox,
        srid=srid,
        items_url=f"{_base(request)}/collections/{col.id}/items",
        publisher=_resolve_tenant(session, user).name,
    )
    return Response(xml, media_type="application/xml")
```

Noms vérifiés : `DEFAULT_TENANT_SLUG = "default"` (`app/tenants/repository.py:9`), `parse_bbox_floats(raw) -> tuple | None` lève `ValueError` (`app/bbox.py:16`, converti en 400 ci-dessus), `get_item_service` (`app/items/service.py:54`). `main.py` : `from app.records import routes as records_routes` et, à côté de l'inclusion des routeurs `dcat`/`stac` dans `v1_router` : `v1_router.include_router(records_routes.router)` puis `v1_router.include_router(records_routes.metadata_router)`. `core/pyproject.toml` : insérer `"app.records",` entre `"app.notifications",` et `"app.dcat",` (avec un commentaire `# app.records (AUD-048) : OGC API Records + ISO 19139, au-dessus de dcat/items/catalog.`). `core/app/collections/routes.py::_ogc_links` : ajouter

```python
        {
            "rel": "describedby",
            "type": "application/xml",
            "href": f"{base}/collections/{cid}/metadata",
        },
```

- [ ] **Step 7:** `uv run pytest tests/test_records_routes.py tests/test_records_iso19139.py tests/test_ogc_discovery.py tests/test_public_items_list.py -v` → PASS ; `uv run lint-imports` → OK. Si l'import de `get_item_service` déclenche un cycle (`app.items.service` importe `app.sharing`), le contrat de couches le dira : `app.records` est au-dessus de `app.items`, aucune arête vers le haut. Régénérer OpenAPI + types TS.

- [ ] **Step 8: Commit**

```bash
git add core/app/records core/app/items/repository.py core/app/main.py core/app/collections/routes.py \
  core/pyproject.toml core/tests/test_records_routes.py core/tests/test_records_iso19139.py \
  core/openapi.json shell/src/api/generated
git commit -m "feat(core): OGC API Records sur le catalogue et fiche ISO 19139 par collection (AUD-048/047)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: AUD-122 — fonds de carte souverains (IGN Géoplateforme, mode sans fond externe)

**Files:**
- Modify: `core/app/auth/dependency.py` (`is_external_basemaps_enabled`)
- Modify: `core/app/instance/routes.py:47-61`, `core/app/auth/routes.py:41-62, 106-119` (`externalBasemapsEnabled`)
- Modify: `core/app/ingestion/importer.py:58-59, 491` (`default_basemap_style()`)
- Modify: `core/tests/test_auth_me_capabilities.py:20-33`, Create: `core/tests/test_external_basemaps.py`
- Modify: `docker-compose.yml` (services `core` ~l.385 et `worker` ~l.640), `.env.example` (~l.303), `deploy/helm/geostudio/values.yaml` (~l.101)
- Create: `shell/public/basemaps/blank.json`
- Modify: `shell/src/map/basemaps.ts`, `shell/src/map/useBasemaps.ts`, `shell/src/builder/widgets/mapWidget.tsx:35,99,334`, `shell/src/builder/ExplorerDrawer.tsx:15,84`, `shell/src/pages/CatalogSpatialFilter.tsx:84`, `shell/src/api/domains/layers.ts:47`, `shell/src/api/types.ts:261-274`, `shell/src/api/meSchemaParity.test.ts:69-82`, `shell/src/desktop/DesktopItemClient.ts:232`, `shell/e2e/mocks.ts:142`
- Create: `shell/src/map/basemaps.test.ts` ; Modify: `shell/src/api/itemClient.test.ts:608`

**Interfaces:**
- Consumes: `ItemClient.getInstanceInfo(): Promise<InstanceInfo>` ; `useOptionalItemClient()` ; `resolveBasemapStyle(style)`.
- Produces: `CORE_EXTERNAL_BASEMAPS_ENABLED` (défaut `true`) ; `is_external_basemaps_enabled() -> bool` ; capacité `externalBasemapsEnabled` (`/instance` et `/me`) ; `default_basemap_style() -> str` (`importer.py`) ; shell : `Basemap.external?: boolean`, `BLANK_BASEMAP`, `defaultBasemapStyle(externalEnabled: boolean): string`, `allowedBasemaps(all: Basemap[], externalEnabled: boolean): Basemap[]`, `useExternalBasemapsEnabled(): boolean`, `InstanceInfo.externalBasemapsEnabled?: boolean` (absent ⇒ `true`).

**Jumelles :** les **cinq** sites de fond par défaut (`mapWidget`, `ExplorerDrawer`, `CatalogSpatialFilter`, `createMapItem`, `importer.py`) + la galerie (`useBasemaps` → `BasemapSelect`, `basemapGallery`) ; `PipelinePreviewMap.tsx` **laissé à L7** (AUD-161) ; gabarits swipe (reporté) ; `/instance` et `/me` (parité forcée par `test_auth_me_capabilities.py` et `meSchemaParity.test.ts`) ; services `core` **et** `worker` (l'importer tourne dans le worker — piège n°2).

- [ ] **Step 1: Tests cœur qui échouent** — `core/tests/test_auth_me_capabilities.py` : ajouter `"externalBasemapsEnabled",` à `CAPABILITY_KEYS`. `core/tests/test_external_basemaps.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-122 : un déploiement souverain coupe tout fond de carte tiers par défaut."""

from app.auth.dependency import is_external_basemaps_enabled
from app.ingestion.importer import default_basemap_style
from app.instance.routes import get_instance_info


def test_default_is_external(monkeypatch):
    monkeypatch.delenv("CORE_EXTERNAL_BASEMAPS_ENABLED", raising=False)
    assert is_external_basemaps_enabled() is True
    assert default_basemap_style().startswith("https://")
    assert get_instance_info()["externalBasemapsEnabled"] is True


def test_sovereign_mode_uses_local_blank_style(monkeypatch):
    monkeypatch.setenv("CORE_EXTERNAL_BASEMAPS_ENABLED", "false")
    assert is_external_basemaps_enabled() is False
    assert default_basemap_style() == "/basemaps/blank.json"
    assert get_instance_info()["externalBasemapsEnabled"] is False
```

(vérifier que `get_instance_info` n'a pas de dépendance FastAPI obligatoire — l.47, sans paramètre : appel direct OK.) → FAIL (`ImportError`).

- [ ] **Step 2: Cœur** — `core/app/auth/dependency.py`, à côté de `is_routing_enabled` :

```python
def is_external_basemaps_enabled() -> bool:
    """AUD-122 : fonds de carte tiers (MapLibre démo, Carto, IGN Géoplateforme) proposés.
    `false` = déploiement souverain/air-gapped : fond vierge local par défaut, fonds tiers
    masqués dans le shell. Défaut `true` (comportement historique)."""
    return os.environ.get("CORE_EXTERNAL_BASEMAPS_ENABLED", "true").strip().lower() != "false"
```

`instance/routes.py::get_instance_info` : ajouter `"externalBasemapsEnabled": is_external_basemaps_enabled(),` (et l'import). `auth/routes.py` : `externalBasemapsEnabled: bool` dans `MeCapabilities`, `externalBasemapsEnabled=is_external_basemaps_enabled(),` dans la construction (et l'import). `ingestion/importer.py` : remplacer l.58-59 par

```python
# Doit rester synchronisé avec shell/src/map/basemaps.ts (DEFAULT_BASEMAP / BLANK_BASEMAP).
_EXTERNAL_BASEMAP_STYLE = "https://demotiles.maplibre.org/style.json"
BLANK_BASEMAP_STYLE = "/basemaps/blank.json"


def default_basemap_style() -> str:
    return _EXTERNAL_BASEMAP_STYLE if is_external_basemaps_enabled() else BLANK_BASEMAP_STYLE
```

et l.491 `basemap=BaseMap(style=default_basemap_style()),` (import `from app.auth.dependency import is_external_basemaps_enabled` ; si `lint-imports` refuse l'arête `app.ingestion → app.auth`, lire la variable d'environnement directement dans `importer.py` avec le même défaut et un commentaire renvoyant à `is_external_basemaps_enabled`). `grep -rn "_DEFAULT_BASEMAP_STYLE" core` → plus aucune occurrence (tests compris).

Déploiement : `docker-compose.yml`, service `core` juste après `CORE_RASTER_ENABLED: ${CORE_RASTER_ENABLED:-false}` (~l.385) **et** service `worker` après sa ligne `CORE_RASTER_ENABLED` (~l.640) :

```yaml
      # AUD-122 : false = aucun fond de carte tiers (déploiement souverain/air-gapped).
      CORE_EXTERNAL_BASEMAPS_ENABLED: ${CORE_EXTERNAL_BASEMAPS_ENABLED:-true}
```

`.env.example`, après `CORE_RASTER_ENABLED=false` :

```
# AUD-122 : false = fond vierge local par défaut et fonds tiers (MapLibre démo, Carto,
# IGN Géoplateforme) masqués — pour un déploiement souverain ou sans accès Internet.
CORE_EXTERNAL_BASEMAPS_ENABLED=true
```

`deploy/helm/geostudio/values.yaml`, après `CORE_RASTER_ENABLED: "false"` : `  CORE_EXTERNAL_BASEMAPS_ENABLED: "true"`. `uv run pytest tests/test_external_basemaps.py tests/test_auth_me_capabilities.py tests/test_deployability.py tests/test_ingestion_importer.py -v` → PASS (`test_deployability` vérifie la documentation de la substitution et la présence par service).

- [ ] **Step 3: Tests shell qui échouent** — `shell/src/map/basemaps.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  BASEMAPS,
  BLANK_BASEMAP,
  DEFAULT_BASEMAP,
  allowedBasemaps,
  defaultBasemapStyle,
  resolveBasemapStyle,
} from "./basemaps";

describe("fonds de carte souverains (AUD-122)", () => {
  it("propose les fonds IGN Géoplateforme en raster", () => {
    const ign = BASEMAPS.filter((b) => b.id.startsWith("ign-"));
    expect(ign.map((b) => b.id)).toEqual(["ign-plan", "ign-ortho"]);
    for (const b of ign) expect(b.style.startsWith("xyz:https://data.geopf.fr/wmts?")).toBe(true);
    const style = resolveBasemapStyle(ign[0].style);
    expect(typeof style).toBe("object");
    if (typeof style === "object") {
      const source = style.sources.basemap as { attribution?: string };
      expect(source.attribution).toContain("IGN");
    }
  });

  it("masque les fonds externes et passe au fond vierge en mode souverain", () => {
    expect(defaultBasemapStyle(true)).toBe(DEFAULT_BASEMAP.style);
    expect(defaultBasemapStyle(false)).toBe("/basemaps/blank.json");
    expect(allowedBasemaps(BASEMAPS, false)).toEqual([BLANK_BASEMAP]);
    expect(allowedBasemaps(BASEMAPS, true)).toEqual(BASEMAPS);
  });
});
```

`shell/src/api/itemClient.test.ts`, après le test `createMapItem` existant :

```ts
test("createMapItem prend le fond vierge quand l'instance coupe les fonds externes", async () => {
  let body: any;
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, externalBasemapsEnabled: false }),
    ),
    http.post("https://core.test/v1/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: "map", itemId: "77" }, { status: 201 });
    }),
  );
  await makeClient().createMapItem({ title: "Carte", owner: "alice" });
  expect(body.config.map.basemap.style).toBe("/basemaps/blank.json");
});
```

`npx vitest run src/map/basemaps.test.ts src/api/itemClient.test.ts` → FAIL.

- [ ] **Step 4: Shell** — `shell/public/basemaps/blank.json` :

```json
{
  "version": 8,
  "name": "Vierge",
  "sources": {},
  "layers": [{ "id": "background", "type": "background", "paint": { "background-color": "#f2efe9" } }]
}
```

`shell/src/map/basemaps.ts` (remplace la déclaration de `Basemap`/`BASEMAPS`/`DEFAULT_BASEMAP` et `resolveBasemapStyle`) :

```ts
// SPDX-License-Identifier: Apache-2.0
import type { StyleSpecification } from "maplibre-gl";

/** `external` : fond servi par un tiers (masqué quand l'instance coupe les fonds externes,
 * AUD-122). */
export type Basemap = { id: string; label: string; style: string; external?: boolean };

// Géoplateforme IGN (WMTS en KVP, grille PM = WebMercatorQuad) — gabarit vérifié (HTTP 200).
const IGN_WMTS =
  "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=normal" +
  "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}";

/** Fond local sans aucune requête vers un tiers (servi par le shell : public/basemaps). */
export const BLANK_BASEMAP: Basemap = { id: "vierge", label: "Vierge", style: "/basemaps/blank.json" };

export const BASEMAPS: Basemap[] = [
  {
    id: "clair",
    label: "Clair",
    style: "https://demotiles.maplibre.org/style.json",
    external: true,
  },
  {
    id: "positron",
    label: "Positron",
    style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    external: true,
  },
  {
    id: "voyager",
    label: "Voyager",
    style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    external: true,
  },
  {
    id: "ign-plan",
    label: "Plan IGN",
    style: `xyz:${IGN_WMTS}&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&FORMAT=image/png`,
    external: true,
  },
  {
    id: "ign-ortho",
    label: "Ortho IGN",
    style: `xyz:${IGN_WMTS}&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&FORMAT=image/jpeg`,
    external: true,
  },
  BLANK_BASEMAP,
];

export const DEFAULT_BASEMAP: Basemap = BASEMAPS[0];

export function defaultBasemapStyle(externalEnabled: boolean): string {
  return externalEnabled ? DEFAULT_BASEMAP.style : BLANK_BASEMAP.style;
}

export function allowedBasemaps(all: Basemap[], externalEnabled: boolean): Basemap[] {
  return externalEnabled ? all : all.filter((b) => !b.external);
}

const XYZ_PREFIX = "xyz:";

/** REV-367 i : un fond `xyz:<gabarit {z}/{x}/{y}>` devient un style raster minimal ;
 * toute autre valeur (URL de style.json) est transmise telle quelle à MapLibre. */
export function resolveBasemapStyle(style: string): string | StyleSpecification {
  if (!style.startsWith(XYZ_PREFIX)) return style;
  const tiles = style.slice(XYZ_PREFIX.length);
  // Licence ouverte Etalab 2.0 : l'attribution IGN est requise.
  const attribution = tiles.startsWith("https://data.geopf.fr/") ? "© IGN" : undefined;
  return {
    version: 8,
    sources: {
      basemap: { type: "raster", tiles: [tiles], tileSize: 256, ...(attribution ? { attribution } : {}) },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}
```

(libellés sans accent ni mot de la liste du détecteur i18n — `scripts/check-i18n-coverage.mjs` — volontairement ; `npm run lint` doit rester vert.) `shell/src/map/useBasemaps.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useOptionalItemClient } from "../api/ItemClientProvider";
import { BASEMAPS, allowedBasemaps, type Basemap } from "./basemaps";

/** AUD-122 : l'instance autorise-t-elle les fonds tiers ? Sans client, sans réponse ou champ
 * absent : oui (comportement historique). ponytail: `true` jusqu'à la réponse de /instance —
 * un widget sans fond configuré peut tenter un fond tiers une fois ; les cartes créées
 * (createMapItem, import) portent déjà le bon fond, choisi côté requête. */
export function useExternalBasemapsEnabled(): boolean {
  const client = useOptionalItemClient();
  const [enabled, setEnabled] = useState(true);
  useEffect(() => {
    let cancelled = false;
    if (!client?.getInstanceInfo) return;
    client
      .getInstanceInfo()
      .then((info) => {
        if (!cancelled) setEnabled(info.externalBasemapsEnabled !== false);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client]);
  return enabled;
}

/** Fonds intégrés autorisés + fonds partagés du tenant (REV-367 i, déclarés par un admin :
 * jamais filtrés). Sans client, sans `listTenantBasemaps` ou en cas d'échec : intégrés seuls. */
export function useBasemaps(): Basemap[] {
  const client = useOptionalItemClient();
  const external = useExternalBasemapsEnabled();
  const [tenant, setTenant] = useState<Basemap[]>([]);
  useEffect(() => {
    let cancelled = false;
    const load = client?.listTenantBasemaps;
    if (!load) return;
    load
      .call(client)
      .then((rows) => {
        if (!cancelled) setTenant(rows.map((r) => ({ ...r, id: `tenant-${r.id}` })));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client]);
  const builtIn = allowedBasemaps(BASEMAPS, external);
  const known = new Set(builtIn.map((b) => b.style));
  return [...builtIn, ...tenant.filter((b) => !known.has(b.style))];
}
```

`mapWidget.tsx` : supprimer `const DEFAULT_STYLE = …` (l.35) ; dans chaque composant qui lisait `DEFAULT_STYLE` (l.99 et l.334), ajouter `const fallbackStyle = defaultBasemapStyle(useExternalBasemapsEnabled());` en tête du composant et remplacer `DEFAULT_STYLE` par `fallbackStyle` (imports depuis `../../map/basemaps` et `../../map/useBasemaps`). `ExplorerDrawer.tsx` : même traitement (l.15 supprimée, l.84 `basemap: { style: fallbackStyle }`). `CatalogSpatialFilter.tsx` : `const external = useExternalBasemapsEnabled();` dans le composant, `style: defaultBasemapStyle(external)` à la création (l.84), et un effet

```tsx
  useEffect(() => {
    mapRef.current?.setStyle(defaultBasemapStyle(external));
  }, [external]);
```

`api/domains/layers.ts::createMapItem` :

```ts
      // AUD-122 : le fond par défaut suit la capacité de l'instance (fond vierge si coupée).
      const info = await request<InstanceInfo>("GET", "/instance").catch(() => null);
      const map: MapConfig = {
        basemap: { style: defaultBasemapStyle(info?.externalBasemapsEnabled !== false) },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
```

(remplacer l'import de `DEFAULT_BASEMAP` par `defaultBasemapStyle` et importer le type `InstanceInfo`.) `api/types.ts`, dans `InstanceInfo` après `experimentalOpsEnabled: boolean;` : `/** AUD-122 : absent = true. */ externalBasemapsEnabled?: boolean;`. `meSchemaParity.test.ts` : ajouter `"externalBasemapsEnabled",` à `INSTANCE_INFO_FIELDS`. `DesktopItemClient.ts:232` et `e2e/mocks.ts:142` : ajouter `externalBasemapsEnabled: true,`.

- [ ] **Step 5:** régénérer OpenAPI + types TS (`MeCapabilities` change) ; `cd shell && npx vitest run src/map src/api/itemClient.test.ts src/api/meSchemaParity.test.ts src/builder/widgets src/pages/CatalogSpatialFilter.test.tsx` → PASS ; `npm run lint && npm run build` ; `npx playwright test e2e/map-*.spec.ts e2e/catalog*.spec.ts` → PASS (aucun changement de comportement par défaut).

- [ ] **Step 6: Commit**

```bash
git add core/app/auth core/app/instance core/app/ingestion/importer.py core/tests docker-compose.yml \
  .env.example deploy/helm/geostudio/values.yaml core/openapi.json shell/public/basemaps shell/src shell/e2e/mocks.ts
git commit -m "feat(shell): fonds IGN Géoplateforme et mode sans fond externe (AUD-122)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Clôture — inventaire, régénérations, suites complètes, jumelles

**Files:**
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (lignes 242, 255, 259, 318, 324 + une ligne nouvelle)

**Interfaces:**
- Consumes: toutes les surfaces produites par T1-T8.
- Produces: inventaire à jour (porte CI `core/tests/test_feature_inventory.py`), suites vertes.

- [ ] **Step 1: Inventaire** — script ponctuel (ne pas le committer), lancé depuis la racine :

```bash
cd /home/lenen/projets/geostudio && python3 - <<'EOF'
import json
p = "docs/revue/inventaire-fonctionnalites.jsonl"
rows = [json.loads(line) for line in open(p, encoding="utf-8")]
by_id = {r["id"]: r for r in rows}

landing = by_id["features-ogc-api-landing-page-et-declaration-de-conformite-ogc-api-features"]
landing["description"] = (
    "GET / et /conformance servent les liens standard OGC (self/conformance/data/service-desc/"
    "tiling-schemes) et les classes de conformité supportées (core/geojson/crs/create-replace-"
    "delete, filter/features-filter/queryables, CQL2-text ; Tiles/TMS si CORE_OWS_ENABLED). "
    "GET /collections/{id}/queryables : JSON Schema des propriétés filtrables (AUD-041/042)."
)
landing["surfaces"]["rest"] = sorted(
    set(landing["surfaces"]["rest"]) | {"GET /v1/collections/{collection_id}/queryables"}
)
# queryables : même porte get_readable_collection que /items -> pas dans « publiques ».

ows = by_id["donnees-filtre-cql2-et-wfs-ows"]
old_tile = "GET /v1/collections/{collection_id}/tiles/{tms}/{z}/{x}/{y}"
new = [
    "GET /v1/collections/{collection_id}/tiles/{tms}",
    "GET /v1/collections/{collection_id}/tiles/{tms}/{tile_matrix}/{tile_row}/{tile_col}",
    "GET /v1/tileMatrixSets",
    "GET /v1/tileMatrixSets/{tms_id}",
]
for key in ("rest",):
    ows["surfaces"][key] = sorted((set(ows["surfaces"][key]) - {old_tile}) | set(new))
ows["garde_auto_scopee"] = sorted((set(ows["garde_auto_scopee"]) - {old_tile}) | set(new[:2]))
ows["publiques"] = sorted(set(ows.get("publiques", [])) | set(new[2:]))
ows["description"] += " RESOURCEID WFS ; Tiles 1.0/TMS 2.0 (tileset, TileMatrixSet JSON, ordre tileMatrix/tileRow/tileCol, AUD-042/140)."

rows.append({
    "id": "catalogue-ogc-api-records-et-iso-19139",
    "domaine": "Catalogue",
    "fonctionnalite": "OGC API Records et fiche ISO 19139",
    "description": "OGC API Records Part 1 sur le catalogue d'items (/v1/records : landing, conformance, collection « catalog », items paginés q/bbox/type, détail ; anonyme = publié seulement, authentifié = can()) ; fiche ISO 19139 (gmd) par collection, mots-clés et thème INSPIRE. AUD-047/048, D11.",
    "preuve": ["core/app/records/routes.py", "core/app/records/iso19139.py", "core/tests/test_records_routes.py", "core/tests/test_records_iso19139.py"],
    "surfaces": {"rest": [
        "GET /v1/collections/{collection_id}/metadata",
        "GET /v1/records",
        "GET /v1/records/collections",
        "GET /v1/records/collections/{catalog_id}",
        "GET /v1/records/collections/{catalog_id}/items",
        "GET /v1/records/collections/{catalog_id}/items/{record_id}",
        "GET /v1/records/conformance",
    ], "mcp": [], "shell": [], "autre": []},
    "publiques": [
        "GET /v1/records",
        "GET /v1/records/collections",
        "GET /v1/records/collections/{catalog_id}",
        "GET /v1/records/collections/{catalog_id}/items",
        "GET /v1/records/collections/{catalog_id}/items/{record_id}",
        "GET /v1/records/conformance",
    ],
    "garde_auto_scopee": ["GET /v1/collections/{collection_id}/metadata"],
    "priorite": "moyenne",
    "priorite_source": "manuel-lot-l6",
    "note_sp42": "Entrée créée par le lot L6 (audit 2026-10-16).",
    "note_sp42_date": "2026-10-17",
})
with open(p, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
EOF
```

Puis, à la main (lecture préalable de chaque ligne) : ligne 255 (moissonnage) — ajouter « udata (data.gouv.fr) » à la liste des connecteurs de la `description` et `core/app/harvest/connectors/udata.py` aux `preuve` ; ligne 324 (WMS) — ajouter « WMS 1.1.1, GetLegendGraphic, CRS CC42-50 et outre-mer » à la `description` ; ligne 259 (instance) — ajouter `externalBasemapsEnabled` à la liste des capacités si la description les énumère. Vérifier que chaque ligne reste un JSON valide : `python3 -c "import json; [json.loads(l) for l in open('docs/revue/inventaire-fonctionnalites.jsonl')]"`.

- [ ] **Step 2: Portes** :

```bash
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types && git diff --stat -- ../core/openapi.json src/api/generated
cd ../core && CORE_TEST_DATABASE_URL=… uv run pytest
PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
cd ../shell && npm run lint && npm run format:check && npm run test && npm run build && npm run e2e
```

Attendu : tout vert ; diff OpenAPI vide (déjà régénéré tâche par tâche). Un rouge E2E est réel (CLAUDE.md : plus d'échec « connu »). Échecs intermittents documentés à rejouer isolément avant imputation : `test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented`.

- [ ] **Step 3: Jumelles (piège n°14)** — relire la section « Jumelles » de chaque tâche et confirmer par `grep` : `_DEFAULT_BASEMAP_STYLE` absent ; `oas30` absent de `core/app` ; `{z}/{x}/{y}` absent des gabarits OGC Tiles (`grep -rn "tileCol}}/{{tileRow" core/app` vide) ; `CORE_EXTERNAL_BASEMAPS_ENABLED` présent dans `core` **et** `worker` (`docker compose config | grep -n EXTERNAL_BASEMAPS` → 2 occurrences). Reporter au contrôleur, sans les traiter : `reader.ckan` sur data.gouv.fr, `/public/items/{id}` sans filtre `deprecated`, `PipelinePreviewMap` (L7), STAC `keywords`, gabarits swipe.

- [ ] **Step 4: Commit**

```bash
git add docs/revue/inventaire-fonctionnalites.jsonl
git commit -m "chore(docs): inventaire des surfaces du lot L6 (Records, queryables, Tiles/TMS)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Clôture documentaire (`CLAUDE.md § Livré`, historique d'exécution, backlog/gaps, bilan `--write`) : **par le contrôleur**, hors de ce plan.

