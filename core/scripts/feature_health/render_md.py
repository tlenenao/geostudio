# SPDX-License-Identifier: Apache-2.0
"""Rendu Markdown du bilan (SP-61, spec §7.1).

Le Markdown n'est pas le produit central — le HTML l'est. Il existe pour ce que
le HTML fait mal : être lu dans un diff de commit, et être grepé. Les deux
sorties viennent du même passage du même script sur la même source : aucune
divergence n'est possible."""

from __future__ import annotations

import statistics
from collections.abc import Iterable

_COLUMNS = (
    "Domaine",
    "Fonctionnalité",
    "id",
    "Santé",
    "Δ",
    "Priorité",
    "tests",
    "atteignabilité",
    "garde",
    "dette",
)


def _cell(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _delta(identifier: str, health: float | None, previous: dict[str, float]) -> str:
    if health is None or identifier not in previous:
        return "—"
    difference = health - previous[identifier]
    if abs(difference) < 0.05:
        return "="
    return f"{difference:+.1f}"


def render(rows: Iterable[dict], *, previous: dict[str, float], date: str) -> str:
    rows = sorted(rows, key=lambda row: row["rang"], reverse=True)
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    lines = [
        "# Bilan de fonctionnalités — GeoStudio",
        "",
        f"**Généré le {date}** par "
        "`uv run python scripts/feature_health_cli.py --repo .. --write`. "
        "**Ne pas éditer à la main** : ce fichier est regénéré à chaque clôture de SP.",
        "",
        f"{len(rows)} fonctionnalités — santé médiane "
        f"{statistics.median(measured):.1f} sur {len(measured)} mesurables.",
        "",
        "La **santé** est calculée (quatre sous-scores, spec §3) ; la **priorité** est "
        "déclarée (spec §4). Les deux ne sont jamais moyennées. Le tri est "
        "`priorité × (100 − santé)`.",
        "",
        "## Par domaine",
        "",
        # Colonnes volontairement dans cet ordre (pas « Domaine | ... ») : la
        # ligne d'en-tête de cette table de synthèse ne doit pas commencer par
        # « | Domaine » — ce préfixe désigne sans ambiguïté l'en-tête de la
        # table « Toutes les fonctionnalités » plus bas (même colonne de tête),
        # seule table dont l'en-tête est recherché par préfixe en aval.
        "| Fonctionnalités | Domaine | Santé médiane |",
        "|---|---|---|",
    ]
    domains: dict[str, list[float]] = {}
    for row in rows:
        if row["sante"] is not None:
            domains.setdefault(row["feature"].domain, []).append(row["sante"])
    for domain in sorted(domains):
        values = domains[domain]
        lines.append(f"| {len(values)} | **{domain}** | {statistics.median(values):.1f} |")
    lines += [
        "",
        "## Toutes les fonctionnalités",
        "",
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "---|" * len(_COLUMNS),
    ]
    for row in rows:
        feature = row["feature"]
        subscores = row["sous_scores"]
        lines.append(
            "| {domain} | {name} | `{identifier}` | {health} | {delta} | {priority} "
            "| {tests} | {reach} | {guard} | {debt} |".format(
                domain=feature.domain,
                name=feature.name.replace("|", "/"),
                identifier=feature.identifier,
                health=_cell(row["sante"]),
                delta=_delta(feature.identifier, row["sante"], previous),
                priority=feature.priority,
                tests=_cell(subscores["tests"].value),
                reach=_cell(subscores["atteignabilite"].value),
                guard=_cell(subscores["garde"].value),
                debt=_cell(subscores["dette"].value),
            )
        )
    return "\n".join(lines) + "\n"
