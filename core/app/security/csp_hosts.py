# SPDX-License-Identifier: Apache-2.0
"""Extraction pure d'hôtes externes référencés par des documents/tables
déjà en base, pour construire une allowlist CSP calculée (SP-48/GAP-72,
blocages 1/2/3). Aucune fonction ici ne fait d'I/O — la lecture DB vit
dans app.security.service."""

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


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None  # URL relative (proxy interne) ou schéma non pertinent
    return f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")


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


class _ExtensionLike(Protocol):
    module_url: str


def extract_extension_hosts(extensions: Sequence[_ExtensionLike]) -> set[str]:
    hosts: set[str] = set()
    for extension in extensions:
        origin = _origin(extension.module_url)
        if origin:
            hosts.add(origin)
    return hosts
