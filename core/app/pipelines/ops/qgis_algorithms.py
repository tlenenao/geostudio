# SPDX-License-Identifier: Apache-2.0
"""Allowlist gelée des 50 algorithmes QGIS Processing exposés par
transform.qgis (design SP-15d §5/§10). Généré par
scripts/generate_qgis_algorithm_schemas.py contre l'image pinnée
qgis/qgis:release-3_34 — ne pas éditer qgis_algorithms.json à la main,
relancer le script si l'allowlist doit changer."""
import json
from pathlib import Path

QGIS_ALGORITHMS: dict[str, dict] = json.loads(
    (Path(__file__).parent / "qgis_algorithms.json").read_text()
)
