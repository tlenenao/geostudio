# SPDX-License-Identifier: Apache-2.0
"""Connecteur WMTS (SP-12e) — GetCapabilities → un Layer = un record raster,
gabarit {z}/{y}/{x}. N'ajoute à la carte que les couches offrant une matrice
Web Mercator à identifiants de TileMatrix entiers ; sinon référence-only.
HTTP uniquement, zéro I/O DB, parsing tolérant et borné (ows.py)."""

import logging
from collections.abc import Iterable

import httpx

from app.harvest.connectors import ows
from app.harvest.connectors.base import HarvestedRecord, HarvestFetchError

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
            # Racine injoignable (GAP-59.2, SP-50) : seul point d'échec de ce
            # connecteur (un unique appel GetCapabilities), doit être
            # signalé plutôt que rapporté comme un moissonnage réussi à
            # zéro enregistrement.
            raise HarvestFetchError(
                f"document racine WMTS injoignable ou illisible : {caps_url} ({exc})"
            ) from exc
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
    linked = [
        ows.child_text(link, "TileMatrixSet") for link in ows.children(layer, "TileMatrixSetLink")
    ]
    tms = next((t for t in linked if t in mercator_sets), None)
    tiles = _tiles_url(layer, identifier, base, tms) if tms is not None else None
    return HarvestedRecord(
        external_id=f"{base}#{identifier}",
        title=title,
        abstract=abstract,
        keywords=[],
        bbox=bbox,
        external_url=caps_url,
        items_url=None,
        raster_tiles_url=tiles,
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
            resource.replace("{TileMatrix}", "{z}")
            .replace("{TileRow}", "{y}")
            .replace("{TileCol}", "{x}")
            .replace("{Style}", style)
            .replace("{TileMatrixSet}", tms)
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
