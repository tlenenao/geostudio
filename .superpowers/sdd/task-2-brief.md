## Task 2: Connecteur OGC API - Records (`OgcRecordsConnector`)

**Files:**
- Create: `core/app/harvest/connectors/ogc_records.py`
- Test: `core/tests/test_harvest_ogc_records_connector.py`

**Interfaces:**
- Consumes : `app.harvest.connectors.base.HarvestedRecord` ;
  `app.harvest.egress.build_guarded_client` (import différé).
- Produces : classe `OgcRecordsConnector` (`type = "ogc-records"`,
  `supports_copy = False`, `fetch(url) -> Iterable[HarvestedRecord]`,
  `fetch_copy_geojson(record, *, http_get) -> None`), consommée par la Task 3
  (registre) et les tests E2E (Task 5).

- [ ] **Step 1: Écrire le fichier de tests (RED)**

Créer `core/tests/test_harvest_ogc_records_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.ogc_records import OgcRecordsConnector

OGC_ROOT = "https://records.example.com/api"

COLLECTIONS = {"collections": [{"id": "buildings"}, {"id": "roads"}]}

ITEMS_BUILDINGS_P1 = {
    "type": "FeatureCollection",
    "features": [
        {
            "id": "rec-1",
            "properties": {
                "title": "Batiments centre-ville", "description": "Empreintes",
                "keywords": ["bati", "centre"],
            },
            "bbox": [1.0, 45.0, 2.0, 46.0],
            "links": [{"rel": "self", "href": "https://records.example.com/api/collections/buildings/items/rec-1"}],
        },
    ],
    "links": [{"rel": "next", "href": "https://records.example.com/api/collections/buildings/items?limit=100&offset=100"}],
}
ITEMS_BUILDINGS_P2 = {
    "type": "FeatureCollection",
    "features": [{"id": "rec-2", "properties": {"title": "Batiments peripherie"}}],
    "links": [],
}
ITEMS_ROADS_P1 = {
    "type": "FeatureCollection",
    "features": [{"id": "rec-3", "properties": {"title": "Routes"}}],
    "links": [],
}


def _connector(handler) -> OgcRecordsConnector:
    return OgcRecordsConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_collections_and_items_maps_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=COLLECTIONS)
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(200, json=ITEMS_BUILDINGS_P1)
        if url == "https://records.example.com/api/collections/buildings/items?limit=100&offset=100":
            return httpx.Response(200, json=ITEMS_BUILDINGS_P2)
        if url == f"{OGC_ROOT}/collections/roads/items?limit=100":
            return httpx.Response(200, json=ITEMS_ROADS_P1)
        raise AssertionError(f"unexpected url {url}")

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-1", "rec-2", "rec-3"}

    rec1 = next(r for r in records if r.external_id == "rec-1")
    assert rec1.title == "Batiments centre-ville"
    assert rec1.abstract == "Empreintes"
    assert rec1.keywords == ["bati", "centre"]
    assert rec1.bbox == [1.0, 45.0, 2.0, 46.0]
    assert rec1.external_url == "https://records.example.com/api/collections/buildings/items/rec-1"
    assert rec1.items_url is None
    assert rec1.raster_tiles_url is None

    rec2 = next(r for r in records if r.external_id == "rec-2")
    assert rec2.title == "Batiments peripherie"
    assert rec2.abstract == ""
    assert rec2.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert rec2.external_url == f"{OGC_ROOT}/collections/buildings/items?limit=100"


def test_root_url_trailing_slash_is_stripped():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{OGC_ROOT}/collections"
        return httpx.Response(200, json={"collections": []})

    assert list(_connector(handler).fetch(f"{OGC_ROOT}/")) == []


def test_malformed_collections_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert list(_connector(handler).fetch(OGC_ROOT)) == []


def test_collection_first_page_failure_is_ignored_others_continue():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=COLLECTIONS)
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(500)
        if url == f"{OGC_ROOT}/collections/roads/items?limit=100":
            return httpx.Response(200, json=ITEMS_ROADS_P1)
        raise AssertionError(url)

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-3"}


def test_next_page_failure_keeps_partial_for_collection():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "buildings"}]})
        if url == f"{OGC_ROOT}/collections/buildings/items?limit=100":
            return httpx.Response(200, json=ITEMS_BUILDINGS_P1)
        return httpx.Response(500)  # page suivante (offset=100) echoue

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert {r.external_id for r in records} == {"rec-1"}


def test_feature_without_id_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "x"}]})
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"properties": {"title": "no id"}}],
            "links": [],
        })

    assert list(_connector(handler).fetch(OGC_ROOT)) == []


def test_pages_per_collection_capped():
    from app.harvest.connectors.ogc_records import _MAX_OGC_PAGES_PER_COLLECTION

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json={"collections": [{"id": "x"}]})
        calls["n"] += 1
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"id": f"r{calls['n']}"}],
            "links": [{"rel": "next", "href": f"{OGC_ROOT}/collections/x/items?limit=100&offset={calls['n']}"}],
        })

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert calls["n"] <= _MAX_OGC_PAGES_PER_COLLECTION
    assert len(records) == calls["n"]


def test_collections_capped_at_max():
    from app.harvest.connectors.ogc_records import _MAX_OGC_COLLECTIONS

    many = {"collections": [{"id": f"c{i}"} for i in range(80)]}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{OGC_ROOT}/collections":
            return httpx.Response(200, json=many)
        cid = url.split("/collections/")[1].split("/items")[0]
        return httpx.Response(200, json={
            "type": "FeatureCollection", "features": [{"id": f"{cid}-rec"}], "links": [],
        })

    records = list(_connector(handler).fetch(OGC_ROOT))
    assert len(records) == _MAX_OGC_COLLECTIONS


def test_fetch_copy_geojson_is_none():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=None,
    )
    assert OgcRecordsConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_ogc_records_connector.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.connectors.ogc_records'`

