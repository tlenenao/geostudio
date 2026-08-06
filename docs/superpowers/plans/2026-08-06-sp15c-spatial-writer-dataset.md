# SP-15c — Pipeline : opérations spatiales étage 1 + `writer.dataset` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the SP-15a/b Pipeline op catalogue with 5 spatial transform
ops (`transform.buffer`, `transform.reproject`, `transform.intersection`,
`transform.countWithin`, `transform.h3Aggregate`) and one new writer
(`writer.dataset`), completing amendment A39 — a dataset's declarative
transformation pipeline is now a real `Pipeline` ending in this writer.

**Architecture:** Six new Pydantic param models registered in the existing
op catalogue (`ops/schemas.py`); five new SQL-compiling branches plus a pure
CRS-guard helper in `compiler.py`; a `srid_by_node` side-channel threaded
through `runtime.py` in parallel to the existing `view_by_node`;
`writer.dataset` reuses `_write_collection` verbatim for the row write, then
upserts a `BuilderConfig(kind="dataset")` item via `app.configs.repository`/
`app.items.repository` (already-available lower layers per the import-linter
"layered architecture" contract). Shell needs a single one-line-per-op
addition to `PipelineCanvas.tsx`'s hardcoded insertion menu — everything else
in the shell is schema-driven and already generic (verified by reading
`PipelineNodeInspector.tsx`/`CollectionParamSelect.tsx`/`validation.ts`).

**Tech Stack:** Python/FastAPI (`core/`), Pydantic v2, DuckDB in-process
(`spatial` + `h3` community extension), React/TypeScript shell.

## Global Constraints

- No DB migration (`writer.dataset` reuses `BuilderConfig`/`Collection`, no
  new table).
- No behavior change to the 8 existing SP-15a ops, to `PipelineBuilderPage`,
  or to any shell component other than `PipelineCanvas.tsx`'s
  `INSERTABLE_TRANSFORMS` list.
