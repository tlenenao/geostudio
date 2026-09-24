# SPDX-License-Identifier: Apache-2.0
"""Allowlist gelée des 50 algorithmes QGIS Processing historiquement exposés
par transform.qgis (design SP-15d §5/§10, moteur retiré — Task 28 du volet 3
de retrait du sidecar QGIS). Conservée comme référentiel historique de
correspondance FME↔QGIS (aucune ligne `qgis_frozen`/`engine: "qgis"` ne
subsiste dans la matrice de couverture FME depuis Task 31 du retrait — le
mécanisme de validation de `scripts/fme_coverage_cli.py` qui la consommait
n'a donc plus rien à valider ; il reste en place pour toute ligne future qui
referait référence à ces algorithmes). Généré par
scripts/generate_qgis_algorithm_schemas.py contre l'image pinnée
qgis/qgis:release-3_34 — ne pas éditer qgis_algorithms.json à la main,
relancer le script si l'allowlist doit changer."""

import json
from pathlib import Path

QGIS_ALGORITHMS: dict[str, dict] = json.loads(
    (Path(__file__).parent / "qgis_algorithms.json").read_text()
)
