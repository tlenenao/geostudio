# SPDX-License-Identifier: Apache-2.0
"""Journal de santé append-only (SP-61, spec §7.2).

Append-only et non « fichier réécrit » pour trois raisons tenues : le diff git
d'une régénération ne montre que des ajouts ; deux sessions concurrentes ne
s'écrasent pas ; un bug du générateur ne peut pas perdre l'historique.

Le journal n'est **jamais** rétro-calculé : les six notes d'agents de SP-42
sont des jugements, pas des mesures, et les convertir en santé rétroactive
produirait une courbe fausse à son origine."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable


def append_snapshot(
    path: pathlib.Path,
    healths: Iterable[tuple[str, float | None, dict[str, float | None]]],
    *,
    commit: str,
    date: str,
) -> None:
    lines = [
        json.dumps(
            {
                "date": date,
                "commit": commit,
                "id": identifier,
                "sante": value,
                "sous_scores": subscores,
            },
            ensure_ascii=False,
        )
        for identifier, value, subscores in healths
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def last_snapshot(path: pathlib.Path) -> dict[str, float]:
    """La santé de chaque fonctionnalité au dernier instantané écrit."""
    if not path.exists():
        return {}
    latest_commit = None
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["commit"] != latest_commit:
            latest_commit = row["commit"]
            values = {}
        if row["sante"] is not None:
            values[row["id"]] = float(row["sante"])
    return values
