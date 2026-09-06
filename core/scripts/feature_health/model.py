# SPDX-License-Identifier: Apache-2.0
"""Types partagés par les quatre sous-scores du bilan (SP-61, spec §3)."""

from __future__ import annotations

import dataclasses
import json
import pathlib


@dataclasses.dataclass(frozen=True)
class SubScore:
    """Un sous-score et la donnée qui l'a produit.

    `value is None` signifie **non applicable** — la fonctionnalité n'a aucune
    surface du type mesuré. La moyenne pondérée (scoring.py) renormalise sur
    les seuls sous-scores applicables : un widget builtin sans route REST ne
    doit pas être puni d'un 0 de « garde » qui n'a aucun sens pour lui.

    `evidence` est rendu tel quel dans le détail dépliable du bilan HTML : un
    score dont on ne peut pas voir la source est un score qu'on ne croit pas
    (spec §7.1)."""

    value: float | None
    evidence: dict[str, object]


@dataclasses.dataclass(frozen=True)
class Feature:
    """Une ligne de `docs/revue/inventaire-fonctionnalites.jsonl`.

    `proofs` ne porte que des **chemins de fichier**, jamais `chemin:ligne` :
    les numéros de ligne dérivent en quelques jours (spec §8, mesuré)."""

    identifier: str
    domain: str
    name: str
    proofs: tuple[str, ...]
    rest: tuple[str, ...]
    mcp: tuple[str, ...]
    shell: tuple[str, ...]
    public: tuple[str, ...]
    priority: str
    priority_source: str
    raw: dict


REQUIRED_KEYS = ("id", "domaine", "fonctionnalite", "preuve", "surfaces", "priorite")
PRIORITIES = ("haute", "moyenne", "basse")


def load_inventory(path: pathlib.Path) -> tuple[Feature, ...]:
    features: list[Feature] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [key for key in REQUIRED_KEYS if key not in row]
        if missing:
            raise ValueError(f"{path}:{number} — clés manquantes : {', '.join(missing)}")
        if row["priorite"] not in PRIORITIES:
            raise ValueError(f"{path}:{number} — priorité inconnue : {row['priorite']!r}")
        surfaces = row["surfaces"] or {}
        features.append(
            Feature(
                identifier=row["id"],
                domain=row["domaine"],
                name=row["fonctionnalite"],
                proofs=tuple(row["preuve"]),
                rest=tuple(surfaces.get("rest", ())),
                mcp=tuple(surfaces.get("mcp", ())),
                shell=tuple(surfaces.get("shell", ())),
                public=tuple(row.get("publiques", ())),
                priority=row["priorite"],
                priority_source=row.get("priorite_source", "declaree"),
                raw=row,
            )
        )
    identifiers = [feature.identifier for feature in features]
    duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
    if duplicates:
        raise ValueError(f"{path} — identifiants dupliqués : {', '.join(duplicates)}")
    return tuple(features)
