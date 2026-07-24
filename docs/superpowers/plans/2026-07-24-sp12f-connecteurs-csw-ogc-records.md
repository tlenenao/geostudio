# SP-12f — Connecteurs CSW 2.0.2 et OGC API - Records — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer deux connecteurs de moissonnage référencement-pur — `csw`
(CSW 2.0.2, ISO19139 avec repli Dublin Core) et `ogc-records` (OGC API -
Records, JSON REST) — branchés sur le `HarvestConnector` existant, avec leur
UI d'administration et leurs E2E.

**Architecture:** Deux nouveaux fichiers dans `core/app/harvest/connectors/`
(`csw.py` réutilise le module XML partagé `ows.py` de SP-12e ; `ogc_records.py`
suit le style JSON tolérant de `stac.py`), enregistrés dans `_REGISTRY` et le
`Literal` de `schemas.py`. Aucune migration Alembic (les colonnes
`tiles_url`/`layer_kind` de SP-12e restent `NULL` pour ces deux connecteurs).
Shell : deux nouvelles options dans `CreateHarvestSourceDialog`, mode copie
grisé pour les deux (ni l'un ni l'autre dans `supports_copy`).

**Tech Stack:** Python/FastAPI (`core/`), `httpx` (client HTTP gardé),
`defusedxml` (déjà dépendance depuis SP-12e), React/TypeScript (`shell/`),
Playwright (E2E, mode mock).

## Global Constraints

- GET-KVP uniquement pour CSW (pas de POST-XML `csw:GetRecords`).
- `supports_copy = False` pour les **deux** connecteurs — jamais dans
  `COPY_TYPES` côté shell, jamais accepté en mode `copy` côté API (via
  `connector.supports_copy`, déjà branché dans `routes.py::_check_copy_support`).
- `items_url = None` et `raster_tiles_url = None` toujours pour les deux
  connecteurs (métadonnées pures, aucun affichage carte).
- Bornes CSW : `_MAX_CSW_RECORDS = 500`, `_MAX_CSW_PAGES = 50`, timeout 10 s/page.
- Bornes OGC API - Records : `_MAX_OGC_COLLECTIONS = 50`,
  `_MAX_OGC_PAGES_PER_COLLECTION = 50`, `_MAX_OGC_RECORDS = 500`, timeout 10 s/requête.
- OGC API - Records : chemins fixes `/collections` et `/collections/{id}/items`
  uniquement — pas de découverte via les `links` de la page d'accueil.
- Toutes les requêtes passent par le client d'egress gardé
  (`build_guarded_client`), construit en interne par chaque connecteur.
- Contrat harvest : un connecteur ne lève **jamais** — toute erreur réseau/XML/JSON
  est loggée et donne un résultat vide ou partiel, jamais une exception qui fuite.
- Aucune migration Alembic dans SP-12f.

---

## Task 1: Connecteur CSW (`CswConnector`)

**Files:**
- Create: `core/app/harvest/connectors/csw.py`
- Test: `core/tests/test_harvest_csw_connector.py`

**Interfaces:**
- Consumes : `app.harvest.connectors.ows` (`parse_capabilities`, `local`,
  `children`, `child`, `child_text`, `descendants`, `_DEFAULT_TIMEOUT_SECONDS`,
  `_WORLD_BBOX`) ; `app.harvest.connectors.base.HarvestedRecord` ;
  `app.harvest.egress.build_guarded_client` (import différé, comme les autres
  connecteurs).
- Produces : classe `CswConnector` (`type = "csw"`, `supports_copy = False`,
  `fetch(url) -> Iterable[HarvestedRecord]`,
  `fetch_copy_geojson(record, *, http_get) -> None`), consommée par la Task 3
  (registre) et les tests E2E (Task 5).

- [ ] **Step 1: Écrire le fichier de tests (RED)**

