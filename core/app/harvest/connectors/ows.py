# SPDX-License-Identifier: Apache-2.0
"""Parsing XML sûr et borné des GetCapabilities OGC (SP-12e). defusedxml
neutralise XXE et l'expansion d'entités (billion-laughs). Navigation
namespace-agnostique (WMS 1.1.1 sans namespace vs 1.3.0/WFS/WMTS avec
namespaces) : lookup par local-name plutôt que par QName figé. Tolérant :
un document malformé/hostile retourne None, jamais d'exception qui fuite."""
import logging
from collections.abc import Iterator
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_LAYERS = 500
_MAX_DOCUMENTS = 1  # GetCapabilities = un seul GET par source
_MAX_DEPTH = 10     # profondeur d'arbre <Layer> WMS
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]


def parse_capabilities(content: bytes) -> Element | None:
    try:
        return fromstring(content)
    except Exception as exc:  # ParseError, EntitiesForbidden, DTDForbidden…
        logger.warning("ows harvest: GetCapabilities illisible ou hostile : %s", exc)
        return None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def children(elem: Element, name: str) -> list[Element]:
    return [c for c in elem if local(c.tag) == name]


def child(elem: Element, name: str) -> Element | None:
    for c in elem:
        if local(c.tag) == name:
            return c
    return None


def child_text(elem: Element, name: str) -> str | None:
    c = child(elem, name)
    if c is not None and c.text and c.text.strip():
        return c.text.strip()
    return None


def descendants(elem: Element, name: str) -> Iterator[Element]:
    for c in elem.iter():
        if local(c.tag) == name:
            yield c
