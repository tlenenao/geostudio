# SPDX-License-Identifier: Apache-2.0
"""Fiche ISO 19139 (gmd) d'une collection (AUD-047, D11 : export ISO, pas de CSW).
Profil minimal INSPIRE : identifiant, langue, contact, date, SRS, citation, résumé,
mots-clés (libres + thème GEMET-INSPIRE), contraintes, catégorie, emprise, distribution,
généalogie. Toutes les valeurs passent par escape/quoteattr."""

from xml.sax.saxutils import escape, quoteattr

from app.catalog.metadata import ISO639_2B, resolve_inspire_theme, resolve_license

_NS = (
    'xmlns:gmd="http://www.isotc211.org/2005/gmd" '
    'xmlns:gco="http://www.isotc211.org/2005/gco" '
    'xmlns:xlink="http://www.w3.org/1999/xlink"'
)
_CODELIST = "http://standards.iso.org/iso/19139/resources/gmxCodelists.xml"


def _cs(value: str) -> str:
    return f"<gco:CharacterString>{escape(value)}</gco:CharacterString>"


def _code(element: str, value: str) -> str:
    return (
        f"<gmd:{element} codeList={quoteattr(f'{_CODELIST}#{element}')} "
        f"codeListValue={quoteattr(value)}>{escape(value)}</gmd:{element}>"
    )


def _keywords(words: list[str], thesaurus: tuple[str, str] | None = None) -> str:
    kws = "".join(f"<gmd:keyword>{_cs(w)}</gmd:keyword>" for w in words)
    thes = ""
    if thesaurus:
        title, date = thesaurus
        thes = (
            "<gmd:thesaurusName><gmd:CI_Citation>"
            f"<gmd:title>{_cs(title)}</gmd:title><gmd:date><gmd:CI_Date>"
            f"<gmd:date><gco:Date>{date}</gco:Date></gmd:date>"
            f"<gmd:dateType>{_code('CI_DateTypeCode', 'publication')}</gmd:dateType>"
            "</gmd:CI_Date></gmd:date></gmd:CI_Citation></gmd:thesaurusName>"
        )
    return (
        f"<gmd:descriptiveKeywords><gmd:MD_Keywords>{kws}{thes}"
        "</gmd:MD_Keywords></gmd:descriptiveKeywords>"
    )


def _party(name: str, contact: str, role: str) -> str:
    email = (
        "<gmd:contactInfo><gmd:CI_Contact><gmd:address><gmd:CI_Address>"
        f"<gmd:electronicMailAddress>{_cs(contact)}</gmd:electronicMailAddress>"
        "</gmd:CI_Address></gmd:address></gmd:CI_Contact></gmd:contactInfo>"
        if "@" in contact
        else ""
    )
    return (
        f"<gmd:CI_ResponsibleParty><gmd:organisationName>{_cs(name)}</gmd:organisationName>"
        f"{email}<gmd:role>{_code('CI_RoleCode', role)}</gmd:role></gmd:CI_ResponsibleParty>"
    )