Créer `core/tests/test_harvest_csw_connector.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import httpx

from app.harvest.connectors.base import HarvestedRecord
from app.harvest.connectors.csw import CswConnector

CSW_BASE = "https://geonetwork.example.com/geonetwork/srv/eng/csw"

ISO_PAGE_1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
    xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <csw:SearchStatus timestamp="2026-07-24T10:00:00Z"/>
  <csw:SearchResults numberOfRecordsMatched="1" numberOfRecordsReturned="1" nextRecord="0" recordSchema="http://www.isotc211.org/2005/gmd">
    <gmd:MD_Metadata>
      <gmd:fileIdentifier><gco:CharacterString>iso-1</gco:CharacterString></gmd:fileIdentifier>
      <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
          <gmd:citation>
            <gmd:CI_Citation>
              <gmd:title><gco:CharacterString>Batiments</gco:CharacterString></gmd:title>
            </gmd:CI_Citation>
          </gmd:citation>
          <gmd:abstract><gco:CharacterString>Empreintes de batiments</gco:CharacterString></gmd:abstract>
          <gmd:descriptiveKeywords>
            <gmd:MD_Keywords>
              <gmd:keyword><gco:CharacterString>bati</gco:CharacterString></gmd:keyword>
              <gmd:keyword><gco:CharacterString>urbain</gco:CharacterString></gmd:keyword>
            </gmd:MD_Keywords>
          </gmd:descriptiveKeywords>
          <gmd:extent>
            <gmd:EX_Extent>
              <gmd:geographicElement>
                <gmd:EX_GeographicBoundingBox>
                  <gmd:westBoundLongitude><gco:Decimal>1.0</gco:Decimal></gmd:westBoundLongitude>
                  <gmd:eastBoundLongitude><gco:Decimal>2.0</gco:Decimal></gmd:eastBoundLongitude>
                  <gmd:southBoundLatitude><gco:Decimal>45.0</gco:Decimal></gmd:southBoundLatitude>
                  <gmd:northBoundLatitude><gco:Decimal>46.0</gco:Decimal></gmd:northBoundLatitude>
                </gmd:EX_GeographicBoundingBox>
              </gmd:geographicElement>
            </gmd:EX_Extent>
          </gmd:extent>
        </gmd:MD_DataIdentification>
      </gmd:identificationInfo>
    </gmd:MD_Metadata>
  </csw:SearchResults>
</csw:GetRecordsResponse>"""

ISO_NO_BBOX = b"""<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
    xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <csw:SearchResults numberOfRecordsMatched="1" numberOfRecordsReturned="1" nextRecord="0">
    <gmd:MD_Metadata>
      <gmd:fileIdentifier><gco:CharacterString>iso-nobbox</gco:CharacterString></gmd:fileIdentifier>
    </gmd:MD_Metadata>
  </csw:SearchResults>
</csw:GetRecordsResponse>"""

NO_ID_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
    xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <csw:SearchResults numberOfRecordsMatched="1" numberOfRecordsReturned="1" nextRecord="0">
    <gmd:MD_Metadata>
      <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
          <gmd:citation><gmd:CI_Citation><gmd:title><gco:CharacterString>Sans identifiant</gco:CharacterString></gmd:title></gmd:CI_Citation></gmd:citation>
        </gmd:MD_DataIdentification>
      </gmd:identificationInfo>
    </gmd:MD_Metadata>
  </csw:SearchResults>
</csw:GetRecordsResponse>"""

EXCEPTION_REPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows" version="1.2.0">
  <ows:Exception exceptionCode="InvalidParameterValue" locator="outputSchema">
    <ows:ExceptionText>outputSchema non supporte</ows:ExceptionText>
  </ows:Exception>
</ows:ExceptionReport>"""

DC_PAGE_1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
    xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dct="http://purl.org/dc/terms/"
    xmlns:ows="http://www.opengis.net/ows">
  <csw:SearchResults numberOfRecordsMatched="1" numberOfRecordsReturned="1" nextRecord="0">
    <csw:Record>
      <dc:identifier>dc-1</dc:identifier>
      <dc:title>Parcelles</dc:title>
      <dct:abstract>Parcelles cadastrales</dct:abstract>
      <dc:subject>cadastre</dc:subject>
      <dc:subject>foncier</dc:subject>
      <ows:BoundingBox>
        <ows:LowerCorner>3.0 47.0</ows:LowerCorner>
        <ows:UpperCorner>4.0 48.0</ows:UpperCorner>
      </ows:BoundingBox>
    </csw:Record>
  </csw:SearchResults>
</csw:GetRecordsResponse>"""

XXE_BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"><title>&xxe;</title></csw:GetRecordsResponse>"""


def _connector(handler) -> CswConnector:
    return CswConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


def _iso_page(identifier: str, next_record: int) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"
    xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <csw:SearchResults numberOfRecordsMatched="2" numberOfRecordsReturned="1" nextRecord="{next_record}">
    <gmd:MD_Metadata>
      <gmd:fileIdentifier><gco:CharacterString>{identifier}</gco:CharacterString></gmd:fileIdentifier>
      <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
          <gmd:citation><gmd:CI_Citation><gmd:title><gco:CharacterString>{identifier}-title</gco:CharacterString></gmd:title></gmd:CI_Citation></gmd:citation>
        </gmd:MD_DataIdentification>
      </gmd:identificationInfo>
    </gmd:MD_Metadata>
  </csw:SearchResults>
</csw:GetRecordsResponse>""".encode()


def test_iso_single_page_extracts_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "outputSchema=http%3A%2F%2Fwww.isotc211.org%2F2005%2Fgmd" in str(request.url)
        return httpx.Response(200, content=ISO_PAGE_1)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "iso-1"
    assert rec.title == "Batiments"
    assert rec.abstract == "Empreintes de batiments"
    assert rec.keywords == ["bati", "urbain"]
    assert rec.bbox == [1.0, 45.0, 2.0, 46.0]
    assert rec.items_url is None
    assert rec.raster_tiles_url is None
    assert "request=GetRecordById" in rec.external_url
    assert "id=iso-1" in rec.external_url


def test_iso_record_without_bbox_defaults_to_world():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ISO_NO_BBOX)

    rec = list(_connector(handler).fetch(CSW_BASE))[0]
    assert rec.title == "iso-nobbox"  # pas de <title> trouve -> repli sur l'identifiant
    assert rec.bbox == [-180.0, -90.0, 180.0, 90.0]


def test_pagination_advances_via_next_record_and_stops_at_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        qs = str(request.url)
        if "startPosition=1" in qs:
            return httpx.Response(200, content=_iso_page("iso-1", next_record=2))
        if "startPosition=2" in qs:
            return httpx.Response(200, content=_iso_page("iso-2", next_record=0))
        raise AssertionError(f"unexpected page request: {qs}")

    records = list(_connector(handler).fetch(CSW_BASE))
    assert [r.external_id for r in records] == ["iso-1", "iso-2"]


def test_loop_guard_stops_when_next_record_does_not_advance():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        qs = str(request.url)
        if "startPosition=1" in qs:
            return httpx.Response(200, content=_iso_page("iso-1", next_record=5))
        return httpx.Response(200, content=_iso_page("iso-5", next_record=5))  # ne progresse plus

    records = list(_connector(handler).fetch(CSW_BASE))
    assert calls["n"] == 2
    assert [r.external_id for r in records] == ["iso-1", "iso-5"]


def test_pages_capped_at_max_pages():
    from app.harvest.connectors.csw import _MAX_CSW_PAGES

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        start = int(str(request.url).split("startPosition=")[1].split("&")[0])
        return httpx.Response(200, content=_iso_page(f"iso-{start}", next_record=start + 1))

    records = list(_connector(handler).fetch(CSW_BASE))
    assert calls["n"] <= _MAX_CSW_PAGES
    assert len(records) == _MAX_CSW_PAGES


def test_records_capped_at_max_within_single_page():
    from app.harvest.connectors.csw import _MAX_CSW_RECORDS

    blocks = "".join(
        f'<gmd:MD_Metadata><gmd:fileIdentifier><gco:CharacterString>iso-{i}</gco:CharacterString></gmd:fileIdentifier></gmd:MD_Metadata>'
        for i in range(600)
    )
    page = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2" '
        'xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<csw:SearchResults numberOfRecordsMatched="600" numberOfRecordsReturned="600" nextRecord="0">'
        f"{blocks}"
        "</csw:SearchResults></csw:GetRecordsResponse>"
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=page)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert len(records) == _MAX_CSW_RECORDS


def test_exception_report_on_first_page_falls_back_to_dublin_core():
    def handler(request: httpx.Request) -> httpx.Response:
        if "outputSchema=" in str(request.url):
            return httpx.Response(200, content=EXCEPTION_REPORT)
        return httpx.Response(200, content=DC_PAGE_1)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "dc-1"
    assert rec.title == "Parcelles"
    assert rec.abstract == "Parcelles cadastrales"
    assert rec.keywords == ["cadastre", "foncier"]
    assert rec.bbox == [3.0, 47.0, 4.0, 48.0]
    assert "request=GetRecordById" in rec.external_url
    assert "outputSchema=" not in rec.external_url


def test_malformed_first_page_falls_back_to_dublin_core():
    def handler(request: httpx.Request) -> httpx.Response:
        if "outputSchema=" in str(request.url):
            return httpx.Response(200, content=b"<broken")
        return httpx.Response(200, content=DC_PAGE_1)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert [r.external_id for r in records] == ["dc-1"]


def test_xxe_on_first_page_neutralised_and_falls_back_to_dublin_core():
    def handler(request: httpx.Request) -> httpx.Response:
        if "outputSchema=" in str(request.url):
            return httpx.Response(200, content=XXE_BOMB)
        return httpx.Response(200, content=DC_PAGE_1)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert [r.external_id for r in records] == ["dc-1"]


def test_both_attempts_fail_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert list(_connector(handler).fetch(CSW_BASE)) == []


def test_next_page_failure_keeps_partial_results():
    def handler(request: httpx.Request) -> httpx.Response:
        if "startPosition=1" in str(request.url):
            return httpx.Response(200, content=_iso_page("iso-1", next_record=2))
        return httpx.Response(500)

    records = list(_connector(handler).fetch(CSW_BASE))
    assert [r.external_id for r in records] == ["iso-1"]


def test_record_without_identifier_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=NO_ID_PAGE)

    assert list(_connector(handler).fetch(CSW_BASE)) == []


def test_fetch_copy_geojson_is_none():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=None,
    )
    assert CswConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'app.harvest.connectors.csw'`

