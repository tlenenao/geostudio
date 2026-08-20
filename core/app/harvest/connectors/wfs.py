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
            records.append(
                HarvestedRecord(
                    external_id=f"{base}#{name}",
                    title=ows.child_text(ft, "Title") or name,
                    abstract=ows.child_text(ft, "Abstract") or "",
                    keywords=_ft_keywords(ft),
                    bbox=_ft_bbox(ft),
                    external_url=caps_url,
                    items_url=_getfeature_template(base, name),
                    raster_tiles_url=None,
                )
            )
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
                logger.warning(
                    "wfs harvest: plafond de %d pages pour %s, tronqué",
                    _MAX_COPY_PAGES,
                    record.external_id,
                )
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
                logger.warning(
                    "wfs harvest: plafond de %d entités pour %s, tronqué",
                    _MAX_COPY_FEATURES,
                    record.external_id,
                )
                features = features[:_MAX_COPY_FEATURES]
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
            return [
                float(ll.get("minx")),
                float(ll.get("miny")),
                float(ll.get("maxx")),
                float(ll.get("maxy")),
            ]
        except (TypeError, ValueError):
            pass
    return list(ows._WORLD_BBOX)


def _getfeature_template(base: str, name: str) -> str:
    return (
        f"{base}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeNames={name}&outputFormat=application/json&srsName=EPSG:4326"
    )
