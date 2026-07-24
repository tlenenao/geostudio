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
    initial_items_url = f"{root_url}/collections/{collection_id}/items?limit=100"
    page_url = initial_items_url
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
            rec = _feature_to_record(feature, page_url, initial_items_url)
            if rec is not None:
                records.append(rec)
        if len(records) >= _MAX_OGC_RECORDS:
            return
        page_url = _next_link(doc, page_url)


def _feature_to_record(feature: object, page_url: str, fallback_url: str) -> HarvestedRecord | None:
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
            bbox=bbox, external_url=self_href or fallback_url, items_url=None, raster_tiles_url=None,
        )
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        logger.warning("ogc-records harvest: feature malformée ignorée à %s : %s", page_url, exc)
        return None