- [ ] **Step 3: Implémenter `CswConnector`**

Créer `core/app/harvest/connectors/csw.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/connectors/csw.py core/tests/test_harvest_csw_connector.py
git commit -m "feat(core): connecteur de moissonnage CSW 2.0.2 (ISO19139 + repli DC) (SP-12f)"
```

---

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

## Task 3: Registre, schémas, routes et openapi.json

**Files:**
- Modify: `core/app/harvest/connectors/__init__.py`
- Modify: `core/app/harvest/schemas.py`
- Modify: `core/tests/test_harvest_csw_connector.py` (ajout `test_get_connector_returns_csw`)
- Modify: `core/tests/test_harvest_ogc_records_connector.py` (ajout `test_get_connector_returns_ogc_records`)
- Modify: `core/tests/test_harvest_routes.py`
- Modify: `core/tests/test_harvest_service.py`
- Modify: `core/openapi.json` (régénéré)

**Interfaces:**
- Consumes : `CswConnector` (Task 1), `OgcRecordsConnector` (Task 2).
- Produces : `get_connector("csw")` / `get_connector("ogc-records")`
  fonctionnels ; `HarvestSourceCreate.type` accepte `"csw"`/`"ogc-records"` ;
  `openapi.json` à jour, consommé par la Task 4 (régénération `core-schema.d.ts`).

