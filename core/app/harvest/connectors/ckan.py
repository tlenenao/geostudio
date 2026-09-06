# SPDX-License-Identifier: Apache-2.0
"""Connecteur CKAN / data.gouv.fr (SP-12g) — cinquième et dernier connecteur
d'A22. package_search JSON REST paginé, pas de package_show en N+1 (§3.1 de
la spec). supports_copy=True (comme STAC/ArcGIS/WFS) : une resource géo
reconnue (GeoJSON/GPKG/SHP zippé) est copiable, CSV exclu (pas de mapping
lat/lon pour la copie moissonnée). HTTP uniquement, zéro I/O DB, parsing
tolérant et borné (même philosophie que StacConnector)."""

import json
import logging
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from app.harvest.connectors.base import HarvestedRecord, HarvestFetchError

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
    "GEOJSON": "harvest.geojson",
    "GPKG": "harvest.gpkg",
    "GEOPACKAGE": "harvest.gpkg",
    "SHP": "harvest.zip",
    "SHAPEFILE": "harvest.zip",
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
                    "ckan harvest: plafond de %d pages pour %s, tronqué",
                    _MAX_CKAN_PAGES,
                    admin_url,
                )
                break
            params = [*base_params, ("start", str(start)), ("rows", str(_PAGE_SIZE))]
            page_url = f"{endpoint}?{urlencode(params)}"
            # La première page (pages==1, start==0) est la racine (GAP-59.2,
            # SP-50) : injoignable/illisible, elle doit être signalée — les
            # pages suivantes (pagination) restent tolérantes (root=False).
            doc = _get_json(client, page_url, root=(pages == 1))
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


def _get_json(client, url: str, *, root: bool = False):
    try:
        response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if root:
            raise HarvestFetchError(
                f"document racine CKAN injoignable ou illisible : {url} ({exc})"
            ) from exc
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
        keywords = (
            [t["name"] for t in tags_raw if isinstance(t, dict) and isinstance(t.get("name"), str)]
            if isinstance(tags_raw, list)
            else []
        )
        bbox = _extract_bbox(pkg.get("extras"))
        external_url = f"{scheme}://{netloc}/dataset/{name or external_id}"
        items_url, copy_filename = _pick_copy_resource(pkg.get("resources"))
        return HarvestedRecord(
            external_id=str(external_id),
            title=title,
            abstract=abstract,
            keywords=keywords,
            bbox=bbox,
            external_url=external_url,
            items_url=items_url,
            copy_filename=copy_filename,
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
