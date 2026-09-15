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
dépôt (`app.pipelines.ops.schemas.ops_catalog`, `app.pipelines.ops.
qgis_algorithms.QGIS_ALGORITHMS`) — jamais contre une copie déclarée dans le
JSONL lui-même. --write régénère docs/revue/matrice-couverture-fme.md depuis
le JSONL. Pas de porte CI : --check n'est appelé dans aucun job de ci.yml,
ce n'est pas une surface produit."""

from __future__ import annotations

import json
import pathlib
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