- [ ] **Step 3: Implémenter `OgcRecordsConnector`**

Créer `core/app/harvest/connectors/ogc_records.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur OGC API - Records (SP-12f) — chemins fixes /collections et
/collections/{id}/items (pas de découverte via les `links` de la page
d'accueil, §4.1 de la spec). Pagination JSON via `links[rel="next"]`.
Métadonnées pures : jamais de copie, jamais d'ajout carte (items_url et
raster_tiles_url toujours None). HTTP uniquement, zéro I/O DB, parsing
tolérant et borné (même philosophie que StacConnector)."""
import logging
from collections.abc import Iterable
from urllib.parse import urljoin

import httpx

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_OGC_COLLECTIONS = 50
_MAX_OGC_PAGES_PER_COLLECTION = 50
_MAX_OGC_RECORDS = 500
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


class OgcRecordsConnector:
    type = "ogc-records"
    supports_copy = False

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url.rstrip("/"))
        finally:
            if owns_client:
                client.close()

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        return None  # métadonnées, non copiables (§1 décision 3 de la spec)

    def _fetch(self, client, root_url: str) -> list[HarvestedRecord]:
        records: list[HarvestedRecord] = []
        for collection_id in _list_collections(client, root_url):
            if len(records) >= _MAX_OGC_RECORDS:
                break
            _collect_collection(client, root_url, collection_id, records)
        return records[:_MAX_OGC_RECORDS]


def _get_json(client, url: str):
    try:
        response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ogc-records harvest: échec de récupération de %s : %s", url, exc)
        return None


def _list_collections(client, root_url: str) -> list[str]:
    doc = _get_json(client, f"{root_url}/collections")
    if not isinstance(doc, dict) or not isinstance(doc.get("collections"), list):
        return []
    ids: list[str] = []
    for coll in doc["collections"]:
        if len(ids) >= _MAX_OGC_COLLECTIONS:
            break
        if isinstance(coll, dict) and coll.get("id"):
            ids.append(str(coll["id"]))
    return ids


def _next_link(doc: dict, current_url: str) -> str | None:
    links = doc.get("links")
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "next" and link.get("href"):
            return urljoin(current_url, link["href"])
    return None


def _collect_collection(client, root_url: str, collection_id: str, records: list[HarvestedRecord]) -> None:
    page_url = f"{root_url}/collections/{collection_id}/items?limit=100"
    pages = 0
    while page_url is not None:
        pages += 1
        if pages > _MAX_OGC_PAGES_PER_COLLECTION:
            logger.warning(
                "ogc-records harvest: plafond de %d pages pour la collection %s, tronqué",
                _MAX_OGC_PAGES_PER_COLLECTION, collection_id,
            )
            return
        doc = _get_json(client, page_url)
        if not isinstance(doc, dict) or not isinstance(doc.get("features"), list):
            return  # 1re page illisible: collection ignorée ; page suivante: partiel conservé (§4.1)
        for feature in doc["features"]:
            if len(records) >= _MAX_OGC_RECORDS:
                return
            rec = _feature_to_record(feature, page_url)
            if rec is not None:
                records.append(rec)
        if len(records) >= _MAX_OGC_RECORDS:
            return
        page_url = _next_link(doc, page_url)


def _feature_to_record(feature: object, page_url: str) -> HarvestedRecord | None:
    if not isinstance(feature, dict):
        logger.warning("ogc-records harvest: entrée feature non-objet ignorée à %s", page_url)
        return None
    try:
        external_id = feature.get("id")
        if not external_id:
            return None
        props = feature.get("properties")
        props = props if isinstance(props, dict) else {}
        title = props.get("title") or str(external_id)
        abstract = props.get("description") or ""
        keywords_raw = props.get("keywords")
        keywords = list(keywords_raw) if isinstance(keywords_raw, list) else []

        bbox = list(_WORLD_BBOX)
        bbox_raw = feature.get("bbox")
        if isinstance(bbox_raw, list) and len(bbox_raw) >= 4:
            bbox = [float(v) for v in bbox_raw[:4]]

        self_href = None
        for link in feature.get("links", []) or []:
            if isinstance(link, dict) and link.get("rel") == "self" and link.get("href"):
                self_href = urljoin(page_url, link["href"])
                break

        return HarvestedRecord(
            external_id=str(external_id), title=title, abstract=abstract, keywords=keywords,
            bbox=bbox, external_url=self_href or page_url, items_url=None, raster_tiles_url=None,
        )
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        logger.warning("ogc-records harvest: feature malformée ignorée à %s : %s", page_url, exc)
        return None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_ogc_records_connector.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/connectors/ogc_records.py core/tests/test_harvest_ogc_records_connector.py
git commit -m "feat(core): connecteur de moissonnage OGC API - Records (SP-12f)"
```

---