- **Correction vs. the design doc, empirically verified against a real
  DuckDB in this repo's `core/.venv`:** every `ST_Transform` call MUST pass
  `always_xy := true` as its 4th argument. Without it, DuckDB's `spatial`
  extension applies the EPSG-authority axis order for `EPSG:4326` (lat,lng)
  and silently swaps x/y — confirmed by transforming `POINT(3 45)` to
  `EPSG:3857` both ways: without the flag you get
  `POINT (5009377.09 334111.17)` (wrong — that's lat treated as lon);
  with the flag you get `POINT (333958.47 5621521.49)` (correct). Every
  geometry in this codebase is GeoJSON x=lng,y=lat order (see
  `app/features/repository.py`'s `ST_MakeEnvelope(:bx0,:by0,:bx1,:by1,...)`),
  so `always_xy := true` is mandatory everywhere `ST_Transform` appears
  (`transform.buffer` unit=meters, `transform.reproject`). The design doc's
  SQL sketches omit this — do not copy them verbatim, use this plan's SQL.
- **Correction vs. the design doc's exact wording on the `h3` extension:**
  the design says only `LOAD h3;` goes in `duckdb_conn.py` (install is
  build-time only, in the Dockerfile). That's true for the *deployed image*,
  but `core`'s CI job (`.github/workflows/ci.yml`) runs `uv run pytest`
  directly on a bare `ubuntu-latest` runner — it never builds/runs
  `core/Dockerfile` first. A bare `LOAD h3` would fail there (extension
  never installed on that runner). Mirror the existing `httpfs`/`spatial`
  idiom instead: `open_connection()` calls `INSTALL h3 FROM community; LOAD
  h3;` together, exactly like it already does for `httpfs`/`spatial` — this
  is a no-op network call when already cached (verified empirically: the
  extension installs fine over network in this sandbox, same conditions as
  a GitHub Actions runner) and needs no network at all once the Dockerfile
  has pre-warmed the image, keeping `enable_external_access=false`'s
  rationale intact for the *deployed* runtime path.
- `can()`'s `Action` type (`app/sharing/authorization.py`) is
  `Literal["read", "write", "delete", "share"]` — there is no `"update"`
  action. Where the design doc says `can(actor, "update", dataset_item)`,
  implement it as `can(..., action="write", ...)`, matching every other
  update-permission check in this codebase (e.g.
  `app/configs/routes.py::_require_access(..., action="write")` for PUT).
- Every new item/config write performed by `writer.dataset` (creating or
  updating a `BuilderConfig(kind="dataset")` item) must go through
  `write_audit` (`app/audit/writer.py`), matching every other item/config
  creation path in this codebase (`app/configs/routes.py`,
  `app/mcp/tools.py::create_pipeline`) — CLAUDE.md's non-negotiable
  `tenant_id`/`audit_log` rule. `writer.collection`'s existing per-feature
  row writes are *not* individually audited today (neither is
  `insert_feature` itself) — that precedent is untouched; only the
  item/config-level write gets audited here.
- No MCP tool changes: `create_pipeline`'s `nodes: list[PipelineNode]` param
  is already untyped on `op` (`PipelineNode.op: str`), so the 6 new ops work
  through MCP with zero code changes (verified by reading
  `app/mcp/tools.py`).
- No shell API/type changes: `PipelineOpParamProperty`/`PipelineOpsCatalog`
  (`shell/src/api/types.ts`) are already a generic JSON-Schema subset;
  `PipelineNodeInspector.tsx` dispatches purely on `prop.format`/`prop.enum`/
  `prop.type`, never on a literal op name (verified by reading the file).

---

## Task 1: Op catalogue — 6 new param models

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Produces: `TransformBufferParams`, `TransformReprojectParams`,
  `TransformIntersectionParams`, `TransformCountWithinParams`,
  `TransformH3AggregateParams`, `WriterDatasetParams` (all Pydantic
  `BaseModel` subclasses in `app.pipelines.ops.schemas`), each registered in
  `OP_KINDS`/`OP_PARAMS` under its op name (`transform.buffer`,
  `transform.reproject`, `transform.intersection`, `transform.countWithin`,
  `transform.h3Aggregate`, `writer.dataset`). Consumed by Task 2
  (`compiler.py`), Task 4/5 (`runtime.py`), Task 6 (`config_validation.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_ops_schemas.py`:

```python
def test_all_fourteen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "writer.dataset",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


@pytest.mark.parametrize(
    "op,kind",
    [
        ("transform.buffer", "transform"),
        ("transform.reproject", "transform"),
        ("transform.intersection", "transform"),
        ("transform.countWithin", "transform"),
        ("transform.h3Aggregate", "transform"),
        ("writer.dataset", "writer"),
    ],
)
def test_new_op_kind_matches(op, kind):
    assert OP_KINDS[op] == kind


def test_transform_buffer_defaults_unit_to_meters():
    params = parse_op_params("transform.buffer", {"distance": 500})
    assert params.unit == "meters"
    assert params.distance == 500


def test_transform_buffer_rejects_missing_distance():
    with pytest.raises(ValidationError):
        parse_op_params("transform.buffer", {})


def test_transform_reproject_accepts_epsg_pattern():
    params = parse_op_params("transform.reproject", {"targetCrs": "EPSG:3857"})
    assert params.targetCrs == "EPSG:3857"


def test_transform_reproject_rejects_malformed_crs():
    with pytest.raises(ValidationError):
        parse_op_params("transform.reproject", {"targetCrs": "not-a-crs"})


def test_transform_intersection_defaults():
    params = parse_op_params(
        "transform.intersection", {"withCollectionId": "x"},
    )
    assert params.how == "inner"
    assert params.outputGeometry == "left"


def test_transform_count_within_defaults():
    params = parse_op_params(
        "transform.countWithin", {"withCollectionId": "x"},
    )
    assert params.countColumn == "count"
    assert params.predicate == "intersects"


def test_transform_h3_aggregate_requires_resolution_and_metrics():
    params = parse_op_params(
        "transform.h3Aggregate", {"resolution": 9, "metrics": {"n": "COUNT(*)"}},
    )
    assert params.resolution == 9
    assert params.metrics == {"n": "COUNT(*)"}
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"metrics": {}})


def test_transform_h3_aggregate_rejects_resolution_out_of_bounds():
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"resolution": 16, "metrics": {}})
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"resolution": -1, "metrics": {}})


def test_writer_dataset_requires_title_when_dataset_id_absent():
    params = parse_op_params(
        "writer.dataset", {"collectionId": "c1", "title": "My dataset"},
    )
    assert params.datasetId is None
    assert params.title == "My dataset"
    with pytest.raises(ValidationError):
        parse_op_params("writer.dataset", {"collectionId": "c1"})


def test_writer_dataset_allows_missing_title_when_dataset_id_present():
    params = parse_op_params(
        "writer.dataset", {"collectionId": "c1", "datasetId": "d1"},
    )
    assert params.datasetId == "d1"
    assert params.title is None


def test_new_collection_referencing_fields_carry_collection_id_format_hint():
    catalog = ops_catalog()
    assert catalog["transform.intersection"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"
    assert catalog["transform.countWithin"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"
    assert catalog["writer.dataset"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `AttributeError`/`KeyError` (new ops not registered yet),
`test_all_fourteen_ops_are_registered` fails (only 8 ops present).

- [ ] **Step 3: Implement the 6 param models**

In `core/app/pipelines/ops/schemas.py`, change the imports and module
docstring, then add the models and registration entries:

```python
# SPDX-License-Identifier: Apache-2.0
"""Catalogue des opérations du Pipeline : 8 op de données pures livrées en
Phase 1 (SP-15a — la fourchette 6-8 op de l'étude de faisabilité §5), + 5 op
de transformation spatiale étage 1 et 1 writer (`writer.dataset`) livrés en
Phase 3 étage 1 (SP-15c). Chaque op porte un manifeste de params typé
(Pydantic), publié en JSON Schema par GET /pipelines/ops pour que SP-15b
réutilise le mécanisme WcWidgetManifest/generatedPropsPanel (SP-8a) sans
redesign (design SP-15a §5).

filter.expr/derive.expr/aggregate.metrics[*]/h3Aggregate.metrics[*] sont des
chaînes SQL DuckDB bornées, PAS du CEL (correction du design SP-15a §5.1 —
aucun moteur CEL ne tourne côté serveur) : elles ne sont validées
syntaxiquement qu'à l'exécution (app.pipelines.expr_validation), jamais ici
— ce module ne valide que la FORME des params, pas la sémantique des
expressions."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator
```

Then, after `class WriterExportParams(BaseModel): ...` and before the
`OP_KINDS` dict, add:

```python
class TransformBufferParams(BaseModel):
    distance: float
    unit: Literal["meters", "native"] = "meters"


class TransformReprojectParams(BaseModel):
    targetCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")


class TransformIntersectionParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    how: Literal["inner", "left"] = "inner"
    outputGeometry: Literal["left", "intersection"] = "left"


class TransformCountWithinParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    countColumn: str = "count"
    predicate: Literal["intersects", "contains"] = "intersects"


class TransformH3AggregateParams(BaseModel):
    resolution: int = Field(..., ge=0, le=15)
    metrics: dict[str, str]


class WriterDatasetParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    datasetId: str | None = None    # pk d'un item BuilderConfig(kind="dataset") existant
    title: str | None = None        # requis si datasetId est None

    @model_validator(mode="after")
    def _require_title_for_new_dataset(self) -> "WriterDatasetParams":
        if self.datasetId is None and not (self.title and self.title.strip()):
            raise ValueError("title is required when datasetId is not provided")
        return self
```

Then update `OP_KINDS` and `OP_PARAMS`:

```python
OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "transform.buffer": "transform",
    "transform.reproject": "transform",
    "transform.intersection": "transform",
    "transform.countWithin": "transform",
    "transform.h3Aggregate": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "transform.buffer": TransformBufferParams,
    "transform.reproject": TransformReprojectParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.h3Aggregate": TransformH3AggregateParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
}
```

`parse_op_params`/`ops_catalog` need no changes — both already iterate the
dicts generically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Commit**

```bash
cd core
git add app/pipelines/ops/schemas.py tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): register 5 spatial transform ops + writer.dataset in pipeline op catalogue"
```

---

## Task 2: Compiler — SQL generation for the 5 spatial ops + CRS guard

**Files:**
- Modify: `core/app/pipelines/compiler.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: the 5 param models from Task 1
  (`TransformBufferParams`/`TransformReprojectParams`/
  `TransformIntersectionParams`/`TransformCountWithinParams`/
  `TransformH3AggregateParams`).
- Produces: `compile_transform_sql(op, params, *, input_view, join_view=None,
  input_srid=None) -> str` (signature gains the `input_srid` kwarg, used
  only by `transform.buffer`/`transform.reproject`; other ops ignore it) and
  a new pure function `transform_output_srid(op, params, *, input_srid,
  join_srid=None) -> int` that raises `ValueError` on a CRS mismatch.
  Consumed by Task 4 (`runtime.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_compiler.py`:

```python
@pytest.fixture()
def conn_spatial():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("INSTALL h3 FROM community; LOAD h3;")
    c.execute("CREATE TABLE base (id INTEGER, geometry GEOMETRY)")
    c.execute("INSERT INTO base VALUES (1, ST_Point(3.0, 45.0)), (2, ST_Point(3.001, 45.0))")
    return c


def test_compile_buffer_native_unit(conn_spatial):
    sql = compile_transform_sql(
        "transform.buffer", {"distance": 1, "unit": "native"}, input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute(
        "SELECT ST_GeometryType(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert row == ("POLYGON",)


def test_compile_buffer_meters_unit_uses_correct_axis_order(conn_spatial):
    # Régression : sans always_xy=true dans les deux ST_Transform internes,
    # DuckDB spatial applique l'ordre d'axe EPSG (lat,lng) et le buffer sort
    # décalé de plusieurs milliers de km — vérifié empiriquement (cf. plan
    # Global Constraints). Un point à ~333 m au nord doit être DANS un buffer
    # de 500 m ; un point à ~111 km doit être EN DEHORS.
    sql = compile_transform_sql(
        "transform.buffer", {"distance": 500, "unit": "meters"},
        input_view="base", input_srid=4326,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    near, far = conn_spatial.execute(
        "SELECT ST_Contains(geometry, ST_Point(3.0, 45.003)), "
        "ST_Contains(geometry, ST_Point(3.0, 46.0)) FROM out WHERE id = 1"
    ).fetchone()
    assert near is True
    assert far is False


def test_compile_reproject_uses_correct_axis_order(conn_spatial):
    sql = compile_transform_sql(
        "transform.reproject", {"targetCrs": "EPSG:3857"},
        input_view="base", input_srid=4326,
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert x == pytest.approx(333958.47, abs=1)
    assert y == pytest.approx(5621521.49, abs=1)


def test_compile_intersection_default_keeps_left_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.intersection", {"withCollectionId": "x"},
        input_view="base", join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT id FROM out ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]  # both points fall inside the 1-unit buffer


def test_compile_intersection_output_geometry_intersection(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.intersection",
        {"withCollectionId": "x", "outputGeometry": "intersection"},
        input_view="base", join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    types = conn_spatial.execute("SELECT ST_GeometryType(geometry) FROM out").fetchall()
    assert all(t == ("POINT",) for t in types)  # point ∩ polygon == point


def test_compile_count_within_intersects_default(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 1))")
    sql = compile_transform_sql(
        "transform.countWithin", {"withCollectionId": "x"},
        input_view="base", join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn_spatial.execute("SELECT id, count FROM out").fetchall())
    assert rows == {1: 1, 2: 1}


def test_compile_count_within_custom_column_and_contains_predicate(conn_spatial):
    conn_spatial.execute("CREATE TABLE other (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO other VALUES (10, ST_Buffer(ST_Point(3.0, 45.0), 0.0001))")
    sql = compile_transform_sql(
        "transform.countWithin",
        {"withCollectionId": "x", "countColumn": "n", "predicate": "contains"},
        input_view="base", join_view="other",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn_spatial.execute("SELECT id, n FROM out").fetchall())
    assert rows[1] == 1  # id=1 is exactly the buffer's center, contained
    assert rows[2] == 0  # id=2 is ~111m away, outside a ~11m buffer


def test_compile_h3_aggregate_groups_nearby_points(conn_spatial):
    sql = compile_transform_sql(
        "transform.h3Aggregate",
        {"resolution": 9, "metrics": {"n": "COUNT(*)"}},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT h3Cell, n FROM out").fetchall()
    assert len(rows) == 1  # both points fall in the same res-9 cell
    assert rows[0][1] == 2


def test_compile_h3_aggregate_with_no_metrics_has_no_trailing_comma(conn_spatial):
    sql = compile_transform_sql(
        "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT h3Cell FROM out").fetchall()
    assert len(rows) == 1


def test_transform_output_srid_passthrough_for_unaffected_ops():
    assert compiler.transform_output_srid("transform.filter", {}, input_srid=4326) == 4326
    assert compiler.transform_output_srid(
        "transform.buffer", {"distance": 1}, input_srid=2154,
    ) == 2154


def test_transform_output_srid_reproject_parses_target():
    srid = compiler.transform_output_srid(
        "transform.reproject", {"targetCrs": "EPSG:2154"}, input_srid=4326,
    )
    assert srid == 2154


def test_transform_output_srid_intersection_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.intersection", {"withCollectionId": "x"},
            input_srid=4326, join_srid=3857,
        )


def test_transform_output_srid_intersection_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.intersection", {"withCollectionId": "x"},
        input_srid=4326, join_srid=4326,
    )
    assert srid == 4326


def test_transform_output_srid_count_within_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.countWithin", {"withCollectionId": "x"},
            input_srid=4326, join_srid=2154,
        )


def test_transform_output_srid_h3_aggregate_requires_4326():
    with pytest.raises(ValueError, match="EPSG:4326"):
        compiler.transform_output_srid(
            "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_srid=3857,
        )
    assert compiler.transform_output_srid(
        "transform.h3Aggregate", {"resolution": 9, "metrics": {}}, input_srid=4326,
    ) == 4326
```

Add `import compiler`'s module itself to the test file's imports (needed for
`compiler.transform_output_srid`):

```python
from app.pipelines import compiler
```

(keep the existing `from app.pipelines.compiler import compile_transform_sql, predecessor_id, topological_order` line too — both import styles are used across the new/old tests).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: FAIL — `ValueError: '...' is not a transform op` for the new op
tests, `AttributeError: module 'app.pipelines.compiler' has no attribute
'transform_output_srid'` for the guard tests.

- [ ] **Step 3: Implement**

In `core/app/pipelines/compiler.py`, extend the imports:

```python
from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformBufferParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, TransformReprojectParams,
    TransformSelectParams,
)
```

Change `compile_transform_sql`'s signature and add the 5 new branches right
before the final `raise ValueError(f"'{op}' is not a transform op")`:

```python
def compile_transform_sql(
    op: str, params: dict, *, input_view: str, join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
```

```python
    if op == "transform.buffer":
        p = TransformBufferParams.model_validate(params)
        if p.unit == "native":
            return (
                f"SELECT * EXCLUDE (geometry), ST_Buffer(geometry, {p.distance}) AS geometry "
                f"FROM {_qi(input_view)}"
            )
        assert input_srid is not None, "transform.buffer(unit='meters') requires input_srid"
        # always_xy=true est obligatoire ici : cf. plan Global Constraints
        # (sans lui, ST_Transform applique l'ordre d'axe EPSG (lat,lng) pour
        # EPSG:4326 et intervertit x/y silencieusement — vérifié contre un
        # DuckDB réel).
        src = f"'EPSG:{input_srid}'"
        return (
            f"SELECT * EXCLUDE (geometry), "
            f"ST_Transform(ST_Buffer(ST_Transform(geometry, {src}, 'EPSG:3857', true), {p.distance}), "
            f"'EPSG:3857', {src}, true) AS geometry FROM {_qi(input_view)}"
        )

    if op == "transform.reproject":
        p = TransformReprojectParams.model_validate(params)
        assert input_srid is not None, "transform.reproject requires input_srid"
        return (
            f"SELECT * EXCLUDE (geometry), "
            f"ST_Transform(geometry, 'EPSG:{input_srid}', '{p.targetCrs}', true) AS geometry "
            f"FROM {_qi(input_view)}"
        )

    if op == "transform.intersection":
        p = TransformIntersectionParams.model_validate(params)
        assert join_view is not None, "transform.intersection requires join_view"
        join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
        geom_expr = "t.geometry" if p.outputGeometry == "left" else "ST_Intersection(t.geometry, o.geometry)"
        return (
            f"SELECT t.* EXCLUDE (geometry), {geom_expr} AS geometry "
            f"FROM {_qi(input_view)} t {join_kw} {_qi(join_view)} o ON ST_Intersects(t.geometry, o.geometry)"
        )

    if op == "transform.countWithin":
        p = TransformCountWithinParams.model_validate(params)
        assert join_view is not None, "transform.countWithin requires join_view"
        predicate_fn = "ST_Intersects" if p.predicate == "intersects" else "ST_Contains"
        return (
            f"SELECT t.* EXCLUDE (geometry), t.geometry, COUNT(o.geometry) AS {_qi(p.countColumn)} "
            f"FROM {_qi(input_view)} t LEFT JOIN {_qi(join_view)} o "
            f"ON {predicate_fn}(t.geometry, o.geometry) GROUP BY ALL"
        )

    if op == "transform.h3Aggregate":
        p = TransformH3AggregateParams.model_validate(params)
        h3_expr = (
            f"h3_latlng_to_cell(ST_Y(ST_Centroid(geometry)), ST_X(ST_Centroid(geometry)), {p.resolution})"
        )
        select_parts = [
            f"{h3_expr} AS h3Cell",
            f"ST_GeomFromText(h3_cell_to_boundary_wkt({h3_expr})) AS geometry",
        ]
        metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
        if metric_cols:
            select_parts.append(metric_cols)
        return f"SELECT {', '.join(select_parts)} FROM {_qi(input_view)} GROUP BY h3Cell"

    raise ValueError(f"'{op}' is not a transform op")
```

Then add the new pure guard function at the end of the file:

```python
def transform_output_srid(
    op: str, params: dict, *, input_srid: int, join_srid: int | None = None,
) -> int:
    """SRID de sortie d'un nœud transform, calculé sans connexion DuckDB
    (pur, comme compile_transform_sql). Lève ValueError si les deux entrées
    d'une op spatiale binaire ne partagent pas le même CRS — design §2/§3.3/
    §3.4/§3.5 : aucune réconciliation implicite, jamais un résultat spatial
    silencieusement faux. runtime.py convertit ce ValueError en
    PipelineRuntimeError avant de le laisser remonter."""
    if op == "transform.reproject":
        p = TransformReprojectParams.model_validate(params)
        return int(p.targetCrs.rsplit(":", 1)[1])
    if op in ("transform.intersection", "transform.countWithin"):
        assert join_srid is not None, f"{op} requires join_srid"
        if input_srid != join_srid:
            raise ValueError(
                f"'{op}': input CRS (EPSG:{input_srid}) and joined collection CRS "
                f"(EPSG:{join_srid}) differ — insert transform.reproject first"
            )
        return input_srid
    if op == "transform.h3Aggregate":
        if input_srid != 4326:
            raise ValueError(
                f"'transform.h3Aggregate' requires EPSG:4326 input (got EPSG:{input_srid}) "
                "— insert transform.reproject first"
            )
        return 4326
    return input_srid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: PASS (all tests, old and new). Note: this test run needs network
access the first time (to fetch the `h3` community extension into the local
DuckDB extension cache) — subsequent runs are offline.

- [ ] **Step 5: Commit**

```bash
cd core
git add app/pipelines/compiler.py tests/test_pipeline_compiler.py
git commit -m "feat(core): compile SQL for 5 spatial transform ops + pure CRS-guard helper"
```

---

## Task 3: DuckDB `h3` extension wiring

**Files:**
- Modify: `core/app/analytics/duckdb_conn.py`
- Modify: `core/Dockerfile`
- Test: `core/tests/test_analytics_duckdb_conn.py`

**Interfaces:**
- Produces: `open_connection()` now also installs+loads the `h3` community
  extension. Consumed by Task 4 (`runtime.py`'s `preview_pipeline`/
  `run_pipeline`, both call `open_connection()`).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_analytics_duckdb_conn.py`:

```python
def test_open_connection_installs_and_loads_h3(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    assert "INSTALL h3 FROM community" in joined and "LOAD h3" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py::test_open_connection_installs_and_loads_h3 -v`
Expected: FAIL — assertion error, `h3` never mentioned in recorded statements.

- [ ] **Step 3: Implement**

In `core/app/analytics/duckdb_conn.py`, add one line after the `spatial`
install:

```python
def open_connection(*, endpoint_url: str, access_key: str, secret_key: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute("INSTALL h3 FROM community; LOAD h3;")
    host = endpoint_url.split("://", 1)[-1]
```

Update the module docstring's extension list too (currently says "Extensions
httpfs ... et spatial ..."), appending: `et h3 (fonctions H3, SP-15c,
transform.h3Aggregate)`.

In `core/Dockerfile`, extend the pre-install `RUN` step (line 24) so the
built image never needs network for `h3` either:

```dockerfile
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v`
Expected: PASS (all 4 tests, old 3 + new 1).

- [ ] **Step 5: Commit**

```bash
cd core
git add app/analytics/duckdb_conn.py Dockerfile tests/test_analytics_duckdb_conn.py
git commit -m "feat(core): load DuckDB h3 community extension for transform.h3Aggregate"
```

---

## Task 4: Runtime — SRID tracking + spatial op execution

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `compiler.compile_transform_sql(..., input_srid=...)`,
  `compiler.transform_output_srid(...)` from Task 2; `open_connection()`
  loading `h3` from Task 3; `TransformIntersectionParams`/
  `TransformCountWithinParams`/`TransformH3AggregateParams` from Task 1.
- Produces: `_prepare()` now returns a 4-tuple `(ordered, view_by_node,
  srid_by_node, join_srid_by_node)`; `_execute_transform_chain()` gains two
  new required positional params `srid_by_node: dict[str, int]` and
  `join_srid_by_node: dict[str, int]`. Both `preview_pipeline` and
  `run_pipeline` are updated to match (their own external signatures are
  unchanged). Consumed by Task 5 (`_write_dataset`, added in the next task,
  reuses `_write_collection` which is untouched).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py`. These reuse the file's
existing `_write_partition`/`_row`/`_table_info_for` helpers and monkeypatch
pattern.

```python
def _table_info_srid(collection_id: str, srid: int) -> TableInfo:
    return dataclasses.replace(TABLE_INFO, table_name=collection_id, srid=srid)


def test_preview_buffer_then_reproject(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
            {"id": "t2", "kind": "transform", "op": "transform.reproject", "params": {"targetCrs": "EPSG:3857"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "geojson", "key": "o.geojson"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
            {"id": "e3", "from": "t2", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    assert len(rows) == 1
    assert rows[0]["geometry"]["type"] == "Polygon"


def test_preview_h3_aggregate_requires_4326_reproject_first(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 3857),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.h3Aggregate",
             "params": {"resolution": 9, "metrics": {"n": "COUNT(*)"}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(runtime.PipelineRuntimeError, match="EPSG:4326"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def test_preview_count_within_across_two_readers(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    _write_partition(tmp_path, collection_id="incidents", rows=[
        _row(1, "Nord", 1, x=3.0001, y=45.0), _row(2, "Sud", 1, x=10.0, y=10.0),
    ])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
            {"id": "t2", "kind": "transform", "op": "transform.countWithin",
             "params": {"withCollectionId": "incidents", "countColumn": "n"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
            {"id": "e3", "from": "t2", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path),
    )
    assert len(rows) == 1
    assert rows[0]["n"] == 1  # only the nearby incident falls in the 500m buffer


def test_preview_intersection_crs_mismatch_raises(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    _write_partition(tmp_path, collection_id="communes", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    srids = {"ecoles": 4326, "communes": 3857}
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, srids[collection_id]),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.intersection",
             "params": {"withCollectionId": "communes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(runtime.PipelineRuntimeError, match="transform.reproject"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def test_h3_aggregate_metrics_expression_is_bounded(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.h3Aggregate",
             # "(SELECT 1)" seul ne référence AUCUNE table (collect_table_refs
             # le laisserait passer) — l'expression doit référencer une vraie
             # table/vue pour exercer la garde ; "node_r1" est le nom de vue
             # que _prepare a matérialisé pour le reader r1 à ce stade.
             "params": {"resolution": 9, "metrics": {"n": "(SELECT count(*) FROM node_r1)"}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(Exception, match="must not reference a table"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k "buffer or h3_aggregate or count_within or intersection_crs" -v`
Expected: FAIL — `TypeError` (compile_transform_sql/`_prepare` don't accept
the new args yet) or `ValueError: '...' is not a transform op`.

- [ ] **Step 3: Implement**

In `core/app/pipelines/runtime.py`, extend the ops import:

```python
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, TransformAggregateParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, WriterCollectionParams, WriterExportParams,
)
```

Add a module-level constant right after the imports (used by both `_prepare`
and `_execute_transform_chain` to recognize the 3 ops that need a
second materialized collection):

```python
_JOIN_PARAM_MODELS: dict[str, type] = {
    "transform.join": TransformJoinParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
}
```

Extend `_validate_node_exprs` (h3Aggregate's `metrics` values are bounded SQL
expressions, exactly like `transform.aggregate.metrics` — same validation
must apply):

```python
def _validate_node_exprs(conn: duckdb.DuckDBPyConnection, node: PipelineNode) -> None:
    if node.op == "transform.filter":
        p = TransformFilterParams.model_validate(node.params)
        validate_bounded_expr(conn, p.expr)
    elif node.op == "transform.derive":
        p = TransformDeriveParams.model_validate(node.params)
        validate_bounded_expr(conn, p.expr)
    elif node.op == "transform.aggregate":
        p = TransformAggregateParams.model_validate(node.params)
        for metric_expr in p.metrics.values():
            validate_bounded_expr(conn, metric_expr)
    elif node.op == "transform.h3Aggregate":
        p = TransformH3AggregateParams.model_validate(node.params)
        for metric_expr in p.metrics.values():
            validate_bounded_expr(conn, metric_expr)
```

Replace `_prepare` (currently returns a 2-tuple) with the SRID-tracking
version:

```python
def _prepare(
    conn, session: Session, payload: PipelinePayload, *, tenant_id: str, user: User, base_uri: str,
) -> tuple[list[PipelineNode], dict[str, str], dict[str, int], dict[str, int]]:
    """Passe 1 : matérialise tous les readers (+ le withCollectionId de
    chaque transform.join/intersection/countWithin), puis verrouille.
    Retourne (ordre topologique, view_name par node.id, srid par node.id
    pour les readers, srid par node.id pour la vue __join des 3 op
    binaires) — writer nodes n'ont pas encore de vue."""
    ordered = compiler.topological_order(payload.nodes, payload.edges)
    view_by_node: dict[str, str] = {}
    srid_by_node: dict[str, int] = {}

    for node in ordered:
        if node.kind != "reader":
            continue
        p = ReaderCollectionParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        view_name = f"node_{node.id}"
        _materialize_reader(
            conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.collectionId, table_info=table_info,
        )
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = table_info.srid or 4326

    join_srid_by_node: dict[str, int] = {}
    for node in ordered:
        model = _JOIN_PARAM_MODELS.get(node.op)
        if model is None:
            continue
        p = model.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.withCollectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        join_view = f"node_{node.id}__join"
        _materialize_reader(
            conn, view_name=join_view, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.withCollectionId, table_info=table_info,
        )
        join_srid_by_node[node.id] = table_info.srid or 4326

    _lock_down(conn)
    return ordered, view_by_node, srid_by_node, join_srid_by_node
```

Replace `_execute_transform_chain` with the SRID-aware version:

```python
def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str],
    srid_by_node: dict[str, int], join_srid_by_node: dict[str, int],
    *, stop_at: str | None = None,
) -> list["NodeStat"]:
    stats: list[NodeStat] = []
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
        sql = compiler.compile_transform_sql(
            node.op, node.params, input_view=input_view, join_view=join_view, input_srid=input_srid,
        )
        view_name = f"node_{node.id}"
        conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = output_srid
        stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_name)))
        if stop_at == node.id:
            return stats
    return stats
