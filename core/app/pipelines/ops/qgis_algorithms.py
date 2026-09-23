# SPDX-License-Identifier: Apache-2.0
"""Allowlist gelée des 50 algorithmes QGIS Processing historiquement exposés
par transform.qgis (design SP-15d §5/§10, moteur retiré — Task 28 du volet 3
de retrait du sidecar QGIS). Ne sert plus qu'à valider les lignes
`qgis_frozen` restantes de la matrice de couverture FME
(docs/revue/matrice-couverture-fme.jsonl) : scripts/fme_coverage_cli.py
vérifie que le `geostudio_equivalent` de toute ligne `engine: "qgis"` est
une clé réelle de QGIS_ALGORITHMS — ces algorithmes (essentiellement
raster) restent hors périmètre du moteur de pipeline DuckDB. Généré par
scripts/generate_qgis_algorithm_schemas.py contre l'image pinnée
qgis/qgis:release-3_34 — ne pas éditer qgis_algorithms.json à la main,
relancer le script si l'allowlist doit changer."""

import json
from pathlib import Path

QGIS_ALGORITHMS: dict[str, dict] = json.loads(
    (Path(__file__).parent / "qgis_algorithms.json").read_text()
)
