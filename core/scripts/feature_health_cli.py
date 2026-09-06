# SPDX-License-Identifier: Apache-2.0
"""Bilan de santé des fonctionnalités — calcul, garde-fou et rendu (SP-61).

    PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
    PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write

`--check` n'écrit rien : il calcule et applique les deux planchers de
`feature_health_thresholds.json`. `--write` regénère
`docs/revue/bilan-fonctionnalites.{html,md}` et ajoute un instantané à
`docs/revue/historique-sante.jsonl`."""

from __future__ import annotations

import argparse
import datetime
import pathlib
import statistics
import subprocess
import sys

from scripts.feature_health import history, quality, scoring
from scripts.feature_health.coverage_facts import collect_coverage_facts, score_tests
from scripts.feature_health.debt import collect_debt_facts, score_debt
from scripts.feature_health.mcp_surface import index_mcp_tools
from scripts.feature_health.model import load_inventory
from scripts.feature_health.reachability import collect_reachability_facts, score_reachability
from scripts.feature_health.rest_surface import index_rest_routes, rest_surface_ids, score_guard

INVENTORY = "docs/revue/inventaire-fonctionnalites.jsonl"
JOURNAL = "docs/revue/historique-sante.jsonl"
THRESHOLDS = "core/scripts/feature_health_thresholds.json"


def compute(repo: pathlib.Path):
    features = load_inventory(repo / INVENTORY)
    routes = index_rest_routes(repo)
    reach = collect_reachability_facts(
        repo, rest_paths=rest_surface_ids(routes), mcp_tools=frozenset(index_mcp_tools(repo))
    )
    coverage = collect_coverage_facts(repo)
    debt_items = collect_debt_facts(repo)
    quality_facts = quality.collect_quality_facts(repo)
    thresholds = scoring.load_thresholds(repo / THRESHOLDS)
    rows = []
    for feature in features:
        subscores = {
            "tests": score_tests(feature, coverage),
            "atteignabilite": score_reachability(feature, reach),
            "garde": score_guard(feature, routes),
            "dette": score_debt(feature, debt_items),
        }
        value = scoring.weighted_health(subscores, thresholds.weights)
        rows.append(
            {
                "feature": feature,
                "sante": value,
                "sous_scores": subscores,
                "qualite": quality.quality_for(feature, quality_facts),
                "rang": scoring.priority_rank(feature, value),
            }
        )
    return rows, thresholds


def _check(rows, thresholds) -> int:
    measured = [row["sante"] for row in rows if row["sante"] is not None]
    median = statistics.median(measured) if measured else 0.0
    failures = [
        f"{row['feature'].identifier} : santé {row['sante']:.1f} < plancher "
        f"{thresholds.floor_high_priority}"
        for row in rows
        if row["feature"].priority == "haute"
        and row["sante"] is not None
        and row["sante"] < thresholds.floor_high_priority
    ]
    print(f"Santé médiane : {median:.1f} (plancher {thresholds.floor_median})")
    if median < thresholds.floor_median:
        failures.append(f"santé médiane {median:.1f} < plancher {thresholds.floor_median}")
    for failure in failures:
        print(f"ÉCHEC : {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    rows, thresholds = compute(repo)
    if arguments.write:
        # Import tardif : les deux rendus arrivent en Tâche 7, alors que `--check`
        # doit déjà fonctionner en Tâche 6. Un import de module manquant en tête
        # de fichier casserait `--check` pour une raison sans rapport avec lui.
        from scripts.feature_health import render_html, render_md

        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        date = datetime.date.today().isoformat()
        previous = history.last_snapshot(repo / JOURNAL)
        (repo / "docs/revue/bilan-fonctionnalites.md").write_text(
            render_md.render(rows, previous=previous, date=date), encoding="utf-8"
        )
        (repo / "docs/revue/bilan-fonctionnalites.html").write_text(
            render_html.render(rows, previous=previous, date=date, commit=commit),
            encoding="utf-8",
        )
        history.append_snapshot(
            repo / JOURNAL,
            [
                (
                    row["feature"].identifier,
                    row["sante"],
                    {name: score.value for name, score in row["sous_scores"].items()},
                )
                for row in rows
            ],
            commit=commit,
            date=date,
        )
        print(f"{len(rows)} fonctionnalités — bilan et journal écrits.")
    return _check(rows, thresholds) if arguments.check else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