```

Update `preview_pipeline`'s call sites:

```python
    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node, srid_by_node, join_srid_by_node = _prepare(
            conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri,
        )
        _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node, stop_at=up_to,
        )
```

(rest of `preview_pipeline` unchanged). And `run_pipeline`:

```python
    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node, srid_by_node, join_srid_by_node = _prepare(
            conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri,
        )
        stats = _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
        )
```

(rest of `run_pipeline` unchanged for this task — the `writer.dataset`
dispatch branch is added in Task 5).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: PASS (all tests, old and new — old tests must still pass since
`_prepare`/`_execute_transform_chain` are internal helpers only called from
`preview_pipeline`/`run_pipeline`, whose external signatures didn't change).

- [ ] **Step 5: Commit**

```bash
cd core
git add app/pipelines/runtime.py tests/test_pipeline_runtime.py
git commit -m "feat(core): thread SRID tracking through pipeline runtime, execute spatial ops"
```

---

## Task 5: `writer.dataset` execution

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `WriterDatasetParams` (Task 1), `_write_collection` (unchanged,
  existing), `app.configs.repository.{create_config,get_config_by_item,
  update_config}`, `app.items.repository.{create_item,get_access_facts}`,
  `app.configs.schemas.{BuilderConfig,DatasetPayload}`,
  `app.audit.writer.write_audit`.
- Produces: `_write_dataset(session, conn, *, node, view_by_node, tenant_id,
  user) -> NodeStat`, wired into `run_pipeline`'s writer dispatch under
  `node.op == "writer.dataset"`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py` (all `@pytest.mark.postgis`,
same pattern as `test_run_pipeline_writes_into_target_collection`):