- [ ] **Step 1: Étendre les tests des connecteurs avec `get_connector` (RED)**

Ajouter à la fin de `core/tests/test_harvest_csw_connector.py` :

```python
def test_get_connector_returns_csw():
    from app.harvest.connectors import get_connector

    c = get_connector("csw")
    assert c.type == "csw"
    assert c.supports_copy is False
```

Ajouter à la fin de `core/tests/test_harvest_ogc_records_connector.py` :

```python
def test_get_connector_returns_ogc_records():
    from app.harvest.connectors import get_connector

    c = get_connector("ogc-records")
    assert c.type == "ogc-records"
    assert c.supports_copy is False
```

- [ ] **Step 2: Réécrire les tests de routes autour du nouveau Literal (RED)**

Dans `core/tests/test_harvest_routes.py`, remplacer le test qui utilisait
`"csw"` comme exemple de type inconnu (il devient un type valide) par un type
toujours inexistant, et ajouter la couverture des deux nouveaux types :

```python
def test_create_unknown_type_is_rejected(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": "geonode-legacy", "url": "https://x", "mode": "reference",
    })
    assert resp.status_code == 422


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_create_metadata_source_is_accepted(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": type_, "url": "https://catalog.example.com/x", "mode": "reference",
    })
    assert resp.status_code == 201
    assert resp.json()["type"] == type_


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_copy_mode_rejected_for_metadata_connectors(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post("/harvest/sources", json={
        "type": type_, "url": "https://catalog.example.com/x", "mode": "copy",
    })
    assert resp.status_code == 400
```

