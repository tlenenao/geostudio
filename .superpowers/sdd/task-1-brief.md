## Task 1: QGIS algorithm allowlist — generator script + frozen schema file

**Files:**
- Create: `scripts/generate_qgis_algorithm_schemas.py`
- Create: `core/app/pipelines/ops/qgis_algorithms.json` (generated output,
  committed)
- Create: `core/app/pipelines/ops/qgis_algorithms.py` (thin loader)
- Test: `core/tests/test_pipeline_qgis_algorithms.py`

**Interfaces:**
- Produces: `QGIS_ALGORITHMS: dict[str, dict]` in
  `app.pipelines.ops.qgis_algorithms`, keyed by algorithm id (e.g.
  `"native:simplifygeometries"`), each value shaped
  `{"name": str, "parameters": {PARAM_NAME: {"optional": bool, "type": str,
  "default": <any>?}}}`. Consumed by Task 2 (`TransformQgisParams`
  validator) and Task 6 (`GET /pipelines/ops/qgis-algorithms`).

- [ ] **Step 1: Write the generator script**

Create `scripts/generate_qgis_algorithm_schemas.py`:

```python
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
            "type": p.get("type", {}).get("id", "unknown"),
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
```

- [ ] **Step 2: Run the generator against the real pinned image**

Run: `docker pull qgis/qgis:release-3_34 && python scripts/generate_qgis_algorithm_schemas.py`

Expected: stderr prints 50 `fetching ...` lines, then `wrote 50 algorithms
to .../qgis_algorithms.json`. This creates
`core/app/pipelines/ops/qgis_algorithms.json` with 50 top-level keys.

Spot-check the two algorithms this plan's later tasks rely on (verified
during design, confirm the generated file matches):

```bash
python3 -c "
import json
d = json.load(open('core/app/pipelines/ops/qgis_algorithms.json'))
print(sorted(d['native:simplifygeometries']['parameters']))
print(sorted(d['native:centroids']['parameters']))
"
```

Expected: `['INPUT', 'METHOD', 'OUTPUT', 'TOLERANCE']` and `['ALL_PARTS',
'INPUT', 'OUTPUT']` — all four `native:simplifygeometries` params and all
three `native:centroids` params are non-optional (verified during design).

- [ ] **Step 3: Write the thin loader module**

Create `core/app/pipelines/ops/qgis_algorithms.py`:

```python
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
```

- [ ] **Step 4: Write the failing tests**

Create `core/tests/test_pipeline_qgis_algorithms.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

EXPECTED_IDS = {
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
}


def test_allowlist_has_exactly_fifty_algorithms():
    assert len(QGIS_ALGORITHMS) == 50


def test_allowlist_matches_expected_ids():
    assert set(QGIS_ALGORITHMS) == EXPECTED_IDS


def test_each_entry_has_name_and_nonempty_parameters():
    for algo_id, schema in QGIS_ALGORITHMS.items():
        assert isinstance(schema["name"], str) and schema["name"], algo_id
        assert isinstance(schema["parameters"], dict) and schema["parameters"], algo_id
        for param_name, param in schema["parameters"].items():
            assert isinstance(param["optional"], bool), (algo_id, param_name)
            assert isinstance(param["type"], str), (algo_id, param_name)


def test_simplify_required_params_match_spike_findings():
    required = {
        n for n, p in QGIS_ALGORITHMS["native:simplifygeometries"]["parameters"].items()
        if not p["optional"]
    }
    assert required == {"INPUT", "METHOD", "OUTPUT", "TOLERANCE"}


def test_centroids_required_params_match_spike_findings():
    required = {
        n for n, p in QGIS_ALGORITHMS["native:centroids"]["parameters"].items()
        if not p["optional"]
    }
    assert required == {"ALL_PARTS", "INPUT", "OUTPUT"}


def test_dissolve_field_param_is_optional():
    assert QGIS_ALGORITHMS["native:dissolve"]["parameters"]["FIELD"]["optional"] is True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_qgis_algorithms.py -v`
Expected: 6 passed (the file was generated in Step 2, before the tests were
written — this is the one task in this plan where generation precedes the
test, since the test's job is to lock in what got generated, not drive new
production code).

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_qgis_algorithm_schemas.py \
  core/app/pipelines/ops/qgis_algorithms.json \
  core/app/pipelines/ops/qgis_algorithms.py \
  core/tests/test_pipeline_qgis_algorithms.py
git commit -m "feat(core): freeze the 50-id QGIS Processing algorithm allowlist"
```

---