```python
def _dataset_pipeline_payload(*, reader_collection: str, writer_collection: str, dataset_id=None, title=None):
    from app.configs.schemas import PipelinePayload
    params = {"collectionId": writer_collection}
    if dataset_id is not None:
        params["datasetId"] = dataset_id
    if title is not None:
        params["title"] = title
    return PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": reader_collection}},
            {"id": "w1", "kind": "writer", "op": "writer.dataset", "params": params},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })


@pytest.mark.postgis
def test_writer_dataset_creates_new_dataset_item(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.items.models import Item

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
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", title="Mon dataset",
        )
        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        assert any(stat.op == "writer.dataset" and stat.rowCount == 1 for stat in stats)
        item = s.execute(select(Item).where(Item.tenant_id == tenant.id, Item.resource_type == "dataset")).scalar_one()
        assert item.title == "Mon dataset"
        config = configs_repo.get_config_by_item(s, item.id)
        assert config is not None
        assert config.config.dataset.source == "collection"
        assert config.config.dataset.collectionId == "villes_out"

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.mark.postgis
def test_writer_dataset_updates_existing_dataset_preserving_metadata(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, DatasetPayload
    from app.items import repository as items_repo

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
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")

        existing_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Ancien dataset",
        )
        existing_config = configs_repo.create_config(
            s, BuilderConfig(kind="dataset", dataset=DatasetPayload(
                source="collection", collectionId="villes_out", timeField="createdAt",
            )),
            item_id=existing_item.id, tenant_id=tenant.id,
        )
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", dataset_id=existing_item.id,
        )
        runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        updated = configs_repo.get_config(s, existing_config.id)
        assert updated.config.dataset.collectionId == "villes_out"
        assert updated.config.dataset.timeField == "createdAt"  # preserved, not regenerated

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.mark.postgis
def test_writer_dataset_refuses_update_without_write_access(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, DatasetPayload
    from app.items import repository as items_repo

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")

        other_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=other.id, resource_type="dataset", title="Dataset de Bob",
        )
        configs_repo.create_config(
            s, BuilderConfig(kind="dataset", dataset=DatasetPayload(source="collection", collectionId="villes_out")),
            item_id=other_item.id, tenant_id=tenant.id,
        )
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", dataset_id=other_item.id,
        )
        with pytest.raises(runtime.PipelineRuntimeError, match="not writable"):
            runtime.run_pipeline(
                s, payload=payload, tenant_id=tenant.id, user=owner,  # owner, not Bob
                endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
                base_uri=str(tmp_path),
            )

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

Add `from sqlalchemy import select` if not already imported at module level
in the test file (it already imports `from sqlalchemy import text` — extend
to `from sqlalchemy import select, text`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test uv run pytest tests/test_pipeline_runtime.py -k writer_dataset -v`
Expected: FAIL — `AttributeError`/`ValueError: 'writer.dataset' is not a
transform op`-style errors (no dispatch branch yet), or `WriterDatasetParams`
not found. (Requires a local Postgres — see `docker compose up -d postgis`
or the `CORE_TEST_DATABASE_URL` env var; skipped otherwise per the
`postgis` marker.)

