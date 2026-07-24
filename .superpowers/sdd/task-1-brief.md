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

