# SPDX-License-Identifier: Apache-2.0
"""Agrégation DB de l'allowlist CSP (SP-48/GAP-72) — instance entière, pas
par tenant : la CSP protège un domaine public par installation
(GEOSTUDIO_PUBLIC_HOST), il n'existe qu'une seule origine à protéger."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.models import Config, ConfigRevision
from app.extensions.models import Extension
from app.harvest.models import HarvestSource
from app.security.csp_hosts import (
    extract_config_external_hosts,
    extract_extension_hosts,
    extract_harvest_hosts,
)


@dataclass
class CspAllowlist:
    img_hosts: set[str] = field(default_factory=set)
    connect_hosts: set[str] = field(default_factory=set)
    script_hosts: set[str] = field(default_factory=set)


def _latest_map_config_bodies(session: Session) -> list[dict]:
    """Un `dict` par `MapConfig` (PAS l'enveloppe `BuilderConfig` complète)
    — `ConfigRevision.data` est `BuilderConfig.model_dump()`, qui porte le
    document carte sous la clé `"map"`. Vérifié contre
    `app/configs/schemas.py::BuilderConfig`/`MapConfig` en tâche
    d'exécution (piège CLAUDE.md n°3) : le plan initial supposait `data`
    directement égal au corps MapConfig, ce qui aurait toujours donné un
    dict vide à `extract_config_external_hosts`."""
    map_config_ids = session.scalars(select(Config.id).where(Config.kind == "map")).all()
    bodies = []
    for config_id in map_config_ids:
        revision = session.scalars(
            select(ConfigRevision)
            .where(ConfigRevision.config_id == config_id)
            .order_by(ConfigRevision.version.desc())
        ).first()
        if revision is not None:
            map_body = revision.data.get("map")
            if map_body:
                bodies.append(map_body)
    return bodies


def compute_csp_allowlist(session: Session) -> CspAllowlist:
    sources = session.scalars(select(HarvestSource)).all()
    extensions = session.scalars(select(Extension)).all()
    tile_hosts = extract_harvest_hosts(sources)
    for body in _latest_map_config_bodies(session):
        tile_hosts |= extract_config_external_hosts(body)
    return CspAllowlist(
        img_hosts=set(tile_hosts),
        connect_hosts=set(tile_hosts),
        script_hosts=extract_extension_hosts(extensions),
    )