- [ ] **Step 3: Implement**

In `core/app/pipelines/runtime.py`, extend imports:

```python
from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, DatasetPayload, PipelineNode, PipelinePayload
from app.items import repository as items_repo
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, TransformAggregateParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, WriterCollectionParams,
    WriterDatasetParams, WriterExportParams,
)
```

Add `_write_dataset` right after `_write_collection`:

```python
def _write_dataset(
    session: Session, conn, *, node: PipelineNode, view_by_node: dict, tenant_id: str, user: User,
) -> NodeStat:
    p = WriterDatasetParams.model_validate(node.params)
    # Réutilise _write_collection TEL QUEL (même chemin d'écriture OGC
    # Features) : writer.dataset n'introduit aucune primitive d'écriture, il
    # catalogue seulement le résultat comme item "dataset" ensuite (design
    # §4 point 1). Le node synthétique porte le même id que node.id : c'est
    # ainsi que _write_collection retrouve la bonne entrée de view_by_node
    # (posée par l'appelant, run_pipeline, avant le dispatch).
    collection_node = PipelineNode(
        id=node.id, kind="writer", op="writer.collection", params={"collectionId": p.collectionId},
    )
    write_stat = _write_collection(
        session, conn, node=collection_node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
    )

    if p.datasetId is not None:
        facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=p.datasetId)
        if facts is None or not can(session, user_id=user.id, action="write", item=facts):
            raise PipelineRuntimeError(f"dataset '{p.datasetId}' is not writable")
        existing = configs_repo.get_config_by_item(session, p.datasetId)
        if existing is None or existing.config.kind != "dataset":
            raise PipelineRuntimeError(f"dataset '{p.datasetId}' not found")
        current = existing.config.dataset
        assert current is not None
        # Reconstruit un DatasetPayload frais (pas model_copy sur lui-même) :
        # source/collectionId changent, tout le reste (columns, timeField,
        # reactsToExtent, crossFilterLinks) est copié tel quel, jamais
        # régénéré par le run (design §4).
        updated_dataset = DatasetPayload(
            source="collection", collectionId=p.collectionId,
            columns=current.columns, timeField=current.timeField,
            reactsToExtent=current.reactsToExtent, crossFilterLinks=current.crossFilterLinks,
        )
        # model_copy (pas de re-validation) est sûr ici : seul le champ
        # "dataset" change, et il porte déjà un DatasetPayload fraîchement
        # validé par son propre constructeur ci-dessus ; le reste de
        # existing.config a déjà été validé lors de sa sauvegarde d'origine.
        updated_config = existing.config.model_copy(update={"dataset": updated_dataset})
        configs_repo.update_config(session, existing.id, updated_config, tenant_id=tenant_id)
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="config.update", object_type="config", object_id=existing.id,
            payload={"pipelineNodeId": node.id},
        )
    else:
        assert p.title is not None  # enforced by WriterDatasetParams' model_validator
        item = items_repo.create_item(
            session, tenant_id=tenant_id, owner_id=user.id, resource_type="dataset", title=p.title,
        )
        new_config = BuilderConfig(
            kind="dataset", dataset=DatasetPayload(source="collection", collectionId=p.collectionId),
        )
        config_result = configs_repo.create_config(session, new_config, item_id=item.id, tenant_id=tenant_id)
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="item.create", object_type="item", object_id=item.id,
            payload={"title": p.title},
        )
        write_audit(
            session, tenant_id=tenant_id, actor_id=user.id, actor_kind="user",
            action="config.create", object_type="config", object_id=config_result.id,
            payload={"title": p.title, "kind": "dataset"},
        )
    return NodeStat(node.id, node.op, write_stat.rowCount)
```

