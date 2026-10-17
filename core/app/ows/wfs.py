# SPDX-License-Identifier: Apache-2.0
"""Sérialisation WFS 2.0 / GML 3.2 (ARC-11, ADR 0018). Écriture seule : le cœur
ne PARSE aucun XML entrant (requêtes KVP uniquement), donc pas de surface XXE ;
toute valeur sortante est échappée, les caractères interdits en XML 1.0 retirés.
Chaînes construites à la main (pas d'ElementTree) : les préfixes `gml:`/`gs:`
apparaissent aussi dans des valeurs d'attribut (`type="gml:PointPropertyType"`),
que la sérialisation par espaces de noms ne déclarerait pas."""

import re
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape, quoteattr

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.repository import _property_columns
from app.ogc_crs import SUPPORTED_EPSG

NS_GS = "http://geostudio.local/ows"
NS_WFS = "http://www.opengis.net/wfs/2.0"
NS_GML = "http://www.opengis.net/gml/3.2"
NS_OWS = "http://www.opengis.net/ows/1.1"
GML_FORMAT = "application/gml+xml; version=3.2"
GML_ALIASES = {GML_FORMAT, "application/gml+xml", "gml32", "text/xml; subtype=gml/3.2.1"}
JSON_ALIASES = {"application/json", "json", "geojson", "application/geo+json"}
NCNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_XSD = {
    "string": "xsd:string",
    "enum": "xsd:string",
    "integer": "xsd:long",
    "number": "xsd:double",
    "boolean": "xsd:boolean",
    "date": "xsd:date",
    "datetime": "xsd:dateTime",
}
_GEOM_PROP = {
    "Point": "gml:PointPropertyType",
    "LineString": "gml:CurvePropertyType",
    "Polygon": "gml:SurfacePropertyType",
    "MultiPoint": "gml:MultiPointPropertyType",
    "MultiLineString": "gml:MultiCurvePropertyType",
    "MultiPolygon": "gml:MultiSurfacePropertyType",
}

_OTHER_CRS = "".join(
    f"<wfs:OtherCRS>urn:ogc:def:crs:EPSG::{c}</wfs:OtherCRS>" for c in SUPPORTED_EPSG if c != 4326
)


def _t(value: str) -> str:
    return escape(_BAD_XML.sub("", value))


def _a(value: str) -> str:
    return quoteattr(_BAD_XML.sub("", value))


def exposed_columns(info: TableInfo) -> list[ColumnInfo]:
    """Propriétés servies : types scalaires, nom NCName (sinon l'XSD serait invalide)."""
    return [c for c in _property_columns(info) if c.type in _XSD and NCNAME.match(c.name)]


def exception_report(code: str, locator: str | None, message: str) -> str:
    loc = f" locator={_a(locator)}" if locator else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ows:ExceptionReport xmlns:ows="{NS_OWS}" version="2.0.0">'
        f"<ows:Exception exceptionCode={_a(code)}{loc}>"
        f"<ows:ExceptionText>{_t(message)}</ows:ExceptionText></ows:Exception>"
        "</ows:ExceptionReport>"
    )


def capabilities(base_url: str, title: str, collections: list) -> str:
    ops = ""
    for name in ("GetCapabilities", "DescribeFeatureType", "GetFeature"):
        fmt = ""
        if name != "GetCapabilities":
            fmt = (
                '<ows:Parameter name="outputFormat"><ows:AllowedValues>'
                f"<ows:Value>{_t(GML_FORMAT)}</ows:Value><ows:Value>application/json</ows:Value>"
                "</ows:AllowedValues></ows:Parameter>"
            )
            if name == "DescribeFeatureType":
                fmt = ""
        ops += (
            f'<ows:Operation name="{name}"><ows:DCP><ows:HTTP>'
            f"<ows:Get xlink:href={_a(base_url)}/></ows:HTTP></ows:DCP>{fmt}</ows:Operation>"
        )
    types = ""
    for col in collections:
        types += (
            f"<wfs:FeatureType><wfs:Name>gs:{_t(col.id)}</wfs:Name>"
            f"<wfs:Title>{_t(col.title)}</wfs:Title>"
            f"<wfs:Abstract>{_t(col.description or '')}</wfs:Abstract>"
            "<wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>"
            f"{_OTHER_CRS}"
            "<wfs:OutputFormats>"
            f"<wfs:Format>{_t(GML_FORMAT)}</wfs:Format><wfs:Format>application/json</wfs:Format>"
            "</wfs:OutputFormats></wfs:FeatureType>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="{NS_WFS}" xmlns:ows="{NS_OWS}" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:gml="{NS_GML}" xmlns:gs="{NS_GS}">'
        f"<ows:ServiceIdentification><ows:Title>{_t(title)}</ows:Title>"
        "<ows:ServiceType>WFS</ows:ServiceType><ows:ServiceTypeVersion>2.0.0</ows:ServiceTypeVersion>"
        "</ows:ServiceIdentification>"
        "<ows:ServiceProvider><ows:ProviderName>GeoStudio</ows:ProviderName><ows:ServiceContact/></ows:ServiceProvider>"
        f"<ows:OperationsMetadata>{ops}"
        '<ows:Constraint name="ImplementsBasicWFS"><ows:NoValues/>'
        "<ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>"
        '<ows:Constraint name="KVPEncoding"><ows:NoValues/>'
        "<ows:DefaultValue>TRUE</ows:DefaultValue></ows:Constraint>"
        '<ows:Constraint name="ImplementsTransactionalWFS"><ows:NoValues/>'
        "<ows:DefaultValue>FALSE</ows:DefaultValue></ows:Constraint>"
        f"</ows:OperationsMetadata><wfs:FeatureTypeList>{types}</wfs:FeatureTypeList>"
        "</wfs:WFS_Capabilities>"
    )


