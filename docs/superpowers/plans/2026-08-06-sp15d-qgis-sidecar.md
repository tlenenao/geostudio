# SP-15d — Pipeline : sidecar `qgis_process` (étage 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic `transform.qgis` op to the Pipeline catalogue that
invokes a QGIS Processing algorithm (from a 50-id frozen allowlist) via an
isolated `qgis-worker` sidecar, closing the "long-tail geo" gap the étage-1
DuckDB ops (SP-15c) can't cover.

**Architecture:** One new Pydantic param model (`TransformQgisParams`)
registered in the existing op catalogue, validated against a JSON allowlist
file frozen in the repo (`core/app/pipelines/ops/qgis_algorithms.json`,
generated offline by a script against a pinned `qgis/qgis:release-3_34`
image — never fetched live at runtime). A new minimal service
(`deploy/qgis-worker/`, stdlib `http.server`, no FastAPI) wraps
`qgis_process` behind one `POST /run` route, isolated (no DB creds, no
external network) on a shared `etl-scratch` docker volume, behind
`profiles: ["etl"]`. `runtime.py` gains one dispatch branch that breaks the
existing SQL-view chain for this one op: materialize the upstream DuckDB
relation to a CRS-tagged GeoPackage (`COPY ... FORMAT GDAL ... SRS`), call
the sidecar over internal HTTP (`httpx`, already a dependency), reload the
result (`ST_Read`) as a new `TEMP TABLE`. Every mechanical piece below
(image tag, JSON contract, error format, GRASS provider activation, the
DuckDB↔GDAL round-trip, the "undefined CRS" gotcha) was verified against a
real `qgis/qgis:release-3_34` container and a real DuckDB connection during
design — this plan's code reflects what was actually observed, not
documentation.

**Tech Stack:** Python/FastAPI (`core/`), Pydantic v2, DuckDB in-process
(`spatial` extension), `httpx`, stdlib `http.server` (sidecar), Docker
Compose, `qgis/qgis:release-3_34`.

## Global Constraints

- **No shell/canvas changes anywhere in this plan.** `transform.qgis` is
  authorable via REST/MCP only in v0 (design §1 non-goal). Do not touch
  `PipelineCanvas.tsx`, `PipelinePalette.tsx`, `PipelineNodeInspector.tsx`,
  or any other `shell/` file.
- **No `reader.connector`/dlt, no `transform.sql`.** Out of scope (SP-15e,
  Phase 4 respectively).
- **No DB migration.** `transform.qgis` is a pure data-flow op, nothing new
  to persist beyond the existing `Pipeline`/`PipelineNode` shape (`params:
  dict` already accepts arbitrary JSON).
- **No behavior change to the 14 existing ops** (`reader.collection`,
  `transform.filter/select/derive/aggregate/join/buffer/reproject/
  intersection/countWithin/h3Aggregate`, `writer.collection/export/dataset`)
  or to `PipelineBuilderPage`/canvas/palette.
- **`qgis/qgis:release-3_34` is the pinned image tag everywhere** (compose
  service, generator script, Dockerfile, docs). Never `:latest` — verified
  during design to resolve to an unstable `4.3.0-Master` development build.
- **`QT_QPA_PLATFORM=offscreen` must be set wherever `qgis_process` runs**
  (Dockerfile `ENV` and/or compose `environment:`) — without it, Qt fails
  before reaching any command (verified: no display in a headless
  container).
- **DuckDB's `COPY ... TO ... WITH (FORMAT GDAL, DRIVER 'GPKG')` writes an
  "Undefined geographic SRS" if no `SRS` option is passed** (verified
  empirically — `ogrinfo` on an un-tagged export shows `GEOGCRS["Undefined
  geographic SRS", ...]`). Every `COPY` in this plan that feeds
  `transform.qgis`'s input MUST include `SRS 'EPSG:{input_srid}'` (verified
  DuckDB accepts this option and writes a real CRS).
