# SPDX-License-Identifier: Apache-2.0
"""Allowlist gelée des 50 algorithmes QGIS Processing historiquement exposés
par transform.qgis (design SP-15d §5/§10, moteur retiré — Task 28 du volet 3
de retrait du sidecar QGIS). Conservée comme référentiel historique de
correspondance FME↔QGIS (aucune ligne `qgis_frozen`/`engine: "qgis"` ne
subsiste dans la matrice de couverture FME depuis Task 31 du retrait — le
mécanisme de validation de `scripts/fme_coverage_cli.py` qui la consommait
n'a donc plus rien à valider ; il reste en place pour toute ligne future qui
referait référence à ces algorithmes). Généré à l'origine contre l'image pinnée
qgis/qgis:release-3_34 par un script de génération supprimé avec le sidecar
(REV-199 M6) : `qgis_algorithms.json` est désormais figé, ne pas l'éditer."""

import json
from pathlib import Path

QGIS_ALGORITHMS: dict[str, dict] = json.loads(
    (Path(__file__).parent / "qgis_algorithms.json").read_text()
)