def describe_feature_type(items: list[tuple[str, TableInfo]]) -> str:
    """XSD des types demandés (`items` = [(id de collection, schéma visible)])."""
    body = ""
    for cid, info in items:
        elems = "".join(
            f'<xsd:element name="{c.name}" type="{_XSD[c.type]}" minOccurs="0" nillable="true"/>'
            for c in exposed_columns(info)
        )
        if info.geometry_column and NCNAME.match(info.geometry_column):
            gtype = _GEOM_PROP.get(info.geometry_type or "", "gml:GeometryPropertyType")
            elems += (
                f'<xsd:element name="{info.geometry_column}" type="{gtype}" '
                'minOccurs="0" nillable="true"/>'
            )
        body += (
            f'<xsd:element name="{_t(cid)}" type="gs:{_t(cid)}Type" '
            'substitutionGroup="gml:AbstractFeature"/>'
            f'<xsd:complexType name="{_t(cid)}Type"><xsd:complexContent>'
            f'<xsd:extension base="gml:AbstractFeatureType"><xsd:sequence>{elems}'
            "</xsd:sequence></xsd:extension></xsd:complexContent></xsd:complexType>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:gml="{NS_GML}" '
        f'xmlns:gs="{NS_GS}" targetNamespace="{NS_GS}" elementFormDefault="qualified">'
        f'<xsd:import namespace="{NS_GML}" '
        'schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd"/>'
        f"{body}</xsd:schema>"
    )


def _num(v: float) -> str:
    return f"{v:.15g}"


def _pos(coord: list, swap: bool) -> str:
    xy = [coord[1], coord[0]] if swap else [coord[0], coord[1]]
    return " ".join(_num(v) for v in [*xy, *coord[2:3]])


def _dim(coords: list) -> int:
    return 3 if coords and len(coords[0]) > 2 else 2


def geojson_to_gml(geom: dict, *, srs: str, swap: bool, gid: str) -> str:
    """GeoJSON -> GML 3.2 (gml:id sur chaque géométrie, axe lat/lon si `swap`)."""
    n = [0]

    def ident() -> str:
        n[0] += 1
        return f" gml:id={_a(f'{gid}.{n[0]}')}"

    def posl(coords: list) -> str:
        d = f' srsDimension="{_dim(coords)}"' if _dim(coords) == 3 else ""
        return f"<gml:posList{d}>{' '.join(_pos(c, swap) for c in coords)}</gml:posList>"

    def polygon(rings: list) -> str:
        out = f"<gml:Polygon{ident()}>"
        for k, ring in enumerate(rings):
            tag = "exterior" if k == 0 else "interior"
            out += f"<gml:{tag}><gml:LinearRing{ident()}>{posl(ring)}</gml:LinearRing></gml:{tag}>"
        return out + "</gml:Polygon>"

    def point(c: list) -> str:
        return f"<gml:Point{ident()}><gml:pos>{_pos(c, swap)}</gml:pos></gml:Point>"

    def line(cs: list) -> str:
        return f"<gml:LineString{ident()}>{posl(cs)}</gml:LineString>"

    t, c = geom["type"], geom.get("coordinates")
    s = f" srsName={_a(srs)}"
    if t == "Point":
        out = point(c)
    elif t == "LineString":
        out = line(c)
    elif t == "Polygon":
        out = polygon(c)
    elif t == "MultiPoint":
        out = f"<gml:MultiPoint{ident()}>" + "".join(
            f"<gml:pointMember>{point(p)}</gml:pointMember>" for p in c
        )
        out += "</gml:MultiPoint>"
    elif t == "MultiLineString":
        out = f"<gml:MultiCurve{ident()}>" + "".join(
            f"<gml:curveMember>{line(p)}</gml:curveMember>" for p in c
        )
        out += "</gml:MultiCurve>"
    elif t == "MultiPolygon":
        out = f"<gml:MultiSurface{ident()}>" + "".join(
            f"<gml:surfaceMember>{polygon(p)}</gml:surfaceMember>" for p in c
        )
        out += "</gml:MultiSurface>"
    else:
        raise ValueError(f"unsupported geometry type {t}")
    return out.replace(">", f"{s}>", 1) if s else out


def _value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, Decimal | int | float):
        return str(v)
    return str(v)


def feature_collection(
    *,
    cid: str,
    info: TableInfo,
    features: list[dict],
    matched: int | str,
    returned: int,
    timestamp: str,
    srs: str,
    swap: bool,
    next_url: str | None = None,
) -> str:
    cols = exposed_columns(info)
    members = ""
    for f in features:
        fid = f"{cid}.{f['id']}"
        props = "".join(
            f"<gs:{c.name}>{_t(_value(f['properties'][c.name]))}</gs:{c.name}>"
            for c in cols
            if f["properties"].get(c.name) is not None
        )
        geom = ""
        if f.get("geometry") and info.geometry_column and NCNAME.match(info.geometry_column):
            g = info.geometry_column
            gml = geojson_to_gml(f["geometry"], srs=srs, swap=swap, gid=fid)
            geom = f"<gs:{g}>{gml}</gs:{g}>"
        members += (
            f"<wfs:member><gs:{_t(cid)} gml:id={_a(fid)}>{props}{geom}</gs:{_t(cid)}></wfs:member>"
        )
    nxt = f" next={_a(next_url)}" if next_url else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<wfs:FeatureCollection xmlns:wfs="{NS_WFS}" xmlns:gml="{NS_GML}" xmlns:gs="{NS_GS}" '
        f"timeStamp={_a(timestamp)} numberMatched={_a(str(matched))} "
        f'numberReturned="{returned}"{nxt}>{members}</wfs:FeatureCollection>'
    )