- [ ] **Step 3: Ajouter le test service de confirmation NULL (RED)**

Ajouter à `core/tests/test_harvest_service.py`, après `RASTER_REC` (ligne 33) :

```python
METADATA_ONLY_REC = HarvestedRecord(
    external_id="csw#iso-1", title="Batiments", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0],
    external_url="https://geonetwork.example.com/csw?request=GetRecordById&id=iso-1",
    items_url=None,
)
```

Puis ajouter, après `test_reference_persists_tiles_url_and_layer_kind` :

```python
def test_reference_metadata_only_record_has_null_tiles_and_layer_kind(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([METADATA_ONLY_REC]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="csw",
        url="https://geonetwork.example.com/csw", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="csw#iso-1")
    assert rec.tiles_url is None
    assert rec.layer_kind is None
```

- [ ] **Step 4: Lancer les trois fichiers de tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v`
Expected: FAIL — `get_connector("csw")`/`get_connector("ogc-records")` lèvent
`ValueError` ; les créations de source `csw`/`ogc-records` renvoient 422 au
lieu de 201/400.

- [ ] **Step 5: Enregistrer les deux connecteurs**

Modifier `core/app/harvest/connectors/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.csw import CswConnector
from app.harvest.connectors.ogc_records import OgcRecordsConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wfs import WfsConnector
from app.harvest.connectors.wms import WmsConnector
from app.harvest.connectors.wmts import WmtsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
    "wfs": WfsConnector(),
    "wmts": WmtsConnector(),
    "csw": CswConnector(),
    "ogc-records": OgcRecordsConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 6: Étendre le schéma Pydantic**

Modifier `core/app/harvest/schemas.py` ligne 8 :

```python
class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts", "csw", "ogc-records"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)
```

- [ ] **Step 7: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_harvest_csw_connector.py tests/test_harvest_ogc_records_connector.py tests/test_harvest_routes.py tests/test_harvest_service.py -v`
Expected: PASS

- [ ] **Step 8: Lancer la suite harvest complète**

Run: `cd core && uv run pytest tests/ -k harvest -v`
Expected: PASS (tous les tests harvest, y compris ceux inchangés des Tasks 1-2)

- [ ] **Step 9: Régénérer `openapi.json`**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json`
Expected: le fichier `core/openapi.json` est réécrit — `git diff core/openapi.json`
montre `"csw"` et `"ogc-records"` ajoutés à l'énumération du type de
`HarvestSourceCreate`.

- [ ] **Step 10: Commit**

```bash
git add core/app/harvest/connectors/__init__.py core/app/harvest/schemas.py \
  core/tests/test_harvest_csw_connector.py core/tests/test_harvest_ogc_records_connector.py \
  core/tests/test_harvest_routes.py core/tests/test_harvest_service.py core/openapi.json
git commit -m "feat(core): enregistre les connecteurs csw/ogc-records (SP-12f)"
```

---

## Task 4: Shell — types, dialogue de création, tests

**Files:**
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Modify: `shell/src/shell/CreateHarvestSourceDialog.test.tsx`

**Interfaces:**
- Consumes : `core/openapi.json` régénéré (Task 3).
- Produces : `HarvestSourceType` inclut `"csw" | "ogc-records"`, consommé par
  les E2E de la Task 5.

- [ ] **Step 1: Régénérer les types OpenAPI du shell**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` réécrit — `git diff`
montre `"csw"` et `"ogc-records"` ajoutés au type de `HarvestSourceCreate`
(autour de la ligne 1175).

- [ ] **Step 2: Étendre `HarvestSourceType` (RED implicite — TypeScript)**

Modifier `shell/src/api/types.ts` ligne 264 :

```typescript
export type HarvestSourceType = "stac" | "arcgis" | "wms" | "wfs" | "wmts" | "csw" | "ogc-records";
```

- [ ] **Step 3: Écrire les tests du dialogue (RED)**

Ajouter à la fin de `shell/src/shell/CreateHarvestSourceDialog.test.tsx` :

```tsx
test("envoie le type CSW et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "csw",
          url: "https://geonetwork.example.com/csw",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );

  render(<Harness onClose={() => {}} />);
  await userEvent.type(screen.getByLabelText("URL"), "https://geonetwork.example.com/csw");
  // Passer d'abord en copie (autorisé pour STAC), puis basculer en CSW :
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "csw");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(body).toEqual({
      type: "csw",
      url: "https://geonetwork.example.com/csw",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("garde le mode copie désactivé pour OGC API - Records", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })));
  render(<Harness onClose={() => {}} />);
  await userEvent.selectOptions(screen.getByLabelText("Type"), "ogc-records");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(true);
});
```

- [ ] **Step 4: Lancer les tests, vérifier l'échec**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: FAIL — l'option `<option value="csw">` n'existe pas encore dans le
`<select>`, `selectOptions` échoue.

- [ ] **Step 5: Ajouter les deux options au dialogue**

Modifier `shell/src/shell/CreateHarvestSourceDialog.tsx` lignes 53-58 :

```tsx
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
            <option value="wmts">WMTS</option>
            <option value="csw">CSW</option>
            <option value="ogc-records">OGC API - Records</option>
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: PASS (5 tests)

