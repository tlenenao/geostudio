# SPDX-License-Identifier: Apache-2.0
"""Régénère core/app/pipelines/ops/qgis_algorithms.json depuis
`qgis_process help <id> --json`, exécuté dans l'image pinnée
qgis/qgis:release-3_34 (design SP-15d §2, §5). Offline uniquement — ne
tourne jamais au runtime du cœur. Relancer manuellement si la liste
ALLOWLIST_IDS change :

    python scripts/generate_qgis_algorithm_schemas.py
"""
import json
import subprocess
import sys
from pathlib import Path

QGIS_IMAGE = "qgis/qgis:release-3_34"

# 50 algorithmes vérifiés réels contre `qgis_process list` (base +
# grassprovider activé) pendant le spike de design — design SP-15d §10.
# CORRECTIF (vérifié indépendamment à l'exécution de Task 1, contre le même
# conteneur pinné) : 6 ids du spike initial portaient un préfixe de provider
# erroné (native: -> qgis:/grass7:) et 1 id (native:selectbyattribute)
# n'existe pas du tout en tant qu'algorithme Processing — remplacé par
# native:polygonstolines (décision humaine, cf. progress ledger SP-15d).
ALLOWLIST_IDS = [
    "native:dissolve", "native:simplifygeometries", "native:smoothgeometry",
    "native:centroids", "native:convexhull", "native:multiparttosingleparts",
    "native:fixgeometries", "native:deleteholes", "native:extractvertices",
    "native:pointsalonglines", "native:densifygeometriesgivenaninterval",
    "native:snapgeometries", "qgis:minimumboundinggeometry",
    "native:voronoipolygons", "native:delaunaytriangulation",
    "native:union", "native:difference", "native:symmetricaldifference",
    "native:clip", "native:mergevectorlayers", "native:splitvectorlayer",
    "native:multiringconstantbuffer",
    "native:joinattributesbylocation", "native:extractbylocation",
    "native:extractbyattribute", "native:polygonstolines",
    "native:nearestneighbouranalysis", "native:zonalstatisticsfb",
    "native:rasterlayerzonalstats", "qgis:heatmapkerneldensityestimation",
    "native:creategrid", "native:fieldcalculator",
    "qgis:tininterpolation", "qgis:idwinterpolation",
    "native:shortestpathpointtopoint", "native:serviceareafrompoint",
    "native:hillshade", "native:slope", "native:aspect",
    "gdal:contour", "gdal:polygonize", "gdal:rasterize", "gdal:sieve",
    "gdal:proximity", "gdal:warpreproject", "gdal:viewshed",
    "grass7:r.watershed", "grass7:r.slope.aspect", "grass7:r.fill.dir",
    "grass7:r.flow",
]

OUTPUT_PATH = Path(__file__).parent.parent / "core" / "app" / "pipelines" / "ops" / "qgis_algorithms.json"

# grassprovider est désactivé par défaut et son état ne survit pas entre deux
# `docker run --rm` distincts (vérifié à l'exécution) : pour tout id grass7:*,
# l'activation doit être chaînée dans le MÊME appel de conteneur que la
# commande `help`.
GRASS_ENABLE_CMD = "qgis_process plugins enable grassprovider >/dev/null 2>&1"


def _type_id(type_field) -> str:
    # CORRECTIF (vérifié à l'exécution de Task 1) : pour la plupart des
    # paramètres, "type" est un objet {"id": ..., ...}, mais pour certains
    # paramètres custom (ex. INTERPOLATION_DATA de qgis:tininterpolation /
    # qgis:idwinterpolation) "type" est directement une chaîne (ex.
    # "idw_interpolation_data"). On normalise les deux formes vers un id str,
    # sans changer le contrat de sortie ({"type": str}).
    if isinstance(type_field, dict):
        return type_field.get("id", "unknown")
    if isinstance(type_field, str) and type_field:
        return type_field
    return "unknown"


def fetch_schema(algorithm_id: str) -> dict:
    if algorithm_id.startswith("grass7:"):
        argv = [
            "docker", "run", "--rm", "-e", "QT_QPA_PLATFORM=offscreen", QGIS_IMAGE,
            "bash", "-c", f"{GRASS_ENABLE_CMD} && qgis_process help {algorithm_id} --json",
        ]
    else:
        argv = [
            "docker", "run", "--rm", "-e", "QT_QPA_PLATFORM=offscreen", QGIS_IMAGE,
            "qgis_process", "help", algorithm_id, "--json",
        ]
    result = subprocess.run(argv, capture_output=True, text=True, check=True)
    raw = json.loads(result.stdout)
    parameters = {
        name: {
            "optional": bool(p.get("optional", False)),
            "type": _type_id(p.get("type")),
            **({"default": p["default_value"]} if "default_value" in p else {}),
        }
        for name, p in raw.get("parameters", {}).items()
    }
    return {"name": raw["algorithm_details"]["name"], "parameters": parameters}


def main() -> None:
    if len(ALLOWLIST_IDS) != len(set(ALLOWLIST_IDS)):
        raise SystemExit("ALLOWLIST_IDS contains duplicates")
    schemas: dict[str, dict] = {}
    for algorithm_id in ALLOWLIST_IDS:
        print(f"fetching {algorithm_id}...", file=sys.stderr)
        schemas[algorithm_id] = fetch_schema(algorithm_id)
    OUTPUT_PATH.write_text(json.dumps(schemas, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(schemas)} algorithms to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
