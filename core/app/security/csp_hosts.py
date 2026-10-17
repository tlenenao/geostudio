# SPDX-License-Identifier: Apache-2.0
"""Extraction pure d'hôtes externes référencés par des documents/tables
déjà en base, pour construire une allowlist CSP calculée (SP-48/GAP-72,
blocages 1/2/3). Aucune fonction ici ne fait d'I/O — la lecture DB vit
dans app.security.service."""

import re
from collections.abc import Sequence
from typing import Protocol
from urllib.parse import urlparse

# Vérifié contre le code réel des connecteurs de moissonnage
# (core/app/harvest/connectors/*.py) : seuls wms.py/wmts.py posent jamais
# HarvestedRecord.raster_tiles_url à une valeur non nulle — arcgis/csw/wfs/
# ogc_records/stac/ckan posent toujours raster_tiles_url=None (consommés
# côté serveur par le worker, avec sa propre garde d'egress
# app.harvest.egress ; le navigateur ne les contacte jamais directement).
# wms/wmts sont donc bien les deux seuls types dont HarvestSource.url doit
# entrer dans l'allowlist img-src/connect-src.
_HARVEST_TILE_TYPES = {"wms", "wmts"}
_TILE_LAYER_KINDS = {"raster", "tiles3d"}


_HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def _origin(url: str | None) -> str | None:
    """Origine sûre à insérer dans la CSP, ou None (entrée ignorée, jamais levée :
    un seul enregistrement piégé ne doit ni injecter de directive ni figer la CSP
    de l'instance, AUD-089)."""
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or not _HOST_RE.fullmatch(host):
        return None  # relative (proxy interne), schéma non pertinent ou hôte malformé
    try:
        port = parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")


class _HarvestSourceLike(Protocol):
    type: str
    url: str


def extract_harvest_hosts(sources: Sequence[_HarvestSourceLike]) -> set[str]:
    hosts: set[str] = set()
    for source in sources:
        if source.type not in _HARVEST_TILE_TYPES:
            continue
        origin = _origin(source.url)
        if origin:
            hosts.add(origin)
    return hosts


def extract_config_external_hosts(body: dict) -> set[str]:
    """`body` est le document MapConfig lui-même (clés basemap/view/layers/
    terrain), PAS l'enveloppe BuilderConfig complète — l'appelant
    (app.security.service._latest_map_config_bodies) doit passer
    `revision.data["map"]`, pas `revision.data` tel quel."""
    hosts: set[str] = set()
    terrain = body.get("terrain") or {}
    origin = _origin(terrain.get("tilesUrl"))
    if origin:
        hosts.add(origin)
    for layer in body.get("layers") or []:
        if layer.get("kind") not in _TILE_LAYER_KINDS:
            continue
        if layer.get("collectionId"):
            continue  # servi par le cœur (tuiles MVT), jamais un hôte externe
        origin = _origin(layer.get("url") or layer.get("tilesUrl"))
        if origin:
            hosts.add(origin)
    return hosts


def extract_basemap_hosts(styles: Sequence[str]) -> set[str]:
    """Origines des fonds de carte du tenant : URL de style, ou gabarit raster `xyz:<url>`."""
    return {o for s in styles if (o := _origin(s.removeprefix("xyz:")))}


class _ExtensionLike(Protocol):
    module_url: str


def extract_extension_hosts(extensions: Sequence[_ExtensionLike]) -> set[str]:
    hosts: set[str] = set()
    for extension in extensions:
        origin = _origin(extension.module_url)
        if origin:
            hosts.add(origin)
    return hosts
