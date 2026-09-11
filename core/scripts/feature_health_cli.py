# SPDX-License-Identifier: Apache-2.0
"""Bilan de santé des fonctionnalités — calcul, garde-fou et rendu (SP-61).

    PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
    PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
    PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check-fresh

`--check` n'écrit rien : il calcule et applique les deux planchers de
`feature_health_thresholds.json`. `--write` regénère
`docs/revue/bilan-fonctionnalites.{html,md}` et ajoute un instantané à
`docs/revue/historique-sante.jsonl`. `--check-fresh` (REV-181) est un
troisième mode, DIFFÉRENT de `--check` : il ne dit rien sur les planchers,
il vérifie que les deux rendus committés ont bien été régénérés après le
dernier changement de code/inventaire — en recalculant les deux rendus en
mémoire et en les diffant contre les fichiers commités, plutôt qu'en
espérant qu'un contributeur n'a pas oublié `--write` (la classe de dérive
documentée par ce SP, piège n°12 du dépôt)."""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
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


_BILAN_MD = "docs/revue/bilan-fonctionnalites.md"
_BILAN_HTML = "docs/revue/bilan-fonctionnalites.html"
_DATA_BLOCK = re.compile(r'<script type="application/json" id="bilan-data">(.*?)</script>', re.S)


def _extract_committed_metadata(repo: pathlib.Path) -> tuple[str, str, dict[str, float]]:
    """Ce qu'il faut pour rejouer EXACTEMENT le rendu committé (date, commit,
    previous) — jamais recalculé indépendamment. Piège évité : le journal
    (`historique-sante.jsonl`) a déjà avancé d'un cran par rapport à l'état
    qui a produit ce rendu — `history.append_snapshot()` est appelé par
    `--write` dans le même passage qui calcule `previous`, donc
    `history.last_snapshot()` relu maintenant renvoie le relevé **courant**,
    pas l'ancien. `previous` est reconstruit directement depuis le JSON
    embarqué du HTML committé : `previous[id] = sante - delta` — round-trip
    exact, `render_html.render`/`render_md.render` re-arrondissent `delta` au
    même chiffre après coup (`round(sante - previous[id], 1)`)."""
    path = repo / _BILAN_HTML
    match = _DATA_BLOCK.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{path} : bloc de données JSON introuvable")
    payload = json.loads(match.group(1))
    previous = {
        item["id"]: item["sante"] - item["delta"]
        for item in payload["fonctionnalites"]
        if item["sante"] is not None and item["delta"] is not None
    }
    return payload["date"], payload["commit"], previous


def _check_fresh(rows, repo: pathlib.Path) -> int:
    from scripts.feature_health import render_html, render_md

    date, commit, previous = _extract_committed_metadata(repo)
    fresh = {
        _BILAN_MD: render_md.render(rows, previous=previous, date=date),
        _BILAN_HTML: render_html.render(rows, previous=previous, date=date, commit=commit),
    }
    stale = [
        name
        for name, content in fresh.items()
        if (repo / name).read_text(encoding="utf-8") != content
    ]
    if stale:
        for name in stale:
            print(f"PÉRIMÉ : {name}", file=sys.stderr)
        print(
            "Rendus périmés — régénérer avec `PYTHONPATH=. uv run python "
            "scripts/feature_health_cli.py --repo .. --write`.",
            file=sys.stderr,
        )
        return 1
    print("Rendus committés à jour.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check-fresh", action="store_true", dest="check_fresh")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    rows, thresholds = compute(repo)
    if arguments.check_fresh:
        # Mode indépendant de --check/--write (jamais combiné en pratique,
        # cf. ci.yml : un step dédié). Retour anticipé — ni le calcul des
        # planchers de --check ni la régénération de --write n'ont de sens
        # ici, seule la comparaison au disque compte.
        return _check_fresh(rows, repo)
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
