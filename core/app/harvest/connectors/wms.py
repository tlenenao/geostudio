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
        own_crs = _layer_crs(layer)
        # If layer declares own CRS, use only those; otherwise inherit from parent
        crs = own_crs if own_crs else inherited_crs
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
