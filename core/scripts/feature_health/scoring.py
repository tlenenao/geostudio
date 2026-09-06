# SPDX-License-Identifier: Apache-2.0
"""Agrégation des quatre sous-scores en une santé 0-100 (SP-61, spec §3, §4).

Deux grandeurs, jamais moyennées ensemble : la **santé** (calculée ici) et la
**priorité** (déclarée dans l'inventaire). Le tri de priorisation est
`priorité × (100 − santé)` : ce qui compte le plus et qui va le moins bien.

Un sous-score `None` est **non applicable** : il sort du calcul et les
pondérations se renormalisent sur les sous-scores restants."""

from __future__ import annotations

import dataclasses
import json
import pathlib

from scripts.feature_health.model import Feature, SubScore

PRIORITY_WEIGHT = {"haute": 3.0, "moyenne": 2.0, "basse": 1.0}


@dataclasses.dataclass(frozen=True)
class Thresholds:
    weights: dict[str, float]
    floor_high_priority: float
    floor_median: float


def load_thresholds(path: pathlib.Path) -> Thresholds:
    document = json.loads(path.read_text(encoding="utf-8"))
    return Thresholds(
        weights=document["ponderations"],
        floor_high_priority=float(document["plancher_priorite_haute"]),
        floor_median=float(document["plancher_sante_mediane"]),
    )


def weighted_health(subscores: dict[str, SubScore], weights: dict[str, float]) -> float | None:
    applicable = {
        name: score.value
        for name, score in subscores.items()
        if score.value is not None and name in weights
    }
    if not applicable:
        return None
    total = sum(weights[name] for name in applicable)
    return sum(value * weights[name] for name, value in applicable.items()) / total


def priority_rank(feature: Feature, health: float | None) -> float:
    if health is None:
        return 0.0
    return PRIORITY_WEIGHT.get(feature.priority, 1.0) * (100.0 - health)
