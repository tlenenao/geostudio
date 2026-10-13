# SPDX-License-Identifier: Apache-2.0
"""Export SLD 1.1 / Symbology Encoding 1.1 d'un `Style` (ARC-28). Écriture seule,
chaînes construites à la main : aucun XML entrant n'est parsé (pas de surface XXE)
et toute valeur sortante est échappée (champs, valeurs de catégorie, titres)."""

import re
from xml.sax.saxutils import escape

from app.styles.model import Rule, Style

NS = (
    'xmlns:sld="http://www.opengis.net/sld" xmlns:se="http://www.opengis.net/se" '
    'xmlns:ogc="http://www.opengis.net/ogc"'
)
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _t(v: str) -> str:
    return escape(_BAD_XML.sub("", v))


def _p(name: str, value: str) -> str:
    return f'<se:SvgParameter name="{name}">{_t(value)}</se:SvgParameter>'


def _num(v: float) -> str:
    return f"{v:g}"


def _cmp(tag: str, field: str, value: str) -> str:
    return (
        f"<ogc:{tag}><ogc:PropertyName>{_t(field)}</ogc:PropertyName>"
        f"<ogc:Literal>{_t(value)}</ogc:Literal></ogc:{tag}>"
    )


def _filter(test: tuple | None) -> str:
    if test is None:
        return ""
    if test[0] == "else":
        return "<se:ElseFilter/>"
    if test[0] == "eq":
        return f"<ogc:Filter>{_cmp('PropertyIsEqualTo', test[1], test[2])}</ogc:Filter>"
    parts = []
    if test[2] is not None:
        parts.append(_cmp("PropertyIsGreaterThanOrEqualTo", test[1], _num(test[2])))
    if test[3] is not None:
        parts.append(_cmp("PropertyIsLessThan", test[1], _num(test[3])))
    if not parts:
        return ""
    body = parts[0] if len(parts) == 1 else f"<ogc:And>{''.join(parts)}</ogc:And>"
    return f"<ogc:Filter>{body}</ogc:Filter>"


def _fill(r: Rule) -> str:
    return f"<se:Fill>{_p('fill', r.fill)}{_p('fill-opacity', _num(r.fill_opacity))}</se:Fill>"


def _stroke(color: str, width: float, dash: tuple[float, ...] | None) -> str:
    d = _p("stroke-dasharray", " ".join(_num(x) for x in dash)) if dash else ""
    return f"<se:Stroke>{_p('stroke', color)}{_p('stroke-width', _num(width))}{d}</se:Stroke>"


def _symbolizer(kind: str, r: Rule) -> str:
    if kind == "line":
        return f"<se:LineSymbolizer>{_stroke(r.fill, r.stroke_width, r.dash)}</se:LineSymbolizer>"
    stroke = _stroke(r.stroke, r.stroke_width, r.dash) if r.stroke else ""
    if kind == "polygon":
        return f"<se:PolygonSymbolizer>{_fill(r)}{stroke}</se:PolygonSymbolizer>"
    return (
        "<se:PointSymbolizer><se:Graphic><se:Mark><se:WellKnownName>circle</se:WellKnownName>"
        f"{_fill(r)}{stroke}</se:Mark><se:Size>{_num(r.radius * 2)}</se:Size></se:Graphic>"
        "</se:PointSymbolizer>"
    )


def style_to_sld(style: Style, *, layer_name: str, title: str | None = None) -> str:
    rules = "".join(
        f"<se:Rule><se:Name>r{i}</se:Name><se:Description><se:Title>{_t(r.title)}</se:Title>"
        f"</se:Description>{_filter(r.test)}{_symbolizer(style.geometry_kind, r)}</se:Rule>"
        for i, r in enumerate(style.rules)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sld:StyledLayerDescriptor version="1.1.0" {NS}>'
        f"<sld:NamedLayer><se:Name>{_t(layer_name)}</se:Name><sld:UserStyle>"
        f"<se:Name>{_t(layer_name)}</se:Name>"
        f"<se:Description><se:Title>{_t(title or layer_name)}</se:Title></se:Description>"
        f"<se:FeatureTypeStyle>{rules}</se:FeatureTypeStyle></sld:UserStyle></sld:NamedLayer>"
        "</sld:StyledLayerDescriptor>"
    )