- [ ] **Step 7: Lancer la suite Vitest complète et la vérification de types**

Run: `cd shell && npm test && npm run build`
Expected: PASS (398+ tests) ; `tsc --noEmit` sans erreur.

- [ ] **Step 8: Commit**

```bash
git add shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts \
  shell/src/shell/CreateHarvestSourceDialog.tsx shell/src/shell/CreateHarvestSourceDialog.test.tsx
git commit -m "feat(shell): options CSW / OGC API - Records dans le dialogue de moissonnage (SP-12f)"
```

---

## Task 5: E2E Playwright et documentation

**Files:**
- Create: `shell/e2e/harvest-csw.spec.ts`
- Create: `shell/e2e/harvest-ogc-records.spec.ts`
- Modify: `CLAUDE.md`
- Modify: `docs/vision/2026-07-04-feuille-de-route-geostudio.md`

**Interfaces:**
- Consumes : `CreateHarvestSourceDialog` avec les options `csw`/`ogc-records`
  (Task 4) ; `mockCore` (`shell/e2e/mocks.ts`, inchangé).

- [ ] **Step 1: Écrire le spec E2E CSW**

Créer `shell/e2e/harvest-csw.spec.ts` :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const CSW_URL = "https://geonetwork.example.com/geonetwork/srv/eng/csw";

test("un admin déclare une source CSW, la moissonne, et l'item apparaît au catalogue, cherchable", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "csw", url: CSW_URL, mode: "reference", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "csw", url: CSW_URL, mode: "reference", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("iso-1", {
      pk: "iso-1", resourceType: "external", title: "Batiments cadastraux (CSW distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(CSW_URL);
  await dialog.getByLabel("Type").selectOption("csw");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "csw", url: CSW_URL, mode: "reference", enabled: true,
  });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Batiments cadastraux (CSW distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  const request = page.waitForRequest((req) => req.url().includes("/items?") && req.url().includes("q=cadastraux"));
  await page.getByRole("textbox", { name: "Rechercher" }).fill("cadastraux");
  await request;
  await expect(page.getByText("Batiments cadastraux (CSW distant)")).toBeVisible();
});
```

- [ ] **Step 2: Écrire le spec E2E OGC API - Records**

Créer `shell/e2e/harvest-ogc-records.spec.ts` :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const OGC_URL = "https://records.example.com/api";

test("un admin déclare une source OGC API - Records, la moissonne, et l'item apparaît au catalogue, cherchable", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "ogc-records", url: OGC_URL, mode: "reference", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "ogc-records", url: OGC_URL, mode: "reference", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("rec-1", {
      pk: "rec-1", resourceType: "external", title: "Sentiers de randonnée (OGC Records distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(OGC_URL);
  await dialog.getByLabel("Type").selectOption("ogc-records");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "ogc-records", url: OGC_URL, mode: "reference", enabled: true,
  });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Sentiers de randonnée (OGC Records distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  const request = page.waitForRequest((req) => req.url().includes("/items?") && req.url().includes("q=Sentiers"));
  await page.getByRole("textbox", { name: "Rechercher" }).fill("Sentiers");
  await request;
  await expect(page.getByText("Sentiers de randonnée (OGC Records distant)")).toBeVisible();
});
```

