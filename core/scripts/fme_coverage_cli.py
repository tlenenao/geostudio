# SPDX-License-Identifier: Apache-2.0
"""Matrice de couverture FME→GeoStudio (design 2026-09-15) — CLI léger, sans
scoring ni porte CI, patron simplifié de scripts/feature_health_cli.py.

    PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --check
    PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --write

La commande nue échoue en ModuleNotFoundError sans PYTHONPATH=. — même
gotcha que feature_health_cli.py/export_openapi.py, à ne pas répéter une 3e
fois sans avertissement inline.

--check vérifie mécaniquement les 3 règles du design (cf. docs/superpowers/
specs/2026-09-15-matrice-couverture-fme-design.md) contre le code réel du
dépôt (`app.pipelines.ops.contracts.ops_catalog`, `app.pipelines.ops.
qgis_algorithms.QGIS_ALGORITHMS`) — jamais contre une copie déclarée dans le
JSONL lui-même. --write régénère docs/revue/matrice-couverture-fme.md depuis
le JSONL. Pas de porte CI : --check n'est appelé dans aucun job de ci.yml,
ce n'est pas une surface produit."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass

JSONL = "docs/revue/matrice-couverture-fme.jsonl"
RENDERED_MD = "docs/revue/matrice-couverture-fme.md"

_VALID_STATUSES = {
    "implemented",
    "planned_duckdb",
    "planned_gdal",
    "planned_pdal",
    "planned_otb",
    "planned_rust",
    "qgis_frozen",
    "license_blocked",
    "out_of_scope",
    "unknown",
}


@dataclass(frozen=True)
class Row:
    fme_transformer: str
    fme_category: str
    fme_description: str
    geostudio_equivalent: str | None
    engine: str
    engine_license: str
    coverage_status: str
    usage_frequency: str
    notes: str

    @staticmethod
    def from_dict(data: dict) -> Row:
        status = data["coverage_status"]
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"{data.get('fme_transformer', '?')!r} : coverage_status inconnu {status!r}"
            )
        return Row(
            fme_transformer=data["fme_transformer"],
            fme_category=data["fme_category"],
            fme_description=data["fme_description"],
            geostudio_equivalent=data.get("geostudio_equivalent"),
            engine=data["engine"],
            engine_license=data["engine_license"],
            coverage_status=status,
            usage_frequency=data["usage_frequency"],
            notes=data.get("notes", ""),
        )


def load_rows(path: pathlib.Path) -> list[Row]:
    rows: list[Row] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} : JSON invalide ({exc})") from exc
        rows.append(Row.from_dict(data))
    return rows


_NOT_YET_INTEGRATED_ENGINES = ("gdal", "pdal", "otb")


def check_rows(rows: list[Row], *, ops: dict, qgis_algorithms: dict) -> list[str]:
    errors: list[str] = []
    for row in rows:
        if row.coverage_status == "implemented" and row.engine == "duckdb":
            if row.geostudio_equivalent not in ops:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans ops_catalog()"
                )
        if row.engine == "qgis":
            if row.geostudio_equivalent not in qgis_algorithms:
                errors.append(
                    f"{row.fme_transformer!r} : geostudio_equivalent "
                    f"{row.geostudio_equivalent!r} n'existe pas dans QGIS_ALGORITHMS"
                )
        if row.coverage_status == "implemented" and (
            row.engine in _NOT_YET_INTEGRATED_ENGINES or row.engine.startswith("rust:")
        ):
            errors.append(
                f"{row.fme_transformer!r} : coverage_status=implemented avec "
                f"engine={row.engine!r}, mais ce moteur n'est pas encore intégré "
                "dans core/app/pipelines/ — utiliser planned_* jusqu'à ce que le "
                "sous-projet moteur correspondant ait livré"
            )
    return errors


def _escape_md_cell(value: str) -> str:
    """Échappe une valeur de cellule pour un tableau markdown : un `|`
    littéral casserait la structure du tableau en créant une colonne
    supplémentaire (ex. un `notes` mentionnant l'opérateur `||` de DuckDB) ;
    un saut de ligne intégré casserait la ligne elle-même."""
    return value.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ")


def render_md(rows: list[Row]) -> str:
    lines = ["# Matrice de couverture FME→GeoStudio", ""]
    lines.append(f"{len(rows)} transformers FME recensés.")
    lines.append("")
    lines.append("## Résumé par statut")
    lines.append("")
    lines.append("| Statut | Nombre |")
    lines.append("|---|---|")
    status_counts = Counter(row.coverage_status for row in rows)
    for status in sorted(status_counts):
        lines.append(f"| `{status}` | {status_counts[status]} |")
    lines.append("")
    lines.append("## Résumé par moteur")
    lines.append("")
    lines.append("| Moteur | Nombre |")
    lines.append("|---|---|")
    engine_counts = Counter(row.engine for row in rows)
    for engine in sorted(engine_counts):
        lines.append(f"| `{engine}` | {engine_counts[engine]} |")
    lines.append("")
    lines.append("## Détail par catégorie")
    lines.append("")
    categories = sorted({row.fme_category for row in rows})
    lines.append("Sommaire : " + " · ".join(f"[{cat}](#{_md_anchor(cat)})" for cat in categories))
    lines.append("")
    for category in categories:
        cat_rows = sorted(
            (row for row in rows if row.fme_category == category),
            key=lambda r: r.fme_transformer,
        )
        lines.append(f"### {category} ({len(cat_rows)})")
        lines.append("")
        lines.append(
            "| Transformer FME | Équivalent GeoStudio | Moteur | Licence | "
            "Statut | Fréquence | Notes |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for row in cat_rows:
            lines.append(
                "| "
                + " | ".join(
                    _escape_md_cell(cell)
                    for cell in [
                        row.fme_transformer,
                        row.geostudio_equivalent or "",
                        row.engine,
                        row.engine_license,
                        f"`{row.coverage_status}`",
                        row.usage_frequency,
                        row.notes,
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _md_anchor(heading: str) -> str:
    """Reproduit la règle d'ancrage GitHub : minuscules, espaces → tirets,
    ponctuation retirée — pour que le sommaire pointe vers le bon `###`."""
    slug = heading.lower().replace(" ", "-")
    return "".join(c for c in slug if c.isalnum() or c == "-")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="..", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    repo = arguments.repo.resolve()
    rows = load_rows(repo / JSONL)

    if arguments.write:
        (repo / RENDERED_MD).write_text(render_md(rows), encoding="utf-8")
        print(f"{len(rows)} lignes — {RENDERED_MD} régénéré.")

    if arguments.check:
        from app.pipelines.ops.contracts import ops_catalog
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

        errors = check_rows(rows, ops=ops_catalog(), qgis_algorithms=QGIS_ALGORITHMS)
        for error in errors:
            print(f"ERREUR : {error}", file=sys.stderr)
        if errors:
            return 1
        print(f"{len(rows)} lignes vérifiées, aucune erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