- **`qgis_process` distances/tolerances are in the input layer's native CRS
  units, not auto-converted to meters** (verified: `native:buffer` with
  `DISTANCE=500` on an EPSG:4326 layer buffers by 500 *degrees*, not
  meters). This plan does not attempt to fix this — same non-goal posture as
  SP-15c's CRS-reconciliation non-goal. Pipeline authors are responsible for
  reprojecting to an appropriate CRS before an op where this matters
  (documented in `TransformQgisParams`'s docstring in Task 2).
- **`grassprovider` is present in the image but disabled by default**
  (verified: `qgis_process list` shows zero `grass:*` ids until `qgis_process
  plugins enable grassprovider` runs). Must be baked into the sidecar image
  at build time (Task 4's Dockerfile), not enabled per-request.
- **The real GRASS algorithm namespace is `grass:*`, not `grass7:*`**
  (verified against the pinned image — the feasibility study's `grass7:*`
  wording is an older-version convention; do not use it anywhere in code,
  tests, or the allowlist).
- **`qgis_process run <id> -` contract, verified against a real container**:
  success = exit code 0, complete JSON on stdout (top-level `results` key
  has output paths), nothing on stderr worth parsing. Failure = exit code
  ≠0, **stdout is 0 bytes** (verified), stderr contains a line starting with
  literal `ERROR:` followed by an indented detail line, mixed in with
  verbose provider-init logging.
- **Both `worker` and the new `qgis-worker` container run as root**
  (`core/Dockerfile` has no `USER` directive; `qgis/qgis` base image is root
  by default, verified). This means no file-ownership mismatch on the shared
  `etl-scratch` volume — do not add a `USER` switch to either image as part
  of this plan, that would introduce a permission problem that doesn't
  exist today.
- Every new item/config write must go through `write_audit`
  (`app/audit/writer.py`) — moot for this plan: `transform.qgis` performs no
  item/config writes of its own (it's a transform, not a writer).
- `can()`'s `Action` type is `Literal["read", "write", "delete", "share"]` —
  no `"update"`. Not directly relevant here (`transform.qgis` doesn't touch
  collections), noted for consistency with the rest of the module.

---

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
ALLOWLIST_IDS = [
    "native:dissolve", "native:simplifygeometries", "native:smoothgeometry",
    "native:centroids", "native:convexhull", "native:multiparttosingleparts",
    "native:fixgeometries", "native:deleteholes", "native:extractvertices",
    "native:pointsalonglines", "native:densifygeometriesgivenaninterval",
    "native:snapgeometries", "native:minimumboundinggeometry",
    "native:voronoipolygons", "native:delaunaytriangulation",
    "native:union", "native:difference", "native:symmetricaldifference",
    "native:clip", "native:mergevectorlayers", "native:splitvectorlayer",
    "native:multiringconstantbuffer",
    "native:joinattributesbylocation", "native:extractbylocation",
    "native:extractbyattribute", "native:selectbyattribute",
    "native:nearestneighbouranalysis", "native:zonalstatisticsfb",
    "native:rasterlayerzonalstats", "native:heatmapkerneldensityestimation",
    "native:creategrid", "native:fieldcalculator",
    "qgis:tininterpolation", "qgis:idwinterpolation",
    "native:shortestpathpointtopoint", "native:serviceareafrompoint",
    "native:hillshade", "native:slope", "native:aspect",
    "gdal:contour", "gdal:polygonize", "gdal:rasterize", "gdal:sieve",
    "gdal:proximity", "gdal:warpreproject", "gdal:viewshed",
    "grass:r.watershed", "grass:r.slope.aspect", "grass:r.fill.dir",
    "grass:r.flow",
]

OUTPUT_PATH = Path(__file__).parent.parent / "core" / "app" / "pipelines" / "ops" / "qgis_algorithms.json"


def fetch_schema(algorithm_id: str) -> dict:
    result = subprocess.run(
        [
            "docker", "run", "--rm", "-e", "QT_QPA_PLATFORM=offscreen", QGIS_IMAGE,
            "qgis_process", "help", algorithm_id, "--json",
        ],
        capture_output=True, text=True, check=True,
    )
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
    "native:snapgeometries", "native:minimumboundinggeometry",
    "native:voronoipolygons", "native:delaunaytriangulation",
    "native:union", "native:difference", "native:symmetricaldifference",
    "native:clip", "native:mergevectorlayers", "native:splitvectorlayer",
    "native:multiringconstantbuffer",
    "native:joinattributesbylocation", "native:extractbylocation",
    "native:extractbyattribute", "native:selectbyattribute",
    "native:nearestneighbouranalysis", "native:zonalstatisticsfb",
    "native:rasterlayerzonalstats", "native:heatmapkerneldensityestimation",
    "native:creategrid", "native:fieldcalculator",
    "qgis:tininterpolation", "qgis:idwinterpolation",
    "native:shortestpathpointtopoint", "native:serviceareafrompoint",
    "native:hillshade", "native:slope", "native:aspect",
    "gdal:contour", "gdal:polygonize", "gdal:rasterize", "gdal:sieve",
    "gdal:proximity", "gdal:warpreproject", "gdal:viewshed",
    "grass:r.watershed", "grass:r.slope.aspect", "grass:r.fill.dir",
    "grass:r.flow",
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

## Task 2: Op catalogue — `transform.qgis` param model

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Consumes: `QGIS_ALGORITHMS` (Task 1, `app.pipelines.ops.qgis_algorithms`).
- Produces: `TransformQgisParams` (Pydantic `BaseModel` in
  `app.pipelines.ops.schemas`), registered as `OP_KINDS["transform.qgis"] =
  "transform"` and `OP_PARAMS["transform.qgis"] = TransformQgisParams`.
  Fields: `algorithmId: str`, `params: dict[str, Any]`, `outputSrid: str |
  None`. Consumed by Task 3 (`compiler.py`), Task 5 (`runtime.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_ops_schemas.py`:

```python
def test_fifteenth_op_is_registered():
    assert "transform.qgis" in OP_PARAMS
    assert "transform.qgis" in OP_KINDS
    assert OP_KINDS["transform.qgis"] == "transform"


def test_transform_qgis_accepts_allowlisted_id_with_required_params():
    params = parse_op_params(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
    )
    assert params.algorithmId == "native:centroids"
    assert params.params == {"ALL_PARTS": False}
    assert params.outputSrid is None


def test_transform_qgis_rejects_non_allowlisted_id():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:totallymadeup", "params": {}},
        )


def test_transform_qgis_rejects_missing_required_param():
    # native:centroids requires ALL_PARTS beyond INPUT/OUTPUT (design Task 2 —
    # INPUT/OUTPUT are runtime-injected, never authored, cf. spike finding
    # in test_pipeline_qgis_algorithms.py::test_centroids_required_params_...).
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis", {"algorithmId": "native:centroids", "params": {}},
        )


def test_transform_qgis_does_not_require_input_output_in_params():
    # INPUT/OUTPUT are required by native:simplifygeometries' own schema but
    # are filled in by the runtime (scratch file paths), never by the author.
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "native:simplifygeometries",
            "params": {"METHOD": 0, "TOLERANCE": 1.0},
        },
    )
    assert "INPUT" not in params.params
    assert "OUTPUT" not in params.params


def test_transform_qgis_accepts_optional_output_srid():
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {"TARGET_CRS": "EPSG:2154"},
            "outputSrid": "EPSG:2154",
        },
    )
    assert params.outputSrid == "EPSG:2154"


def test_transform_qgis_rejects_malformed_output_srid():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:dissolve",
             "params": {"SEPARATE_DISJOINT": False},
             "outputSrid": "not-a-crs"},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -k transform_qgis -v`
Expected: FAIL — `KeyError`/`AttributeError`, `transform.qgis` not in
`OP_PARAMS` (doesn't exist yet).

- [ ] **Step 3: Add the `Any` import and `TransformQgisParams`**

Modify `core/app/pipelines/ops/schemas.py` — change the top import:

```python
from typing import Any, Literal
```

Add after `WriterDatasetParams` (before the `OP_KINDS` dict):

```python
class TransformQgisParams(BaseModel):
    """Op générique pour tout algorithme QGIS Processing de l'allowlist
    gelée (app.pipelines.ops.qgis_algorithms.QGIS_ALGORITHMS, design SP-15d
    §5/§10). `params` ne doit JAMAIS contenir INPUT/OUTPUT — le runtime les
    injecte (chemins scratch, design §6). `outputSrid` doit être renseigné
    explicitement quand l'algorithme change le CRS (ex. gdal:warpreproject
    via son propre param TARGET_CRS) ; laissé à None, le SRID de sortie est
    supposé identique à l'entrée — vrai pour la quasi-totalité des 50 op de
    l'allowlist, faux pour un algorithme de reprojection. Aucune conversion
    automatique d'unité : un DISTANCE/TOLERANCE d'un algorithme QGIS est
    dans les unités du CRS natif de la couche d'entrée, jamais auto-converti
    en mètres (vérifié empiriquement en design, §2)."""
    algorithmId: str
    params: dict[str, Any] = Field(default_factory=dict)
    outputSrid: str | None = Field(default=None, pattern=r"^[A-Za-z]+:\d+$")

    @model_validator(mode="after")
    def _check_allowlisted_and_required_params(self) -> "TransformQgisParams":
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

        schema = QGIS_ALGORITHMS.get(self.algorithmId)
        if schema is None:
            raise ValueError(f"algorithme non autorisé : {self.algorithmId}")
        required = {
            name for name, p in schema["parameters"].items() if not p["optional"]
        } - {"INPUT", "OUTPUT"}
        missing = required - self.params.keys()
        if missing:
            raise ValueError(
                f"{self.algorithmId} : paramètres requis manquants {sorted(missing)}"
            )
        return self
```

Add to `OP_KINDS`:

```python
    "transform.qgis": "transform",
```

Add to `OP_PARAMS`:

```python
    "transform.qgis": TransformQgisParams,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass, including the pre-existing 14-op tests (no regression —
`test_all_fourteen_ops_are_registered` from SP-15c will need updating to
15; do that now too):

Modify the existing `test_all_fourteen_ops_are_registered` (or whatever it's
now named) in `core/tests/test_pipeline_ops_schemas.py` to add
`"transform.qgis"` to the expected set and rename to
`test_all_fifteen_ops_are_registered`.

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): transform.qgis op — generic QGIS Processing param model"
```

---

## Task 3: `compiler.py` — SRID tracking for `transform.qgis`

**Files:**
- Modify: `core/app/pipelines/compiler.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `TransformQgisParams` (Task 2).
- Produces: `transform_output_srid("transform.qgis", ...)` now returns
  `int(outputSrid)` when set, else passes `input_srid` through unchanged.
  Consumed by Task 5 (`runtime.py`, called before the qgis dispatch branch).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_compiler.py`:

```python
def test_transform_output_srid_qgis_passes_through_by_default():
    srid = transform_output_srid(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
        input_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_qgis_uses_explicit_output_srid():
    srid = transform_output_srid(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {"TARGET_CRS": "EPSG:2154"},
            "outputSrid": "EPSG:2154",
        },
        input_srid=4326,
    )
    assert srid == 2154
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k qgis -v`
Expected: FAIL — the current fallthrough (`return input_srid`) already
makes the first test pass by accident, but the second test fails (`2154 !=
4326`, `outputSrid` ignored). Confirm this asymmetry before implementing.

- [ ] **Step 3: Implement**

Modify `core/app/pipelines/compiler.py` — add `TransformQgisParams` to the
import from `app.pipelines.ops.schemas`:

```python
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformBufferParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, TransformQgisParams,
    TransformReprojectParams, TransformSelectParams,
)
```

In `transform_output_srid`, add a branch before the final `return
input_srid`:

```python
    if op == "transform.qgis":
        p = TransformQgisParams.model_validate(params)
        return int(p.outputSrid.rsplit(":", 1)[1]) if p.outputSrid is not None else input_srid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: all pass, no regression on the other transform ops' SRID tests.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/compiler.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): transform.qgis SRID tracking via explicit outputSrid"
```

---

## Task 4: `qgis-worker` sidecar service

**Files:**
- Create: `deploy/qgis-worker/Dockerfile`
- Create: `deploy/qgis-worker/server.py`
- Create: `deploy/qgis-worker/allowlist.txt` (generated)
- Create: `scripts/generate_qgis_worker_allowlist.py`
- Modify: `core/tests/conftest.py`
- Modify: `core/pyproject.toml` (new pytest marker)
- Test: `core/tests/test_qgis_worker_sidecar.py`

**Interfaces:**
- Produces: a `POST /run` HTTP contract (`{"algorithmId": str, "inputs":
  dict}` → `200 {...qgis_process JSON...}` | `403 {"error": str}` (not
  allowlisted) | `502 {"error": str}` (qgis_process failed) | `504
  {"error": str}` (timeout)). Consumed by Task 5 (`runtime.py`'s HTTP call).
- Produces: `qgis_worker_url` and `qgis_scratch_dir` session-scoped pytest
  fixtures in `core/tests/conftest.py`, skipping (marker `qgis`) if the
  required env vars are unset — consumed by this task's test and Task 8's.

- [ ] **Step 1: Write the allowlist-ids generator (ids only, no schemas)**

Create `scripts/generate_qgis_worker_allowlist.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Régénère deploy/qgis-worker/allowlist.txt (un id par ligne) depuis la
même liste ALLOWLIST_IDS que scripts/generate_qgis_algorithm_schemas.py —
dupliquée ici plutôt qu'importée (le sidecar ne dépend jamais de core/,
design SP-15d §3/§4 : isolation totale). Relancer si l'allowlist change,
en même temps que generate_qgis_algorithm_schemas.py."""
from pathlib import Path

from generate_qgis_algorithm_schemas import ALLOWLIST_IDS

OUTPUT_PATH = Path(__file__).parent.parent / "deploy" / "qgis-worker" / "allowlist.txt"


def main() -> None:
    OUTPUT_PATH.write_text("\n".join(sorted(ALLOWLIST_IDS)) + "\n")
    print(f"wrote {len(ALLOWLIST_IDS)} ids to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd scripts && python generate_qgis_worker_allowlist.py`
Expected: `wrote 50 ids to .../deploy/qgis-worker/allowlist.txt`, a 50-line
text file, one algorithm id per line, sorted.

- [ ] **Step 3: Write the sidecar HTTP wrapper**

Create `deploy/qgis-worker/server.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Wrapper HTTP minimal autour de qgis_process (design SP-15d §3). Une
seule route, POST /run : shelle `qgis_process run <algorithmId> -` avec les
inputs en JSON sur stdin, retranscrit le contrat exit-code/stdout/stderr
vérifié empiriquement en design en réponse HTTP. Aucune logique métier
au-delà du contrôle d'appartenance à allowlist.txt (une garde de sécurité,
pas une transformation de données — design §3)."""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWLIST_PATH = Path("/app/allowlist.txt")
# Marge au-dessus du timeout HTTP worker->qgis-worker (design §8, 600s par
# défaut) : le sous-process est tué en premier, jamais la connexion HTTP.
QGIS_TIMEOUT_SECONDS = 900


def _load_allowlist() -> set[str]:
    return {line.strip() for line in ALLOWLIST_PATH.read_text().splitlines() if line.strip()}


_ALLOWLIST = _load_allowlist()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/run":
            self._respond(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        algorithm_id = body["algorithmId"]
        inputs = body["inputs"]

        if algorithm_id not in _ALLOWLIST:
            self._respond(403, {"error": f"algorithme non autorisé : {algorithm_id}"})
            return

        try:
            result = subprocess.run(
                ["qgis_process", "run", algorithm_id, "-"],
                input=json.dumps({"inputs": inputs}),
                capture_output=True, text=True, timeout=QGIS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            self._respond(504, {"error": f"timeout après {QGIS_TIMEOUT_SECONDS}s"})
            return

        if result.returncode != 0:
            error_line = next(
                (line for line in result.stderr.splitlines() if line.startswith("ERROR:")),
                "qgis_process a échoué sans message ERROR: identifiable",
            )
            self._respond(502, {"error": error_line})
            return

        self._respond(200, json.loads(result.stdout))

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass  # évite de polluer stdout du conteneur ; pas d'instrumentation OTel v0 (design §8)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
```

- [ ] **Step 4: Write the Dockerfile**

Create `deploy/qgis-worker/Dockerfile`:

```dockerfile
# qgis/qgis:release-3_34 = QGIS 3.34.5 "Prizren" (LTR) — PAS :latest, qui
# pointe vers un build 4.3.0-Master instable (vérifié en design, §2).
FROM qgis/qgis:release-3_34

# grassprovider fournit les ids grass:* (dont grass:r.watershed, le cas
# hydrologie de l'étude de faisabilité) mais est désactivé par défaut —
# vérifié en design (qgis_process plugins list). L'activer ici l'écrit dans
# le profil QGIS gravé dans cette image ; l'activer au runtime ne
# survivrait pas à un `docker run --rm` frais (design §2 point 6).
RUN qgis_process plugins enable grassprovider

COPY server.py /app/server.py
COPY allowlist.txt /app/allowlist.txt

ENV QT_QPA_PLATFORM=offscreen

CMD ["python3", "/app/server.py"]
```

- [ ] **Step 5: Build the image and smoke-test it manually**

Run:
```bash
docker build -t geostudio-qgis-worker deploy/qgis-worker
sudo mkdir -p /scratch && sudo chown "$(whoami)" /scratch
docker run -d --rm --name qgis-worker-test -p 8300:8000 -v /scratch:/scratch geostudio-qgis-worker
```
Expected: container starts and stays up (`docker ps` shows
`qgis-worker-test`). If `/scratch` already exists and is owned by someone
else, `chown` will fail loudly — that's the one-time local setup this
plan's `qgis`-marked tests require (mirrors the existing `postgis` marker's
own pre-provisioned-container convention, see `core/tests/conftest.py`'s
`pg_engine` fixture).

- [ ] **Step 6: Add the `qgis` marker and fixtures**

Modify `core/pyproject.toml` — extend the `markers` list:

```python
markers = [
    "postgis: nécessite un PostGIS réel (CORE_TEST_DATABASE_URL) ; skippé sinon",
    "qgis: nécessite un sidecar qgis-worker réel (CORE_TEST_QGIS_WORKER_URL) ; skippé sinon",
]
```

Modify `core/tests/conftest.py` — add after the existing `pg_engine`
fixture:

```python
@pytest.fixture(scope="session")
def qgis_worker_url():
    url = os.environ.get("CORE_TEST_QGIS_WORKER_URL")
    if not url:
        pytest.skip("CORE_TEST_QGIS_WORKER_URL non défini — test qgis skippé")
    return url


@pytest.fixture(scope="session")
def qgis_scratch_dir():
    path = os.environ.get("CORE_TEST_QGIS_SCRATCH_DIR")
    if not path:
        pytest.skip("CORE_TEST_QGIS_SCRATCH_DIR non défini — test qgis skippé")
    return Path(path)
```

Add `from pathlib import Path` to `conftest.py`'s imports if not already
present (it is — reused from the `pg_engine`/other fixtures' existing
imports; verify, add only if missing).

- [ ] **Step 7: Write the failing tests**

Create `core/tests/test_qgis_worker_sidecar.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Exercise le vrai sidecar qgis-worker (conteneur pré-démarré par le
développeur, cf. Task 4 Step 5 de docs/superpowers/plans/
2026-08-06-sp15d-qgis-sidecar.md). export CORE_TEST_QGIS_WORKER_URL=
http://localhost:8300 CORE_TEST_QGIS_SCRATCH_DIR=/scratch avant de lancer."""
import geopandas as gpd
import httpx
import pytest
from shapely.geometry import Polygon

pytestmark = pytest.mark.qgis


def _write_test_polygon(scratch_dir, name: str) -> None:
    gdf = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])], crs="EPSG:4326",
    )
    gdf.to_file(scratch_dir / name, driver="GPKG")


def test_run_allowlisted_algorithm_succeeds(qgis_worker_url, qgis_scratch_dir):
    _write_test_polygon(qgis_scratch_dir, "in_centroids.gpkg")
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={
            "algorithmId": "native:centroids",
            "inputs": {
                "INPUT": "/scratch/in_centroids.gpkg", "ALL_PARTS": False,
                "OUTPUT": "/scratch/out_centroids.gpkg",
            },
        },
        timeout=30,
    )
    assert response.status_code == 200
    assert response.json()["results"]["OUTPUT"] == "/scratch/out_centroids.gpkg"
    assert (qgis_scratch_dir / "out_centroids.gpkg").exists()


def test_run_rejects_non_allowlisted_algorithm(qgis_worker_url):
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={"algorithmId": "native:totallymadeup", "inputs": {}},
        timeout=30,
    )
    assert response.status_code == 403
    assert "non autorisé" in response.json()["error"]


def test_run_propagates_qgis_error_for_missing_input(qgis_worker_url):
    response = httpx.post(
        f"{qgis_worker_url}/run",
        json={
            "algorithmId": "native:centroids",
            "inputs": {
                "INPUT": "/scratch/does-not-exist.gpkg", "ALL_PARTS": False,
                "OUTPUT": "/scratch/out_missing.gpkg",
            },
        },
        timeout=30,
    )
    assert response.status_code == 502
    assert response.json()["error"].startswith("ERROR:")
```

- [ ] **Step 8: Run tests to verify they fail without the sidecar**

Run: `cd core && uv run pytest tests/test_qgis_worker_sidecar.py -v`
Expected (no env vars set): 3 skipped, `CORE_TEST_QGIS_WORKER_URL non
défini`.

- [ ] **Step 9: Run tests against the real sidecar**

Run:
```bash
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
export CORE_TEST_QGIS_SCRATCH_DIR=/scratch
cd core && uv run pytest tests/test_qgis_worker_sidecar.py -v
```
Expected: 3 passed, against the container started in Step 5.

- [ ] **Step 10: Commit**

```bash
git add deploy/qgis-worker/ scripts/generate_qgis_worker_allowlist.py \
  core/tests/conftest.py core/pyproject.toml core/tests/test_qgis_worker_sidecar.py
git commit -m "feat(deploy): qgis-worker sidecar — isolated qgis_process HTTP wrapper"
```

---

## Task 5: `runtime.py` — dispatch `transform.qgis`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `TransformQgisParams` (Task 2), `qgis_worker_url`/
  `qgis_scratch_dir` fixtures (Task 4), `httpx` (already a dependency).
- Produces: `run_pipeline(...)` and `preview_pipeline(...)` gain two new
  keyword params, `qgis_worker_url: str = ""` and
  `qgis_worker_timeout_seconds: int = 600` — consumed by Task 6
  (`routes.py`/`jobs.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py`:

```python
def test_execute_qgis_transform_raises_clean_error_without_worker_url(tmp_path, monkeypatch):
    """No QGIS_WORKER_URL configured (profile 'etl' not enabled) must fail
    the run cleanly, never crash on a connection error."""
    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: _table_info_for(cid))
    _write_partition(tmp_path, rows=[_row(1, "Nord", 1, x=2.35, y=48.85)])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}],
    })
    with pytest.raises(runtime.PipelineRuntimeError, match="QGIS_WORKER_URL"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k qgis_transform_raises -v`
Expected: FAIL — `transform.qgis` isn't dispatched at all yet,
`compiler.compile_transform_sql` raises `ValueError("'transform.qgis' is
not a transform op")`, which is unhandled (propagates as a raw
`ValueError`, not `PipelineRuntimeError` with the expected message).

- [ ] **Step 3: Implement the dispatch branch**

Modify `core/app/pipelines/runtime.py` — extend imports:

```python
import os
import uuid

import httpx
```

(add `os`, `uuid`, `httpx` to the existing `import csv / import io / import
json` block, alphabetically: `import csv`, `import io`, `import json`,
`import os`, `import uuid`, blank line, `import duckdb`, `import httpx`,
blank line, `from sqlalchemy.orm import Session`)

Add `TransformQgisParams` to the existing `from app.pipelines.ops.schemas
import (...)` block.

Add a new helper, right before `_execute_transform_chain`:

```python
def _execute_qgis_transform(
    conn, node: PipelineNode, *, input_view: str, input_srid: int,
    qgis_worker_url: str, qgis_worker_timeout_seconds: int, scratch_run_id: str,
) -> None:
    if not qgis_worker_url:
        raise PipelineRuntimeError(
            "transform.qgis requires QGIS_WORKER_URL to be configured (profile 'etl')"
        )
    p = TransformQgisParams.model_validate(node.params)
    scratch_dir = f"/scratch/{scratch_run_id}/{node.id}"
    in_path = f"{scratch_dir}/in.gpkg"
    out_path = f"{scratch_dir}/out.gpkg"
    os.makedirs(scratch_dir, exist_ok=True)
    # SRS explicite obligatoire : sans elle, DuckDB écrit "Undefined
    # geographic SRS" (vérifié en design §2) et qgis_process interprète les
    # géométries dans un CRS inconnu.
    conn.execute(
        f"COPY (SELECT * FROM {_qi(input_view)}) TO '{in_path}' "
        f"WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:{input_srid}')"
    )
    try:
        response = httpx.post(
            f"{qgis_worker_url}/run",
            json={
                "algorithmId": p.algorithmId,
                "inputs": {**p.params, "INPUT": in_path, "OUTPUT": out_path},
            },
            timeout=qgis_worker_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise PipelineRuntimeError(
            f"transform.qgis ({p.algorithmId}) : timeout après {qgis_worker_timeout_seconds}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise PipelineRuntimeError(
            f"transform.qgis ({p.algorithmId}) : échec de connexion au sidecar qgis-worker : {exc}"
        ) from exc
    if response.status_code != 200:
        detail = response.json().get("error", response.text)
        raise PipelineRuntimeError(f"transform.qgis ({p.algorithmId}) : {detail}")
    view_name = f"node_{node.id}"
    conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM ST_Read('{out_path}')")
    # Best-effort : ne bloque jamais le run si le nettoyage échoue (design
    # §12, risque accepté — un scratch non nettoyé après un CRASH, pas après
    # un succès, reste un problème d'exploitation mineur).
    import shutil
    shutil.rmtree(scratch_dir, ignore_errors=True)
```

Modify `_execute_transform_chain`'s signature and body:

```python
def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str],
    srid_by_node: dict[str, int], join_srid_by_node: dict[str, int],
    *, stop_at: str | None = None, qgis_worker_url: str = "",
    qgis_worker_timeout_seconds: int = 600,
) -> list["NodeStat"]:
    stats: list[NodeStat] = []
    scratch_run_id = uuid.uuid4().hex
    for node in ordered:
        if node.kind == "reader":
            stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_by_node[node.id])))
            if stop_at == node.id:
                return stats
            continue
        if node.kind != "transform":
            break  # writer nodes are handled by the caller, not here
        pred_id = compiler.predecessor_id(node.id, edges)
        assert pred_id is not None
        input_view = view_by_node[pred_id]
        input_srid = srid_by_node[pred_id]
        join_view = f"node_{node.id}__join" if node.op in _JOIN_PARAM_MODELS else None
        join_srid = join_srid_by_node.get(node.id)
        _validate_node_exprs(conn, node)
        try:
            output_srid = compiler.transform_output_srid(
                node.op, node.params, input_srid=input_srid, join_srid=join_srid,
            )
        except ValueError as exc:
            raise PipelineRuntimeError(str(exc)) from exc
        view_name = f"node_{node.id}"
        if node.op == "transform.qgis":
            _execute_qgis_transform(
                conn, node, input_view=input_view, input_srid=input_srid,
                qgis_worker_url=qgis_worker_url,
                qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
                scratch_run_id=scratch_run_id,
            )
        else:
            sql = compiler.compile_transform_sql(
                node.op, node.params, input_view=input_view, join_view=join_view, input_srid=input_srid,
            )
            conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = output_srid
        stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_name)))
        if stop_at == node.id:
            return stats
    return stats
```

Modify `preview_pipeline`'s signature and its call to
`_execute_transform_chain`:

```python
def preview_pipeline(
    *, session: Session | None, payload: PipelinePayload, tenant_id: str, user: User | None,
    up_to: str, endpoint_url: str, access_key: str, secret_key: str, base_uri: str, limit: int = 50,
    qgis_worker_url: str = "", qgis_worker_timeout_seconds: int = 600,
) -> list[dict]:
```

```python
        _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
            stop_at=up_to, qgis_worker_url=qgis_worker_url,
            qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
        )
```

Modify `run_pipeline`'s signature and its call to
`_execute_transform_chain`:

```python
def run_pipeline(
    session: Session, *, payload: PipelinePayload, tenant_id: str, user: User,
    endpoint_url: str, access_key: str, secret_key: str, base_uri: str,
    s3_client=None, exports_bucket: str | None = None,
    qgis_worker_url: str = "", qgis_worker_timeout_seconds: int = 600,
) -> list[NodeStat]:
```

```python
        stats = _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
            qgis_worker_url=qgis_worker_url, qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k qgis_transform_raises -v`
Expected: PASS — `PipelineRuntimeError` raised with "QGIS_WORKER_URL" in
the message, before any file/network I/O is attempted.

- [ ] **Step 5: Write the real end-to-end dispatch test (needs the sidecar)**

Append to `core/tests/test_pipeline_runtime.py`:

```python
@pytest.mark.qgis
def test_execute_qgis_transform_computes_centroids(tmp_path, monkeypatch, qgis_worker_url):
    """reader.collection (2 polygons) -> transform.qgis(native:centroids) ->
    preview: real sidecar round-trip, real DuckDB COPY/ST_Read (design §6).
    Requires /scratch to be the SAME directory the qgis-worker container in
    Task 4 Step 5 has bind-mounted at /scratch — this test writes via
    DuckDB's COPY (inside this Python process, on the host), the sidecar
    reads the identical path from inside its container."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    polygons_info = dataclasses.replace(
        TABLE_INFO, table_name="polygons", geometry_type="Polygon",
        columns=[ColumnInfo(name="region", type="string", required=True)],
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: polygons_info)

    _write_partition(tmp_path, collection_id="polygons", rows=[
        {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])},
        {"id": 2, "region": "b", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(10, 10), (10, 12), (12, 12), (12, 10)])},
    ])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}],
    })
    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
    )
    assert len(rows) == 2
    centroids = sorted(
        (row["geometry"]["coordinates"][0], row["geometry"]["coordinates"][1]) for row in rows
    )
    assert centroids == [(1.0, 1.0), (11.0, 11.0)]
```

Note: this test needs `/scratch` writable by the host process running
pytest (same one-time `sudo mkdir -p /scratch && sudo chown "$(whoami)"
/scratch` from Task 4 Step 5) — the container from Task 4 must be running
with `-v /scratch:/scratch` for the paths to match on both sides.

- [ ] **Step 6: Run test to verify it fails without setup, passes with it**

Run (no sidecar running): `cd core && uv run pytest tests/test_pipeline_runtime.py -k computes_centroids -v`
Expected: 1 skipped (`CORE_TEST_QGIS_WORKER_URL non défini`).

Run (with the Task 4 Step 5/9 setup — container running, env vars set):
```bash
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
cd core && uv run pytest tests/test_pipeline_runtime.py -k computes_centroids -v
```
Expected: 1 passed — centroids `(1.0, 1.0)` and `(11.0, 11.0)` match the
two synthetic squares' actual centers exactly (deterministic geometry, no
floating-point tolerance needed).

- [ ] **Step 7: Run the full test file to check for regressions**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: all pass (postgis/qgis-marked tests skipped if those env vars
aren't set, everything else passes unconditionally).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py
git commit -m "feat(core): runtime dispatch for transform.qgis via the qgis-worker sidecar"
```

---

## Task 6: `routes.py` + `jobs.py` — env var wiring + algorithm catalogue resource

**Files:**
- Modify: `core/app/pipelines/routes.py`
- Modify: `core/app/pipelines/jobs.py`
- Test: `core/tests/test_pipeline_routes.py`

**Interfaces:**
- Consumes: `QGIS_ALGORITHMS` (Task 1), `run_pipeline`/`preview_pipeline`'s
  new kwargs (Task 5).
- Produces: `GET /pipelines/ops/qgis-algorithms` (public REST resource,
  returns the full allowlist + schemas). `QGIS_WORKER_URL`/
  `QGIS_WORKER_TIMEOUT_SECONDS` env vars now read and threaded through both
  the run job and the preview route.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_routes.py`:

```python
def test_get_qgis_algorithms_returns_full_allowlist(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops/qgis-algorithms")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 50
    assert "native:centroids" in body
    assert "ALL_PARTS" in body["native:centroids"]["parameters"]


def test_get_qgis_algorithms_absent_when_etl_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/pipelines/ops/qgis-algorithms").status_code == 404
```

No new fixture: this file uses a local `_make_app(monkeypatch, *,
etl_enabled)` helper (not a shared pytest fixture) that builds a
`TestClient` with `CORE_ETL_ENABLED` set via `monkeypatch.setenv` — reused
here exactly as `test_get_pipelines_ops_returns_all_eight` already does.
The new route is registered on the same `router` as the rest of
`app.pipelines.routes`, so it inherits the existing `CORE_ETL_ENABLED`
gating (whatever mounts/unmounts the router based on that env var already
covers it) — the second test above locks that in explicitly rather than
assuming it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -k qgis_algorithms -v`
Expected: FAIL — 404, route doesn't exist yet.

- [ ] **Step 3: Add the route**

Modify `core/app/pipelines/routes.py` — add the import:

```python
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
```

Add right after the existing `GET /pipelines/ops` route:

```python
@router.get("/pipelines/ops/qgis-algorithms")
def get_qgis_algorithms() -> dict:
    return QGIS_ALGORITHMS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -k qgis_algorithms -v`
Expected: PASS.

- [ ] **Step 5: Thread the env vars through `preview_pipeline_route`**

Modify `core/app/pipelines/routes.py`'s `preview_pipeline_route`:

```python
        return preview_pipeline(
            session=session, payload=config.config.pipeline, tenant_id=user.tenant_id, user=user,
            up_to=upTo, endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""), secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
            qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
        )
```

- [ ] **Step 6: Thread the env vars through `run_pipeline_task`**

Modify `core/app/pipelines/jobs.py`'s `run_pipeline_task`:

```python
            stats = run_pipeline(
                session, payload=payload, tenant_id=tenant_id, user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
                qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
                qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
            )
```

- [ ] **Step 7: Run the full pipelines route/jobs test files**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py tests/test_pipeline_jobs.py -v`
Expected: all pass, no regression (existing tests don't set
`QGIS_WORKER_URL`, so `run_pipeline`/`preview_pipeline` receive `""` — the
same as their new default, no behavior change for pipelines without a
`transform.qgis` node).

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/routes.py core/app/pipelines/jobs.py core/tests/test_pipeline_routes.py
git commit -m "feat(core): wire QGIS_WORKER_URL env + publish the algorithm catalogue resource"
```

---

## Task 7: Docker Compose wiring

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `qgis-worker` service (profile `etl`), `etl-scratch` named
  volume shared with `worker`, `worker`'s new `QGIS_WORKER_URL`/
  `QGIS_WORKER_TIMEOUT_SECONDS` env vars + volume mount.

- [ ] **Step 1: Add the named volume**

Modify `docker-compose.yml`'s top-level `volumes:` section (currently
`pg-data:` and `minio-data:`, around line 5-8):

```yaml
volumes:
  pg-data:
  minio-data:
  etl-scratch:
```

- [ ] **Step 2: Add the `qgis-worker` service**

Add a new service block near `worker` (after the `worker:` block, around
line 176, before the `cdc-worker:` comment):

```yaml
  # Sidecar QGIS Processing étage 2 (SP-15d, arbitrage A39 — GPL en
  # sous-processus isolé, cœur Apache-2.0 intact). Profil `etl` : un
  # `docker compose up` par défaut ne le démarre pas, même porte que
  # CORE_ETL_ENABLED. Aucune credential DB, aucun accès réseau externe —
  # ne voit que le volume scratch partagé avec `worker` (garde
  # anti-confused-deputy, patron SP-6a).
  qgis-worker:
    build: ./deploy/qgis-worker
    profiles: ["etl"]
    environment:
      QT_QPA_PLATFORM: offscreen
    volumes:
      - etl-scratch:/scratch
    networks: [gis-net]
    restart: unless-stopped
```

- [ ] **Step 3: Wire `worker`'s env vars + volume**

Modify `docker-compose.yml`'s `worker:` service block — add to its
`environment:` section:

```yaml
      QGIS_WORKER_URL: http://qgis-worker:8000
      QGIS_WORKER_TIMEOUT_SECONDS: "600"
```

`worker:` (`docker-compose.yml:156-176`) has no `volumes:` key today —
add one, right after its `environment:` block and before `networks:
[gis-net]`:

```yaml
    volumes:
      - etl-scratch:/scratch
```

- [ ] **Step 4: Validate the compose file**

Run: `docker compose config --quiet`
Expected: no output, exit code 0 (valid YAML + valid compose schema).

Run: `docker compose --profile etl config --services`
Expected: includes `qgis-worker` in the service list (confirms the profile
gate works as intended — omit `--profile etl` and re-run to confirm
`qgis-worker` is absent from the default service list).

- [ ] **Step 5: Smoke-test the full compose service (manual, not automated)**

Run: `docker compose --profile etl build qgis-worker && docker compose --profile etl up -d qgis-worker`
Expected: service starts, `docker compose --profile etl logs qgis-worker`
shows no crash loop (the `ThreadingHTTPServer` from Task 4 blocks forever
on `serve_forever()`, so "no output, still running" after a few seconds is
the success signal).

Run: `docker compose --profile etl down`

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(deploy): wire qgis-worker into compose behind the etl profile"
```

---

## Task 8: End-to-end integration test — full pipeline run through the sidecar

**Files:**
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7. No new production code — this task
  is purely a test that proves the whole chain works together, mirroring
  SP-15c's own Task 8 (`test_use_case_3_incidents_near_schools_by_commune`).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_runtime.py`:

```python
@pytest.mark.postgis
@pytest.mark.qgis
def test_transform_qgis_end_to_end_dissolve_then_write(pg_engine, monkeypatch, tmp_path, qgis_worker_url):
    """reader.collection (2 adjacent polygons, same region) ->
    transform.qgis(native:dissolve) -> writer.collection: full run_pipeline,
    real Postgres write, real sidecar round-trip. Two squares sharing an
    edge dissolve (grouped by "region", both "a") into one polygon feature —
    proves the qgis dispatch composes with the pre-existing writer.collection
    path unchanged (design §6, 'no fusion to break, node-by-node as before')."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('dissolved_out', :t, :o, 'dissolved_out', 'Dissolved', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            # geometry(MultiPolygon, 4326), PAS geometry(Polygon, 4326) : verified
            # against a real qgis_process run during plan-writing that
            # native:dissolve always outputs MultiPolygon (even for a single
            # dissolved group of 1 feature) — ogrinfo on the real output showed
            # "Geometry: Multi Polygon". Using Polygon here would make
            # validate_feature reject every row ("expected Polygon").
            "CREATE TABLE dissolved_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, geometry geometry(MultiPolygon, 4326))"
        ))
        apply_collection_ddl(s, "dissolved_out")
        s.commit()

        polygons_info = dataclasses.replace(
            TABLE_INFO, table_name="polygons_in", geometry_type="Polygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )
        out_info = dataclasses.replace(
            # geometry_type="MultiPolygon" (not "Polygon") — see the CREATE
            # TABLE comment above: native:dissolve's real output type, verified.
            TABLE_INFO, table_name="dissolved_out", geometry_type="MultiPolygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )

        def _table_info(session, collection_id):
            return out_info if collection_id == "dissolved_out" else polygons_info

        monkeypatch.setattr(runtime, "_table_info_for_collection", _table_info)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="polygons_in", rows=[
            {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(0, 0), (0, 2), (1, 2), (1, 0)])},
            {"id": 2, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(1, 0), (1, 2), (2, 2), (2, 0)])},
        ])

        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons_in"}},
                {"id": "t1", "kind": "transform", "op": "transform.qgis",
                 "params": {"algorithmId": "native:dissolve",
                            "params": {"FIELD": "region", "SEPARATE_DISJOINT": False}}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "dissolved_out"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
        })
        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
        )
        s.commit()

        rows = s.execute(text("SELECT region FROM dissolved_out")).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "a"
        assert any(stat.op == "writer.collection" and stat.rowCount == 1 for stat in stats)

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE dissolved_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

- [ ] **Step 2: Run test to verify it's skipped without infra**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k transform_qgis_end_to_end -v`
Expected (no `CORE_TEST_DATABASE_URL`/`CORE_TEST_QGIS_WORKER_URL` set): 1
skipped.

- [ ] **Step 3: Run test against real infra**

Run:
```bash
export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
cd core && uv run pytest tests/test_pipeline_runtime.py -k transform_qgis_end_to_end -v
```
Expected: 1 passed — the two adjacent squares (sharing the edge `x=1`)
dissolve into a single polygon feature grouped by `region="a"`, written
into the real `dissolved_out` Postgres table via the unchanged
`writer.collection` path.

- [ ] **Step 4: Run the full core test suite**

Run:
```bash
export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
export CORE_TEST_QGIS_SCRATCH_DIR=/scratch
cd core && uv run pytest -q
```
Expected: all tests pass (previous count + this plan's new tests), 0
regressions. Then also run `uv run lint-imports` (expect `Contracts: 1
kept, 0 broken` — this plan adds no new cross-module imports that violate
the layered-architecture contract: `runtime.py`/`compiler.py`/
`routes.py`/`jobs.py` already import from `app.pipelines.ops.schemas`,
`qgis_algorithms.py` is a new file in that same already-permitted
package).

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_pipeline_runtime.py
git commit -m "test(core): end-to-end scenario for transform.qgis dissolve -> writer.collection"
```

---

## Final check (after all 8 tasks)

Run the full suite one more time with all env vars set (Task 8 Step 4's
commands), plus:

```bash
cd shell && npx vitest run && npx tsc --noEmit
```

Expected: unchanged shell test count and a clean typecheck — this plan
never touches `shell/`, so this is purely a regression guard, not expected
to surface anything new.
