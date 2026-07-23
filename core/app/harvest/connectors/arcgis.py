# SPDX-License-Identifier: Apache-2.0
"""Connecteur ArcGIS Feature Service (SP-12d §2) — HTTP uniquement, zéro I/O DB.
Une couche = un jeu de données (§2.1) : chaque couche du FeatureServer devient un
HarvestedRecord. Parsing tolérant et borné (§2.4) : un service malformé/hostile
/géant ne fait jamais tomber le moissonnage ni ne bloque le worker."""
import json
import logging
from collections.abc import Iterable

import httpx
import pyproj
from pyproj.exceptions import ProjError

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_LAYERS = 200
_MAX_DOCUMENTS = 250  # 1 service + N couches ; borne le nombre total de GET
_COPY_PAGE_SIZE = 1000
_MAX_COPY_FEATURES = 200000
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]
_WGS84 = pyproj.CRS.from_epsg(4326)


class ArcgisConnector:
    type = "arcgis"
    supports_copy = True

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

    def _fetch(self, client, service_url: str) -> list[HarvestedRecord]:
        gets = 0
        meta = self._get_json(client, f"{service_url}?f=json")
        gets += 1
        if not isinstance(meta, dict):
            logger.warning("arcgis harvest: réponse service non-objet ignorée à %s", service_url)
            return []
        layers = meta.get("layers")
        if not isinstance(layers, list):
            return []
        keywords = _service_keywords(meta)

        records: list[HarvestedRecord] = []
        for entry in layers[:_MAX_LAYERS]:
            if gets >= _MAX_DOCUMENTS:
                logger.warning("arcgis harvest: plafond de documents atteint à %s", service_url)
                break
            if not isinstance(entry, dict):
                continue
            layer_id = entry.get("id")
            if layer_id is None:
                continue
            layer_url = f"{service_url}/{layer_id}"
            layer_meta = self._get_json(client, f"{layer_url}?f=json")
            gets += 1
            if not isinstance(layer_meta, dict):
                logger.warning("arcgis harvest: couche non-objet ignorée à %s", layer_url)
                continue
            records.append(HarvestedRecord(
                external_id=layer_url,
                title=layer_meta.get("name") or str(layer_id),
                abstract=layer_meta.get("description") or "",
                keywords=keywords,
                bbox=_reproject_extent(layer_meta.get("extent")),
                external_url=layer_url,
                items_url=f"{layer_url}/query?where=1=1&outFields=*&f=geojson",
            ))
        return records

    @staticmethod
    def _get_json(client, url: str):
        try:
            response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("arcgis harvest: échec de récupération de %s : %s", url, exc)
            return None

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        if record.items_url is None:
            return None
        features: list = []
        offset = 0
        while True:
            page_url = (
                f"{record.items_url}"
                f"&resultOffset={offset}&resultRecordCount={_COPY_PAGE_SIZE}"
            )
            try:
                page = http_get(page_url).json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("arcgis harvest: page de copie illisible à %s : %s", page_url, exc)
                break
            if not isinstance(page, dict) or not isinstance(page.get("features"), list):
                logger.warning("arcgis harvest: page de copie malformée à %s, arrêt", page_url)
                break
            page_features = page["features"]
            if not page_features:
                break
            features.extend(page_features)
            offset += len(page_features)
            if len(features) >= _MAX_COPY_FEATURES:
                logger.warning(
                    "arcgis harvest: plafond de %d entités atteint pour %s, tronqué",
                    _MAX_COPY_FEATURES, record.external_id,
                )
                features = features[:_MAX_COPY_FEATURES]
                break
            if not page.get("exceededTransferLimit"):
                break
        collection = {"type": "FeatureCollection", "features": features}
        return json.dumps(collection).encode("utf-8")


def _service_keywords(meta: dict) -> list[str]:
    info = meta.get("documentInfo")
    raw = info.get("Keywords") if isinstance(info, dict) else None
    if isinstance(raw, str) and raw.strip():
        return [k.strip() for k in raw.split(",") if k.strip()]
    return []


def _reproject_extent(extent) -> list[float]:
    if not isinstance(extent, dict):
        return list(_WORLD_BBOX)
    try:
        xmin, ymin = float(extent["xmin"]), float(extent["ymin"])
        xmax, ymax = float(extent["xmax"]), float(extent["ymax"])
    except (KeyError, TypeError, ValueError):
        return list(_WORLD_BBOX)

    sr = extent.get("spatialReference")
    wkid = None
    if isinstance(sr, dict):
        wkid = sr.get("latestWkid") or sr.get("wkid")
    if wkid == 4326:
        return [xmin, ymin, xmax, ymax]
    if wkid is None:
        return list(_WORLD_BBOX)
    try:
        src = pyproj.CRS.from_epsg(int(wkid))
        transformer = pyproj.Transformer.from_crs(src, _WGS84, always_xy=True)
        lon_min, lat_min = transformer.transform(xmin, ymin)
        lon_max, lat_max = transformer.transform(xmax, ymax)
        return [lon_min, lat_min, lon_max, lat_max]
    except (ProjError, ValueError, TypeError) as exc:
        logger.warning("arcgis harvest: reprojection d'emprise échouée (wkid=%s) : %s", wkid, exc)
        return list(_WORLD_BBOX)