- [ ] **Step 3: Lancer les deux specs E2E**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test harvest-csw harvest-ogc-records`
Expected: PASS (2 specs)

- [ ] **Step 4: Lancer la suite E2E complète (non-régression)**

Run: `cd shell && npm run e2e`
Expected: PASS (20 specs — les 18 existantes + les 2 nouvelles)

- [ ] **Step 5: Mettre à jour `CLAUDE.md`**

Dans `CLAUDE.md`, remplacer le bloc SP-12 de la section « Fait » :

```markdown
- **SP-12** (a→f) — fédération STAC/DCAT : API STAC native (lecture seule),
  export DCAT-AP (JSON-LD), moteur de moissonnage + connecteur STAC externe,
  connecteur ArcGIS FS + garde d'egress SSRF, connecteurs GetCapabilities
  WMS/WFS/WMTS + affichage raster (LayerPicker → `GET /harvest/layers`),
  connecteurs métadonnées CSW 2.0.2 + OGC API - Records (référencement pur,
  parser XML tolérant partagé avec WMS/WFS/WMTS).
```

Et le bloc SP-12 de la section « À venir » :

```markdown
- **SP-12** (g) — dernier connecteur de moissonnage : CKAN/data.gouv.fr
  (abstraction `HarvestConnector` déjà dimensionnée).
```

- [ ] **Step 6: Mettre à jour la feuille de route**

Dans `docs/vision/2026-07-04-feuille-de-route-geostudio.md`, remplacer le
paragraphe « Connecteurs » de la section `### SP-12` (autour de la ligne 591) :

```markdown
- **Connecteurs** (A22 — les cinq retenus, amendé 2026-07-09), *chacun
  livrable séparément* : ① catalogues STAC externes ; ArcGIS Feature Services
  (référencement + copie, inséré en 2ᵉ position) ; ② WMS/WFS/WMTS
  GetCapabilities (référencer un GeoServer existant en secondes) ; ③ CSW/ISO
  19139 (GeoNetwork/geOrchestra — parser tolérant, champs minimaux) **et son
  protocole successeur OGC API - Records** (extension documentée SP-12f,
  2026-07-24) ; ④ CKAN/data.gouv.fr.
```

Et, deux lignes plus bas dans la même section (« Risques »), remplacer
« Quatre connecteurs = risque d'étalement » par « Cinq connecteurs = risque
d'étalement ».

Dans la section `### A22 — Connecteurs de moissonnage v1 (SP-12)` (autour de
la ligne 1050), ajouter après le paragraphe d'amendement 2026-07-09 :

```markdown
> **Extension 2026-07-24 (SP-12f)** : le connecteur ③ (CSW/ISO 19139) livre
> aussi son protocole successeur **OGC API - Records** (JSON/REST), sous le
> même incrément — deux connecteurs distincts au registre (`csw` et
> `ogc-records`), tous deux référencement pur. Ne redéfinit pas l'ordre ni le
> périmètre des cinq connecteurs, documente ce que ③ couvre concrètement (cf.
> `docs/superpowers/specs/2026-07-24-sp12f-connecteurs-csw-ogc-records-design.md`
> §9).
```

Dans le tableau récapitulatif des arbitrages (autour de la ligne 1236),
remplacer la ligne A22 :

```markdown
| A22 | Connecteurs moissonnage | **Les cinq** (amendé 2026-07-09) — ordre : STAC → **ArcGIS FS** → GetCapabilities → CSW/ISO **+ OGC API - Records** (SP-12f, 2026-07-24) → CKAN | SP-12 (réf. comme source de dataset dès SP-14) |
```

- [ ] **Step 7: Commit**

```bash
git add shell/e2e/harvest-csw.spec.ts shell/e2e/harvest-ogc-records.spec.ts \
  CLAUDE.md docs/vision/2026-07-04-feuille-de-route-geostudio.md
git commit -m "test(e2e): admin CSW / OGC API - Records → moissonnage → item cherchable (SP-12f)

docs(vision): SP-12f livré, extension d'A22 ③ à OGC API - Records"
```

---

## Vérification finale

- [ ] **Step 1: Suite complète cœur**

Run: `cd core && uv run pytest`
Expected: PASS (tests précédents + 24 nouveaux : 14 CSW + 8 OGC Records +
1 registre×2 + 3 routes + 1 service — le compte exact peut varier légèrement
selon les tests exécutés en paramétré)

- [ ] **Step 2: Suite complète shell (unitaires + build)**

Run: `cd shell && npm run build && npm test`
Expected: PASS

- [ ] **Step 3: Suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS (20 specs)
