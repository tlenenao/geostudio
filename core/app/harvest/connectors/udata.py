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
            logger.warning(
                "udata harvest: plafond de %d pages pour %s, tronqué", _MAX_PAGES, admin_url
            )
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