def collection_metadata(
    *, col, bbox: list[float] | None, srid: int | None, items_url: str, publisher: str
) -> str:
    lang = ISO639_2B.get(col.language, "fre")
    organisation = col.producer or publisher
    theme = resolve_inspire_theme(col.inspire_theme) if col.inspire_theme else None
    lic = resolve_license(col.license) if col.license else None
    licence_text = (lic.label if lic else "") or col.license_uri or "Conditions inconnues"
    keywords = _keywords(list(col.keywords)) if col.keywords else ""
    if theme is not None:
        keywords += _keywords([theme.label], ("GEMET - INSPIRE themes, version 1.0", "2008-06-01"))
    topic = (
        f"<gmd:topicCategory><gmd:MD_TopicCategoryCode>{theme.iso_category}"
        "</gmd:MD_TopicCategoryCode></gmd:topicCategory>"
        if theme is not None
        else ""
    )
    extent = ""
    if bbox:
        w, s, e, n = bbox
        extent = (
            "<gmd:extent><gmd:EX_Extent><gmd:geographicElement><gmd:EX_GeographicBoundingBox>"
            f"<gmd:westBoundLongitude><gco:Decimal>{w}</gco:Decimal></gmd:westBoundLongitude>"
            f"<gmd:eastBoundLongitude><gco:Decimal>{e}</gco:Decimal></gmd:eastBoundLongitude>"
            f"<gmd:southBoundLatitude><gco:Decimal>{s}</gco:Decimal></gmd:southBoundLatitude>"
            f"<gmd:northBoundLatitude><gco:Decimal>{n}</gco:Decimal></gmd:northBoundLatitude>"
            "</gmd:EX_GeographicBoundingBox></gmd:geographicElement></gmd:EX_Extent></gmd:extent>"
        )
    srs = (
        "<gmd:referenceSystemInfo><gmd:MD_ReferenceSystem><gmd:referenceSystemIdentifier>"
        f"<gmd:RS_Identifier><gmd:code>{_cs(f'EPSG:{srid}')}</gmd:code></gmd:RS_Identifier>"
        "</gmd:referenceSystemIdentifier></gmd:MD_ReferenceSystem></gmd:referenceSystemInfo>"
        if srid
        else ""
    )
    lineage = (
        "<gmd:dataQualityInfo><gmd:DQ_DataQuality><gmd:scope><gmd:DQ_Scope>"
        f"<gmd:level>{_code('MD_ScopeCode', 'dataset')}</gmd:level></gmd:DQ_Scope></gmd:scope>"
        f"<gmd:lineage><gmd:LI_Lineage><gmd:statement>{_cs(col.lineage)}</gmd:statement>"
        "</gmd:LI_Lineage></gmd:lineage></gmd:DQ_DataQuality></gmd:dataQualityInfo>"
        if col.lineage
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<gmd:MD_Metadata {_NS}>"
        f"<gmd:fileIdentifier>{_cs(col.id)}</gmd:fileIdentifier>"
        f"<gmd:language>{_code('LanguageCode', lang)}</gmd:language>"
        f"<gmd:hierarchyLevel>{_code('MD_ScopeCode', 'dataset')}</gmd:hierarchyLevel>"
        f"<gmd:contact>{_party(organisation, col.contact, 'pointOfContact')}</gmd:contact>"
        f"<gmd:dateStamp><gco:Date>{col.updated_at.date().isoformat()}</gco:Date></gmd:dateStamp>"
        f"{srs}"
        "<gmd:identificationInfo><gmd:MD_DataIdentification>"
        f"<gmd:citation><gmd:CI_Citation><gmd:title>{_cs(col.title)}</gmd:title>"
        "<gmd:date><gmd:CI_Date>"
        f"<gmd:date><gco:Date>{col.created_at.date().isoformat()}</gco:Date></gmd:date>"
        f"<gmd:dateType>{_code('CI_DateTypeCode', 'creation')}</gmd:dateType>"
        "</gmd:CI_Date></gmd:date>"
        f"<gmd:identifier><gmd:RS_Identifier><gmd:code>{_cs(col.id)}</gmd:code></gmd:RS_Identifier></gmd:identifier>"
        "</gmd:CI_Citation></gmd:citation>"
        f"<gmd:abstract>{_cs(col.description or col.title)}</gmd:abstract>"
        f"<gmd:pointOfContact>{_party(organisation, col.contact, 'owner')}</gmd:pointOfContact>"
        f"{keywords}"
        "<gmd:resourceConstraints><gmd:MD_LegalConstraints>"
        f"<gmd:useLimitation>{_cs(licence_text)}</gmd:useLimitation>"
        f"<gmd:accessConstraints>{_code('MD_RestrictionCode', 'otherRestrictions')}"
        "</gmd:accessConstraints>"
        f"<gmd:otherConstraints>{_cs(licence_text)}</gmd:otherConstraints>"
        "</gmd:MD_LegalConstraints></gmd:resourceConstraints>"
        f"<gmd:language>{_code('LanguageCode', lang)}</gmd:language>"
        f"{topic}{extent}"
        "</gmd:MD_DataIdentification></gmd:identificationInfo>"
        "<gmd:distributionInfo><gmd:MD_Distribution><gmd:transferOptions><gmd:MD_DigitalTransferOptions>"
        f"<gmd:onLine><gmd:CI_OnlineResource><gmd:linkage><gmd:URL>{escape(items_url)}</gmd:URL></gmd:linkage>"
        f"<gmd:protocol>{_cs('OGC API Features')}</gmd:protocol>"
        "</gmd:CI_OnlineResource></gmd:onLine>"
        "</gmd:MD_DigitalTransferOptions></gmd:transferOptions></gmd:MD_Distribution></gmd:distributionInfo>"
        f"{lineage}"
        "</gmd:MD_Metadata>"
    )
