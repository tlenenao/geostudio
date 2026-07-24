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

