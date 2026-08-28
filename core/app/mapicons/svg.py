# SPDX-License-Identifier: Apache-2.0
"""Assainissement des SVG d'icônes personnalisées (SP-27, D4 + D6).

Appliqué à l'ÉCRITURE : ce sont les octets assainis qui sont stockés dans S3,
et la lecture ne réassainit jamais. Cet invariant est vrai parce que D7
(déviation 16) supprime la présignation : le cœur reçoit les octets, choisit la
clé, et n'écrit que la version assainie. Aucun client ne détient jamais de
droit d'écriture sur la clé servie.

Deux couches distinctes, parce qu'elles protègent de choses différentes :
1. `defusedxml` (déjà dépendance directe du cœur, SP-12e) neutralise les
   bombes d'entités et l'XXE. MESURÉ (voir les faits de la tâche) : il ne fait
   RIEN contre <script>, onload= ou xlink:href — c'est du XML parfaitement
   valide. `forbid_dtd` reste à False : une ligne <!DOCTYPE> sans déclaration
   d'entité est acceptée (tous les exports Illustrator en portent une), et
   mesuré, la DTD externe référencée n'est JAMAIS récupérée sur le réseau.
2. Une allowlist stricte d'éléments et d'attributs, appliquée sur l'arbre
   parsé, puis une RE-SÉRIALISATION depuis cet arbre. Jamais de filtrage par
   expression régulière sur le texte source : un filtre textuel se contourne
   par encodage, un arbre reconstruit ne contient que ce qu'on y a remis.

C'est cette seconde couche qui rend l'acceptation du DOCTYPE sûre : une
déclaration <!ATTLIST> du sous-ensemble interne injecte réellement des
attributs par défaut dans l'arbre (mesuré), et c'est l'allowlist d'attributs
qui les écarte. Ne jamais désactiver l'une en gardant l'autre.
"""

import math
import re
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

SVG_NS = "http://www.w3.org/2000/svg"

_ALLOWED_ELEMENTS = frozenset(
    {
        "svg",
        "g",
        "path",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "rect",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
        "text",
        "tspan",
    }
)

_GRAPHIC_ELEMENTS = frozenset(
    {"path", "circle", "ellipse", "line", "polyline", "polygon", "rect", "text"}
)
_REQUIRED_GEOMETRY = {"path": "d", "polyline": "points", "polygon": "points"}

_ALLOWED_ATTRS = frozenset(
    {
        "d",
        "points",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "width",
        "height",
        "viewBox",
        "transform",
        "fill",
        "fill-rule",
        "fill-opacity",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-opacity",
        "stroke-miterlimit",
        "opacity",
        "id",
        "offset",
        "stop-color",
        "stop-opacity",
        "gradientUnits",
        "gradientTransform",
        "spreadMethod",
        "fx",
        "fy",
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "text-anchor",
        "dominant-baseline",
        "letter-spacing",
        "word-spacing",
        "dx",
        "dy",
    }
)

_MAX_SANITIZED_BYTES = 200_000
_MAX_DEPTH = 20
_MAX_DIMENSION = 4096

# `\Z` (not `$`) on both regexes: `$` in Python also matches immediately before
# a single trailing "\n", so a value ending in a literal newline (reachable via
# a `&#10;` character reference, which the XML parser does NOT collapse to a
# space the way it does a literal source newline) would otherwise slip past an
# anchor meant to bind the whole value. These two regexes ARE the security
# contract of D6(c) — keep both ends genuinely anchored.
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\Z")
_LOCAL_URL_RE = re.compile(
    r"""^url\(\s*(?:"|')?\#([A-Za-z_][A-Za-z0-9_.-]*)(?:"|')?\s*\)\Z""", re.IGNORECASE
)

# Paint-bearing attributes (SVG <paint> / <color> value syntax). Browsers parse
# these with the CSS value grammar, whose tokenizer resolves CSS escapes
# (`\XX ` = hex codepoint, optionally space-terminated) BEFORE forming tokens
# such as `url(...)`. A substring blacklist on the raw attribute text (looking
# for "url(", "javascript:", "data:") is therefore bypassable: the raw string
# never contains the forbidden substring, yet the browser's decoded value does
# (e.g. `fill="\75 rl(http://evil.test/x)"` is CSS-equivalent to
# `fill="url(http://evil.test/x)"`). Whitelisting the value SHAPE closes this
# generally, instead of chasing individual escaped substrings.
_PAINT_ATTRS = frozenset({"fill", "stroke", "stop-color"})
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\Z")
_PAINT_KEYWORDS = frozenset({"none", "currentcolor"})


class SvgRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _local(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _paint_value_is_allowed(value: str) -> bool:
    # No `.strip()` here: stripping would undo the `\Z` anchor fix above by
    # silently discarding a trailing `\n` (reachable via `&#10;`) before the
    # regex ever sees it. None of the accepted shapes carry outer whitespace.
    if value.lower() in _PAINT_KEYWORDS:
        return True
    if _HEX_COLOR_RE.match(value):
        return True
    return bool(_LOCAL_URL_RE.match(value))


def _attr_value_is_allowed(key: str, value: str) -> bool:
    # A backslash never belongs in any of these values legitimately, and it is
    # the one character that lets the CSS tokenizer rewrite the value into
    # something a raw-substring check never sees. Reject it outright, for
    # every attribute, before any other check runs.
    if "\\" in value:
        return False
    if key == "id":
        return bool(_ID_RE.match(value))
    if key in _PAINT_ATTRS:
        return _paint_value_is_allowed(value)
    lowered = value.lower()
    if "javascript:" in lowered or "data:" in lowered:
        return False
    if "url(" in lowered:
        return bool(_LOCAL_URL_RE.match(value))
    return True


def _clean(element: ET.Element, depth: int) -> ET.Element | None:
    if depth > _MAX_DEPTH:
        raise SvgRejected("svg_too_deep", f"Ce SVG imbrique plus de {_MAX_DEPTH} niveaux.")
    tag = element.tag
    if not isinstance(tag, str):
        return None
    ns = _namespace(tag)
    if ns is not None and ns != SVG_NS:
        return None
    name = _local(tag)
    if name not in _ALLOWED_ELEMENTS:
        return None
    out = ET.Element(name)
    for key, value in element.attrib.items():
        if "}" in key or ":" in key:
            continue
        if key.lower().startswith("on"):
            continue
        if key not in _ALLOWED_ATTRS:
            continue
        if not _attr_value_is_allowed(key, value):
            continue
        out.set(key, value)
    if element.text:
        out.text = element.text
    if element.tail:
        out.tail = element.tail
    for child in element:
        cleaned = _clean(child, depth + 1)
        if cleaned is not None:
            out.append(cleaned)
    return out


def _has_graphics(element: ET.Element) -> bool:
    for e in element.iter():
        name = _local(e.tag)
        if name not in _GRAPHIC_ELEMENTS:
            continue
        required = _REQUIRED_GEOMETRY.get(name)
        if required is not None and not e.get(required):
            continue
        if name == "text" and not (e.text or "").strip():
            continue
        return True
    return False


def _dimension(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw.strip().removesuffix("px"))
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0 or value > _MAX_DIMENSION:
        return None
    return value


def sanitize_svg(raw: bytes) -> bytes:
    try:
        parsed = fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        name = type(exc).__name__
        if name == "EntitiesForbidden":
            raise SvgRejected(
                "svg_entities_forbidden",
                "Ce SVG déclare une entité XML (<!ENTITY>) : retirez-la. "
                "Une ligne <!DOCTYPE> sans déclaration d'entité est acceptée.",
            ) from exc
        if "Forbidden" in name:
            raise SvgRejected(
                "svg_dtd_forbidden",
                "Ce SVG contient une déclaration XML refusée (DTD externe ou entité).",
            ) from exc
        raise SvgRejected(
            "svg_unparsable",
            "SVG illisible : le document n'est pas du XML bien formé.",
        ) from exc

    if _local(parsed.tag) != "svg" or _namespace(parsed.tag) not in (None, SVG_NS):
        raise SvgRejected("svg_not_svg_root", "La racine du document n'est pas un <svg>.")

    cleaned = _clean(parsed, 0)
    if cleaned is None or not _has_graphics(cleaned):
        raise SvgRejected(
            "svg_no_graphics",
            "Après assainissement, ce SVG ne contient plus aucun élément graphique.",
        )
    cleaned.tail = None

    view_box = cleaned.get("viewBox")
    width = _dimension(cleaned.get("width"))
    height = _dimension(cleaned.get("height"))
    if width is None or height is None:
        parts = (view_box or "").replace(",", " ").split()
        vb = [_dimension(p) for p in parts[2:4]] if len(parts) == 4 else []
        if len(vb) != 2 or vb[0] is None or vb[1] is None:
            raise SvgRejected(
                "svg_no_dimensions",
                "Ce SVG n'a ni width/height numériques exploitables (0 < v ≤ "
                f"{_MAX_DIMENSION}) ni viewBox dont les deux dernières valeurs le soient.",
            )
        width, height = vb
    cleaned.set("width", f"{width:g}")
    cleaned.set("height", f"{height:g}")

    cleaned.set("xmlns", SVG_NS)
    out = ET.tostring(cleaned, encoding="utf-8")
    if len(out) > _MAX_SANITIZED_BYTES:
        raise SvgRejected("svg_too_large", "SVG trop volumineux après assainissement.")
    return out


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_UTF8_BOM = b"\xef\xbb\xbf"
_SNIFF_WINDOW = 1024


def sniff_content_type(head: bytes) -> str | None:
    if head.startswith(_PNG_MAGIC):
        return "image/png"
    if b"<svg" in head.removeprefix(_UTF8_BOM)[:_SNIFF_WINDOW].lower():
        return "image/svg+xml"
    return None