Wire it into `run_pipeline`'s writer dispatch loop:

```python
            if node.op == "writer.collection":
                stats.append(_write_collection(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                ))
            elif node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stats.append(_write_export(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node))
            elif node.op == "writer.dataset":
                stats.append(_write_dataset(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test uv run pytest tests/test_pipeline_runtime.py -v`
Expected: PASS (all tests). If no local Postgres is available, run: `cd core
&& uv run pytest tests/test_pipeline_runtime.py -v -m "not postgis"` and
confirm the 3 new `postgis` tests are reported as skipped, not failed or
errored.

- [ ] **Step 5: Commit**

```bash
cd core
git add app/pipelines/runtime.py tests/test_pipeline_runtime.py
git commit -m "feat(core): writer.dataset — write rows then create/update the dataset item"
```

---

## Task 6: Config-time validation — `writer.dataset` + intersection/countWithin

**Files:**
- Modify: `core/app/pipelines/config_validation.py`
- Test: `core/tests/test_pipeline_config_validation.py`, `core/tests/test_pipeline_node_validation.py`

**Interfaces:**
- Consumes: `OP_PARAMS` (already includes the 6 new ops from Task 1 — no
  change needed there, the registration loop at the bottom of
  `config_validation.py` already iterates `OP_PARAMS` generically).
