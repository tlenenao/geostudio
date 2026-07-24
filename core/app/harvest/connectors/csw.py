# SPDX-License-Identifier: Apache-2.0
"""Connecteur CSW 2.0.2 (SP-12f) — GetRecords paginé en GET-KVP, ISO19139 en
priorité avec repli Dublin Core si le serveur ne supporte pas l'outputSchema
ISO (un seul essai, décidé une fois pour tout le fetch). Métadonnées pures :
jamais de copie, jamais d'ajout carte (items_url et raster_tiles_url toujours
None). HTTP uniquement, zéro I/O DB, parsing tolérant et borné (ows.py)."""
import logging
from collections.abc import Iterable
from urllib.parse import quote

import httpx

from app.harvest.connectors import ows
from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_MAX_CSW_RECORDS = 500
_MAX_CSW_PAGES = 50
_PAGE_SIZE = 100
_ISO_OUTPUT_SCHEMA = "http://www.isotc211.org/2005/gmd"


class CswConnector:
    type = "csw"
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
        return None  # métadonnées, non copiables (§1 décision 3 de la spec)

    def _first_page(self, client, base_url: str):
        iso_url = _page_url(base_url, start_position=1, iso=True)
        root = _fetch_page(client, iso_url)
        if root is not None and ows.local(root.tag) == "GetRecordsResponse":
            return root, True
        dc_url = _page_url(base_url, start_position=1, iso=False)
        root = _fetch_page(client, dc_url)
        if root is not None and ows.local(root.tag) == "GetRecordsResponse":
            return root, False
        return None, False

    def _fetch(self, client, base_url: str) -> list[HarvestedRecord]:
        root, iso = self._first_page(client, base_url)
        if root is None:
            return []
        extractor = _extract_iso if iso else _extract_dc
        records: list[HarvestedRecord] = []
        start_position = 1
        pages = 0
        while True:
            pages += 1
            _collect(root, base_url, iso, extractor, records)
            if len(records) >= _MAX_CSW_RECORDS:
                break
            next_record = _next_record(root)
            if next_record is None or next_record <= start_position:
                break  # nextRecord=0 (fin) ou n'avance pas (garde-fou de boucle)
            if pages >= _MAX_CSW_PAGES:
                logger.warning(
                    "csw harvest: plafond de %d pages pour %s, tronqué", _MAX_CSW_PAGES, base_url,
                )
                break
            start_position = next_record
            page_url = _page_url(base_url, start_position=start_position, iso=iso)
            next_root = _fetch_page(client, page_url)
            if next_root is None or ows.local(next_root.tag) != "GetRecordsResponse":
                break  # page suivante illisible : résultat partiel conservé (§3.1)
            root = next_root
        return records[:_MAX_CSW_RECORDS]


def _fetch_page(client, url: str):
    try:
        response = client.get(url, timeout=ows._DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("csw harvest: échec de récupération de %s : %s", url, exc)
        return None
    return ows.parse_capabilities(response.content)


def _collect(root, base_url: str, iso: bool, extractor, records: list[HarvestedRecord]) -> None:
    search_results = ows.child(root, "SearchResults")
    if search_results is None:
        return
    tag = "MD_Metadata" if iso else "Record"
    for elem in ows.children(search_results, tag):
        if len(records) >= _MAX_CSW_RECORDS:
            return
        rec = extractor(elem, base_url)
        if rec is not None:
            records.append(rec)


def _next_record(root) -> int | None:
    search_results = ows.child(root, "SearchResults")
    if search_results is None:
        return None
    try:
        return int(search_results.get("nextRecord"))
    except (TypeError, ValueError):
        return None


def _page_url(base_url: str, *, start_position: int, iso: bool) -> str:
    params = ["service=CSW", "version=2.0.2", "request=GetRecords", "resultType=results"]
    if iso:
        params += [
            f"outputSchema={quote(_ISO_OUTPUT_SCHEMA, safe='')}",
            "elementSetName=full",
            "typeNames=gmd:MD_Metadata",
        ]
    else:
        params.append("elementSetName=full")
    params += [f"startPosition={start_position}", f"maxRecords={_PAGE_SIZE}"]
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}{'&'.join(params)}"


def _record_by_id_url(base_url: str, identifier: str, *, iso: bool) -> str:
    params = ["service=CSW", "version=2.0.2", "request=GetRecordById", f"id={quote(identifier, safe='')}"]
    if iso:
        params.append(f"outputSchema={quote(_ISO_OUTPUT_SCHEMA, safe='')}")
    params.append("elementSetName=full")
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}{'&'.join(params)}"


def _first_descendant_text(elem, name: str) -> str | None:
    for d in ows.descendants(elem, name):
        text = ows.child_text(d, "CharacterString")
        if text is not None:
            return text
    return None


def _decimal_child(elem, name: str) -> float:
    wrapper = ows.child(elem, name)
    text = ows.child_text(wrapper, "Decimal") if wrapper is not None else None
    return float(text)


def _iso_bbox(elem) -> list[float]:
    ex = next(ows.descendants(elem, "EX_GeographicBoundingBox"), None)
    if ex is None:
        return list(ows._WORLD_BBOX)
    try:
        return [
            _decimal_child(ex, "westBoundLongitude"),
            _decimal_child(ex, "southBoundLatitude"),
            _decimal_child(ex, "eastBoundLongitude"),
            _decimal_child(ex, "northBoundLatitude"),
        ]
    except (TypeError, ValueError):
        return list(ows._WORLD_BBOX)


def _extract_iso(elem, base_url: str) -> HarvestedRecord | None:
    fid = ows.child(elem, "fileIdentifier")
    identifier = ows.child_text(fid, "CharacterString") if fid is not None else None
    if not identifier:
        return None
    title = _first_descendant_text(elem, "title") or identifier
    abstract = _first_descendant_text(elem, "abstract") or ""
    keywords = [
        text for kw in ows.descendants(elem, "keyword")
        if (text := ows.child_text(kw, "CharacterString")) is not None
    ]
    return HarvestedRecord(
        external_id=identifier, title=title, abstract=abstract, keywords=keywords,
        bbox=_iso_bbox(elem), external_url=_record_by_id_url(base_url, identifier, iso=True),
        items_url=None, raster_tiles_url=None,
    )


def _dc_bbox(elem) -> list[float]:
    for tag in ("BoundingBox", "WGS84BoundingBox"):
        box = ows.child(elem, tag)
        if box is None:
            continue
        lower = ows.child_text(box, "LowerCorner")
        upper = ows.child_text(box, "UpperCorner")
        try:
            xmin, ymin = (float(v) for v in lower.split())
            xmax, ymax = (float(v) for v in upper.split())
            return [xmin, ymin, xmax, ymax]
        except (AttributeError, TypeError, ValueError):
            continue
    return list(ows._WORLD_BBOX)


def _extract_dc(elem, base_url: str) -> HarvestedRecord | None:
    identifier = ows.child_text(elem, "identifier")
    if not identifier:
        return None
    title = ows.child_text(elem, "title") or identifier
    abstract = ows.child_text(elem, "abstract") or ows.child_text(elem, "description") or ""
    keywords = [c.text.strip() for c in ows.children(elem, "subject") if c.text and c.text.strip()]
    return HarvestedRecord(
        external_id=identifier, title=title, abstract=abstract, keywords=keywords,
        bbox=_dc_bbox(elem), external_url=_record_by_id_url(base_url, identifier, iso=False),
        items_url=None, raster_tiles_url=None,
    )
