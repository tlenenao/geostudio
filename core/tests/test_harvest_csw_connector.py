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
          <gmd:abstract>
            <gco:CharacterString>Empreintes de batiments</gco:CharacterString>
          </gmd:abstract>
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
          <gmd:citation>
            <gmd:CI_Citation>
              <gmd:title><gco:CharacterString>Sans identifiant</gco:CharacterString></gmd:title>
            </gmd:CI_Citation>
          </gmd:citation>
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
  <csw:SearchResults numberOfRecordsMatched="2" numberOfRecordsReturned="1"
      nextRecord="{next_record}">
    <gmd:MD_Metadata>
      <gmd:fileIdentifier><gco:CharacterString>{identifier}</gco:CharacterString></gmd:fileIdentifier>
      <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
          <gmd:citation>
            <gmd:CI_Citation>
              <gmd:title><gco:CharacterString>{identifier}-title</gco:CharacterString></gmd:title>
            </gmd:CI_Citation>
          </gmd:citation>
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
        f"<gmd:MD_Metadata><gmd:fileIdentifier><gco:CharacterString>iso-{i}</gco:CharacterString></gmd:fileIdentifier></gmd:MD_Metadata>"
        for i in range(600)
    )
    page = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2" '
        'xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<csw:SearchResults numberOfRecordsMatched="600" numberOfRecordsReturned="600" '
        'nextRecord="0">'
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
        external_id="x",
        title="X",
        abstract="",
        keywords=[],
        bbox=[0, 0, 1, 1],
        external_url="x",
        items_url=None,
    )
    assert CswConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_get_connector_returns_csw():
    from app.harvest.connectors import get_connector

    c = get_connector("csw")
    assert c.type == "csw"
    assert c.supports_copy is False
