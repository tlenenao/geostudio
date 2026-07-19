# SPDX-License-Identifier: Apache-2.0
"""Connecteur STAC externe (SP-12c) — HTTP uniquement, zéro I/O DB. Parsing
tolérant et borné (§2.7 spec) : un catalogue distant malformé/cyclique/hostile
ne doit jamais faire tomber tout un moissonnage ni bloquer le worker."""
import logging
from collections.abc import Iterable
from urllib.parse import urljoin

import httpx

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_CATALOG_DEPTH = 5
_MAX_COLLECTIONS = 500
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


class StacConnector:
    type = "stac"
    supports_copy = True

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        client = self._client or httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        records: list[HarvestedRecord] = []
        seen_docs: set[str] = set()
        try:
            self._walk(client, url, depth=0, records=records, seen_docs=seen_docs)
        finally:
            if owns_client:
                client.close()
        return records

    def _walk(self, client, url, *, depth, records, seen_docs) -> None:
        if len(records) >= _MAX_COLLECTIONS or url in seen_docs:
            return
        seen_docs.add(url)
        try:
            response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            doc = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("stac harvest: échec de récupération de %s : %s", url, exc)
            return

        if isinstance(doc.get("collections"), list):
            for coll in doc["collections"]:
                if len(records) >= _MAX_COLLECTIONS:
                    return
                record = self._collection_to_record(coll, base_url=url)
                if record is not None:
                    records.append(record)
            return

        doc_type = doc.get("type")
        if doc_type == "Collection":
            record = self._collection_to_record(doc, base_url=url)
            if record is not None:
                records.append(record)
            return

        if doc_type == "Catalog":
            if depth >= _MAX_CATALOG_DEPTH:
                logger.warning("stac harvest: profondeur maximale atteinte à %s", url)
                return
            for link in doc.get("links", []) or []:
                if link.get("rel") != "child" or not link.get("href"):
                    continue
                child_url = urljoin(url, link["href"])
                self._walk(client, child_url, depth=depth + 1, records=records, seen_docs=seen_docs)
                if len(records) >= _MAX_COLLECTIONS:
                    return
            return
        # Type inconnu/absent : document ignoré silencieusement (tolérance §2.7).

    @staticmethod
    def _collection_to_record(coll: dict, *, base_url: str) -> HarvestedRecord | None:
        external_id = coll.get("id")
        if not external_id:
            return None
        title = coll.get("title") or str(external_id)
        abstract = coll.get("description") or ""
        keywords = list(coll.get("keywords") or [])

        bbox = _WORLD_BBOX
        extent = coll.get("extent")
        spatial = extent.get("spatial") if isinstance(extent, dict) else None
        bboxes = spatial.get("bbox") if isinstance(spatial, dict) else None
        if isinstance(bboxes, list) and bboxes and isinstance(bboxes[0], list) and len(bboxes[0]) >= 4:
            bbox = [float(v) for v in bboxes[0][:4]]

        self_href, items_href = None, None
        for link in coll.get("links", []) or []:
            rel, href = link.get("rel"), link.get("href")
            if not href:
                continue
            if rel == "self" and self_href is None:
                self_href = urljoin(base_url, href)
            if rel == "items" and items_href is None:
                items_href = urljoin(base_url, href)

        return HarvestedRecord(
            external_id=str(external_id), title=title, abstract=abstract,
            keywords=keywords, bbox=bbox, external_url=self_href or base_url,
            items_url=items_href,
        )