- Produces: `_COLLECTION_PARAM_FIELD`/`_WRITE_OPS` gain entries for
  `transform.intersection`, `transform.countWithin` (both readable-collection
  checks, like `transform.join`) and `writer.dataset` (writable-collection
  check on its `collectionId`, like `writer.collection` — `datasetId` is
  deliberately NOT checked here, per design §4: it may reference a dataset
  created by a previous run, unknown at save time).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_node_validation.py` (reuses the file's
`env` fixture — `readable`/`writable`/`locked` collections already seeded):

```python
def _pipeline_body_op(op: str, params: dict) -> dict:
    return {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "t1", "kind": "transform", "op": op, "params": params},
                    {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "writable"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
            },
        },
    }


def test_transform_intersection_with_collection_missing_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body_op(
        "transform.intersection", {"withCollectionId": "does-not-exist"},
    ))
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_transform_count_within_with_collection_readable_saves(env):
    response = env.post("/configs", json=_pipeline_body_op(
        "transform.countWithin", {"withCollectionId": "readable"},
    ))
    assert response.status_code == 201


def test_writer_dataset_collection_not_editable_is_rejected(env):
    body = {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "w1", "kind": "writer", "op": "writer.dataset",
                     "params": {"collectionId": "locked", "title": "D"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    response = env.post("/configs", json=body)
    assert response.status_code == 422


def test_writer_dataset_collection_writable_saves(env):
    body = {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "w1", "kind": "writer", "op": "writer.dataset",
                     "params": {"collectionId": "writable", "title": "D"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    response = env.post("/configs", json=body)
    assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
Expected: FAIL — `transform.intersection`/`transform.countWithin`/
`writer.dataset` pass shape validation but skip the collection-permission
check entirely (no 422 raised for the missing/locked-collection cases; they
return 201 instead).

- [ ] **Step 3: Implement**

In `core/app/pipelines/config_validation.py`, extend both dicts:

```python
_COLLECTION_PARAM_FIELD = {
    "reader.collection": "collectionId",
    "transform.join": "withCollectionId",
    "transform.intersection": "withCollectionId",
    "transform.countWithin": "withCollectionId",
    "writer.collection": "collectionId",
    "writer.dataset": "collectionId",
}
_WRITE_OPS = {"writer.collection", "writer.dataset"}
```

No other change in this file — `_validate_node`/the `for _op in OP_PARAMS:
register_pipeline_node_validator(...)` loop at the bottom already cover the
new ops generically once they're in `OP_PARAMS` (Task 1) and
`_COLLECTION_PARAM_FIELD`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py tests/test_pipeline_config_validation.py -v`
Expected: PASS (all tests, old and new).

Also verify the import-linter contract still holds (no new violations —
`config_validation.py` wasn't touched in a way that adds imports, this is a
sanity check that Tasks 1-5 didn't introduce a layering violation elsewhere):

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 5: Commit**

```bash
cd core
git add app/pipelines/config_validation.py tests/test_pipeline_node_validation.py
git commit -m "feat(core): validate collection permissions for the 3 new collection-referencing ops"
```

---

## Task 7: Shell — spatial ops in the canvas insertion menu

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Produces: `INSERTABLE_TRANSFORMS` gains 5 entries. No other shell file
  changes (verified in Global Constraints — `PipelinePalette.tsx`,
  `PipelineNodeInspector.tsx`, `CollectionParamSelect.tsx`, `validation.ts`
  are all schema-driven already and need zero changes for the 6 new ops to
  be fully usable via drag-and-drop from the palette; only the edge "+"
  insertion shortcut menu is hardcoded).

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/pipeline/PipelineCanvas.test.tsx`:

```typescript
test("the edge insertion menu offers the 5 spatial transform ops", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  for (const label of ["Buffer", "Reprojeter", "Intersection", "Compter dans", "Agréger H3"]) {
    expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: FAIL — `getByRole("menuitem", { name: "Buffer" })` throws (not in
the DOM yet).

- [ ] **Step 3: Implement**

In `shell/src/builder/pipeline/PipelineCanvas.tsx`, extend the list:

```typescript
// Les 5 op transform.* insérables sur une arête (cf. plan Task 6 — clic sur
// le "+" d'une arête, pas de drag-drop précis sur le tracé SVG). SP-15c
// ajoute les 5 op spatiales étage 1 ; writer.dataset n'y figure jamais (ce
// n'est pas une op transform, jamais candidate à cette liste, cf. design §5).
const INSERTABLE_TRANSFORMS: { op: string; label: string }[] = [
  { op: "transform.filter", label: "Filtrer" },
  { op: "transform.select", label: "Sélectionner" },
  { op: "transform.derive", label: "Dériver" },
  { op: "transform.aggregate", label: "Agréger" },
  { op: "transform.join", label: "Joindre" },
  { op: "transform.buffer", label: "Buffer" },
  { op: "transform.reproject", label: "Reprojeter" },
  { op: "transform.intersection", label: "Intersection" },
  { op: "transform.countWithin", label: "Compter dans" },
  { op: "transform.h3Aggregate", label: "Agréger H3" },
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/pipeline/PipelineCanvas.tsx src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "feat(shell): add the 5 spatial transform ops to the edge insertion menu"
```

---

## Task 8: End-to-end scenario — study use case #3

**Files:**
- Modify: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6 (op catalogue, compiler, runtime SRID
  tracking, `writer.dataset`, config-time validation).
- Produces: no new production code — this is a pure integration test proving
  the whole chain composes, matching design §3.4's worked example: "incidents
  à moins de 500 m d'une école, par commune" = `transform.buffer` (500m on
  schools) → `transform.countWithin` (count incidents per buffer) →
  `transform.aggregate` (group by commune) → `writer.dataset`.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_runtime.py`:

```python
@pytest.mark.postgis
def test_use_case_3_incidents_near_schools_by_commune(pg_engine, monkeypatch, tmp_path):
    """buffer(500m on schools) -> countWithin(incidents) -> aggregate(by
    commune) -> writer.dataset — design §3.4's worked example, end to end."""
    from app.configs import repository as configs_repo

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        # Table de sortie tabulaire (pas de géométrie : l'aggregate final
        # group by commune ne conserve aucune colonne géométrie, cf. plan
        # Task 8 note — transform.aggregate ne sélectionne que groupBy+metrics).
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('communes_incidents', :t, :o, 'communes_incidents', 'Communes incidents', "
            "'', 'id', NULL, false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        # Colonne "region" (pas "commune") : c'est le nom réel de la colonne
        # groupBy en sortie de transform.aggregate ci-dessous (aucun
        # renommage n'a lieu dans compile_transform_sql pour transform.
        # aggregate — cf. plan Task 8 note). "commune" dans le vocabulaire du
        # cas d'usage #3 de l'étude == "region" dans les fixtures partagées
        # de ce fichier de test.
        s.execute(text(
            "CREATE TABLE communes_incidents (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, nearby_incidents BIGINT)"
        ))
        apply_collection_ddl(s, "communes_incidents")
        s.commit()

        # Deux écoles dans des communes différentes ; 2 incidents proches de
        # l'école "Nord" (dans le buffer 500m), 0 proche de "Sud".
        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="ecoles", rows=[
            _row(1, "Nord", 1, x=3.0, y=45.0), _row(2, "Sud", 1, x=10.0, y=10.0),
        ])
        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="incidents", rows=[
            _row(1, "x", 1, x=3.0005, y=45.0), _row(2, "x", 1, x=3.0006, y=45.0),
            _row(3, "x", 1, x=20.0, y=20.0),
        ])

        # communes_incidents (le writer.dataset target) a un schéma physique
        # DIFFÉRENT des readers ecoles/incidents (region+nearby_incidents,
        # pas de géométrie) : contrairement au reader-only TABLE_INFO
        # partagé par les autres tests de ce fichier, ce test a besoin d'un
        # TableInfo par collection_id, sans quoi validate_feature rejetterait
        # "nearby_incidents" comme unknown_property (il n'existe pas dans
        # TABLE_INFO.columns == [region, pop]).
        def _table_info(session, collection_id):
            if collection_id == "communes_incidents":
                return dataclasses.replace(
                    TABLE_INFO, table_name=collection_id, srid=4326,
                    geometry_column=None, geometry_type=None,
                    columns=[
                        ColumnInfo(name="region", type="string", required=True),
                        ColumnInfo(name="nearby_incidents", type="integer", required=True),
                    ],
                )
            return dataclasses.replace(TABLE_INFO, table_name=collection_id, srid=4326)

        monkeypatch.setattr(runtime, "_table_info_for_collection", _table_info)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
                {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
                {"id": "t2", "kind": "transform", "op": "transform.countWithin",
                 "params": {"withCollectionId": "incidents", "countColumn": "cnt"}},
                {"id": "t3", "kind": "transform", "op": "transform.aggregate",
                 "params": {"groupBy": ["region"], "metrics": {"nearby_incidents": "SUM(cnt)"}}},
                {"id": "w1", "kind": "writer", "op": "writer.dataset",
                 "params": {"collectionId": "communes_incidents", "title": "Incidents près des écoles"}},
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
                {"id": "e3", "from": "t2", "to": "t3"}, {"id": "e4", "from": "t3", "to": "w1"},
            ],
        })

        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        rows = dict(s.execute(text(
            "SELECT region, nearby_incidents FROM communes_incidents"
        )).fetchall())
        assert rows == {"Nord": 2, "Sud": 0}
        assert any(stat.op == "writer.dataset" and stat.rowCount == 2 for stat in stats)

        # writer.dataset a bien catalogué le résultat.
        item = s.execute(select(Item).where(
            Item.tenant_id == tenant.id, Item.resource_type == "dataset",
        )).scalar_one()
        config = configs_repo.get_config_by_item(s, item.id)
        assert config.config.dataset.collectionId == "communes_incidents"

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE communes_incidents; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

Note: `_row`'s second positional arg is used as the `region` column in the
existing fixture helper (`TABLE_INFO` declares a `region` column, not
`commune`) — the test above deliberately reuses `region` (not `commune`, to
avoid inventing a new fixture column) as the grouping field, and comments
the mapping to the design's "commune" vocabulary. `Item` must be imported at
the top of the test module already (it is, per the file's existing
`from app.items import repository as items_repo` import at the top — add
`from app.items.models import Item` alongside it if not already present as a
bare import; check the top of the file before adding, since Task 5 may have
already added it for its own tests).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test uv run pytest tests/test_pipeline_runtime.py::test_use_case_3_incidents_near_schools_by_commune -v`
Expected: FAIL if Tasks 1-6 aren't complete yet (this task assumes they are
— it's a pure composition test, no new implementation code). If Tasks 1-6
are already done (this is the last task in the plan), this step instead
serves as a first real run: expect it to reveal any integration gap (e.g. a
mismatched column name) that unit-level tests in Tasks 1-6 didn't catch —
fix forward in this task's step 3 if so, don't touch Tasks 1-6's committed
code.

- [ ] **Step 3: Fix forward if needed, otherwise no implementation step**

This task has no production code of its own. If Step 2 fails due to a gap
in Tasks 1-6 (e.g. `region` vs `commune` naming, an off-by-one in the
buffer distance), fix the test itself (this file) to match the real,
already-implemented behavior — do not change `compiler.py`/`runtime.py`
behavior at this stage unless Step 2 reveals an actual bug (in which case,
fix it here and re-verify Tasks 1-6's own test suites still pass:
`cd core && uv run pytest tests/test_pipeline_compiler.py tests/test_pipeline_runtime.py -v`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis_test uv run pytest tests/test_pipeline_runtime.py -v`
Expected: PASS (the full file, all tests).

- [ ] **Step 5: Commit**

```bash
cd core
git add tests/test_pipeline_runtime.py
git commit -m "test(core): end-to-end scenario for buffer -> countWithin -> aggregate -> writer.dataset"
```

---

## Final check

Run the full suites to confirm no regression across both halves of the
monorepo:

```bash
cd core && uv run pytest && uv run lint-imports
cd shell && npm run test && npm run build
```

Expected: `core` — all tests pass (previously: 606 executed + 87 skipped;
this plan adds roughly 45 new tests, ~40 of which run unconditionally and
~5 of which are `postgis`-marked and skip without a local Postgres) plus
`Contracts: 1 kept, 0 broken.`; `shell` — all Vitest suites pass (previously
398 tests; this plan adds 1) and `npm run build` (`tsc --noEmit && vite
build`) succeeds with no type errors.

E2E (`npm run e2e`, 18 Playwright specs) is unaffected by this plan — no
shell UI beyond the already-covered edge-insertion menu changed, and
`pipeline-builder.spec.ts` (SP-15b) doesn't assert on the exact contents of
`INSERTABLE_TRANSFORMS`. Re-running it is optional but recommended if time
allows: `cd shell && npm run e2e`.
