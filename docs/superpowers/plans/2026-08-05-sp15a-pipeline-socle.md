# SP-15a — Pipeline : socle headless + capacité optionnelle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the headless socle of the ETL engine: a declarative `Pipeline`
document (`kind="pipeline"`), an 8-op data-only catalogue, a DuckDB-based
execution runtime running node-by-node (no fusion), a procrastinate job, and
a `CORE_ETL_ENABLED` instance-wide capability flag that gates the whole
surface off by default — author via MCP/REST only, no canvas.

**Architecture:** A new `core/app/pipelines/` module (sits above
`app.harvest`... below `app.ingestion` — wait, see Global Constraints for the
exact layer position) holds the op catalogue, DAG compiler, DuckDB runtime,
procrastinate job and REST routes. `core/app/configs/` gains `kind="pipeline"`
following the exact `dataset`/`bookmark` precedent (a `BuilderConfig` payload
+ a validation-registry indirection, since `app.configs` sits *below*
`app.pipelines` in the layer contract and cannot import it directly).
Everything reuses existing runtime primitives verbatim: the ephemeral
DuckDB connection and GeoParquet CDC dedup CTE from SP-11b
(`app.analytics`), the OGC Features write path from SP-3
(`insert_feature`/`rls_scope`/`validate_feature`), and the procrastinate
queue/job pattern from SP-6a/SP-12c.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, DuckDB (already a core
dependency since SP-11b — `duckdb>=1.0`), procrastinate, Alembic. No new
Python dependency.

## Global Constraints

- **Reference spec:** `docs/superpowers/specs/2026-08-05-sp15a-pipeline-socle-design.md`
  (read it first — this plan implements it verbatim, including the two
  corrections applied to it during this planning session: §5.1 `filter.expr`/
  `derive.expr` are **bounded DuckDB SQL expressions, not CEL** — no server-side
  CEL engine exists in `core/` today, `cel-js` is shell-only — and
  `writer.collection` takes a **required, existing** `collectionId` (no
  `createIfMissing` in Phase 1 — DDL-creation-on-write is deferred, out of
  scope here to keep this plan bounded).
- **Linear+join topology only** (feasibility study §4.1, mitigation D1): every
  node has **at most one incoming edge**; `transform.join`'s second input is a
  node **param** (`withCollectionId`), never a second graph edge. A node with
  more than one incoming edge is rejected — both at save time (Task 4) and at
  execution time (Task 8, defense in depth). Full branching/merge DAGs are
  explicitly deferred to a later sub-plan.
- **No fusion/push-down**: every node materializes its own DuckDB `TEMP VIEW`;
  the next node reads its predecessor's view. This is intentionally naive —
  optimizing it is out of scope (design §1 non-but).
- **Op-param semantic validation vs. save-time validation boundary**: at
  save time (Tasks 4-5), only the **shape** of a node's params is validated
  (Pydantic model + referenced collection exists/readable/writable). Bounded
  SQL expressions (`filter.expr`, `derive.expr`, `aggregate.metrics` values)
  and `transform.join.on` column existence are **not** syntax/semantically
  checked until execution (Task 8) — a bad expression fails the run clearly
  (`PipelineRun.status = "failed"`, `error` populated), never silently, never
  a zombie run. This mirrors how `transform.join`'s `on` column is only
  resolved by DuckDB's binder at run time.
- **Import-linter layer position**: `app.pipelines` is inserted in
  `core/pyproject.toml`'s `[tool.importlinter]` `layers` list **between
  `app.harvest` and `app.ingestion`** (it needs to import `app.features`,
  `app.collections`, `app.configs`, and `app.ingestion.storage` for the S3
  export client — all lower layers once `app.pipelines` sits there).
  `app.analytics` is **not** in the layers list at all (same status as
  `app.db`/`app.jobs` — unconstrained, freely importable from anywhere),
  confirmed by reading the current contract.
- **`CORE_ETL_ENABLED` is read once per relevant surface, not per DB row**:
  router mounting (Task 10) and MCP tool registration (Task 11) read it at
  `create_app()`/`register_tools()` time (process start) — consistent with
  every other env-driven structural choice in this codebase
  (`CORE_AUTH_MODE`, `CORE_BASE_URL`). Only the per-request `POST /configs`
  `kind="pipeline"` guard (Task 4) re-reads it per request, mirroring
  `is_read_only_mode()`'s own per-request convention (tests monkeypatch
  without recreating the app for that one case).
- **Every new/modified file gets `# SPDX-License-Identifier: Apache-2.0`** as
  its first line (every existing file in `core/` does).
- **French code comments where they explain non-obvious rationale**, matching
  the existing codebase's own style (English identifiers, French comments)
  — do not translate; write new comments in French too when they carry a
  "why", English when purely mechanical (matches what's already in the repo).
- **`pytest.mark.postgis`** is required on any test that needs a real
  Postgres/PostGIS (`CORE_TEST_DATABASE_URL`) — used only in Tasks 8 and 9
  (feature writes and procrastinate worker execution). Tasks 1-7 and 10-11
  run entirely against SQLite/local-disk fixtures, no marker needed.
- **Never commit with `--no-verify`**; run the exact test commands shown in
  each step before moving to the next step.

---

## Task 1: `CORE_ETL_ENABLED` capability flag

**Files:**
- Modify: `core/app/auth/dependency.py`
- Modify: `core/app/instance/routes.py`
- Modify: `.env.example`
- Modify: `core/tests/test_read_only_mode.py` (two exact-dict assertions break once `/instance` gains a key)
- Test: `core/tests/test_etl_enabled_flag.py`

**Interfaces:**
- Produces: `is_etl_enabled() -> bool` in `app.auth.dependency`, imported by
  every later task that needs to gate a surface (Tasks 4, 9 doc-only, 10, 11).
  `GET /instance` response gains `"etlEnabled": bool`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_etl_enabled_flag.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_etl_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_etl_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_ETL_ENABLED", raising=False)
    assert is_etl_enabled() is False


def test_is_etl_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    assert is_etl_enabled() is True
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    assert is_etl_enabled() is False


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_reports_etl_disabled_by_default(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": False}


def test_instance_reports_etl_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": True}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_etl_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_etl_enabled'`

- [ ] **Step 3: Implement `is_etl_enabled()`**

In `core/app/auth/dependency.py`, add right after `is_read_only_mode` (after line 23):

```python
def is_etl_enabled() -> bool:
    """CORE_ETL_ENABLED (SP-15a) — capacité instance-wide optionnelle, même
    convention que is_read_only_mode : lue à chaque appel, sans cache, pour
    que les tests basculent via monkeypatch sans recréer l'app. Défaut
    false : une instance qui monte en version ne voit rien de nouveau tant
    qu'elle n'a pas explicitement activé la capacité (cf. design SP-15a §3)."""
    return os.environ.get("CORE_ETL_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Wire it into `GET /instance`**

Replace the full contents of `core/app/instance/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_etl_enabled, is_read_only_mode

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {"readOnly": is_read_only_mode(), "etlEnabled": is_etl_enabled()}
```

- [ ] **Step 5: Fix the two existing exact-dict assertions**

In `core/tests/test_read_only_mode.py`, update:

```python
def test_instance_defaults_to_read_write(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False, "etlEnabled": False}


def test_instance_reports_read_only_without_needing_auth(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": True, "etlEnabled": False}
```

- [ ] **Step 6: Add `.env.example` entry**

In `.env.example`, right after the `CORE_READ_ONLY_MODE=false` line, add:

```
CORE_ETL_ENABLED=false
```

- [ ] **Step 7: Run all affected tests**

Run: `cd core && uv run pytest tests/test_etl_enabled_flag.py tests/test_read_only_mode.py -v`
Expected: PASS (all tests green)

- [ ] **Step 8: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py .env.example \
  core/tests/test_read_only_mode.py core/tests/test_etl_enabled_flag.py
git commit -m "feat(core): add CORE_ETL_ENABLED instance-wide capability flag"
```

---

## Task 2: `BuilderConfig` gains `kind="pipeline"`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_pipeline_config_schema.py`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: `PipelineNode`, `PipelineEdge`, `PipelinePayload` in
  `app.configs.schemas`, `BuilderConfig.kind` literal gains `"pipeline"`,
  `BuilderConfig.pipeline: PipelinePayload | None`. Consumed by every later
  task (`config.pipeline`, `node.id`/`node.kind`/`node.op`/`node.params`,
  `edge.from_`/`edge.to`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_config_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _pipeline_body() -> dict:
    return {
        "version": 1,
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection",
                 "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection",
                 "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }


def test_pipeline_config_valide():
    config = BuilderConfig.model_validate(_pipeline_body())
    assert config.kind == "pipeline"
    assert config.pipeline.nodes[0].op == "reader.collection"
    assert config.pipeline.edges[0].from_ == "r1"


def test_pipeline_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "pipeline"})


def test_pipeline_config_ids_dupliques_rejetes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][1]["id"] = "r1"
    with pytest.raises(ValidationError, match="unique"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_edge_vers_noeud_inconnu_rejetee():
    body = _pipeline_body()
    body["pipeline"]["edges"][0]["to"] = "does-not-exist"
    with pytest.raises(ValidationError, match="unknown node"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_reader_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][1]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="reader"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_writer_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][0]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="writer"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_x_y_when_acceptes_mais_inertes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][0]["x"] = 100
    body["pipeline"]["nodes"][0]["y"] = 40
    body["pipeline"]["edges"][0]["when"] = "true"
    config = BuilderConfig.model_validate(body)
    assert config.pipeline.nodes[0].x == 100
    assert config.pipeline.edges[0].when == "true"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: FAIL — `pydantic_core._pydantic_core.ValidationError: ... Input should be 'app', 'dashboard', 'map', 'site', 'dataset' or 'bookmark'` (kind literal doesn't yet accept "pipeline")

- [ ] **Step 3: Add the schemas**

In `core/app/configs/schemas.py`, change the import line at the top:

```python
from typing import Annotated, Any, Literal
```

Then add, right after `BookmarkPayload` (after line 165, before `class BuilderConfig`):

```python
class PipelineNode(BaseModel):
    id: str
    kind: Literal["reader", "transform", "writer"]
    op: str
    x: int = 0
    y: int = 0                    # idiome LayoutItem, inutilisé tant qu'il n'y a pas de
                                   # canvas (SP-15b) — posé maintenant pour ne pas migrer
                                   # le schéma plus tard (design SP-15a §4.1)
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None       # CEL, routage conditionnel — accepté mais non
                                   # interprété par le compilateur avant Phase 3/4


class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> "PipelinePayload":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("pipeline node ids must be unique")
        id_set = set(ids)
        for edge in self.edges:
            if edge.from_ not in id_set:
                raise ValueError(f"edge references unknown node '{edge.from_}'")
            if edge.to not in id_set:
                raise ValueError(f"edge references unknown node '{edge.to}'")
        if not any(n.kind == "reader" for n in self.nodes):
            raise ValueError("pipeline requires at least one reader node")
        if not any(n.kind == "writer" for n in self.nodes):
            raise ValueError("pipeline requires at least one writer node")
        return self
```

Then in `BuilderConfig`, change the `kind` literal:

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline"]
```

Add the payload field right after `bookmark: BookmarkPayload | None = None`:

```python
    pipeline: PipelinePayload | None = None
```

And add a branch to `_require_kind_payload`, right after the bookmark check:

```python
        if self.kind == "pipeline" and self.pipeline is None:
            raise ValueError("pipeline config requires a pipeline payload")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: PASS (7 tests green)

- [ ] **Step 5: Run the full configs test suite to check no regression**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py tests/test_configs_models.py -v`
Expected: PASS (unchanged)

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_pipeline_config_schema.py
git commit -m "feat(core): add BuilderConfig kind=pipeline (PipelinePayload/Node/Edge)"
```

---

## Task 3: Op catalogue (8 data-only ops)

**Files:**
- Create: `core/app/pipelines/__init__.py`
- Create: `core/app/pipelines/ops/__init__.py`
- Create: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `OP_KINDS: dict[str, str]`, `OP_PARAMS: dict[str, type[BaseModel]]`,
  `parse_op_params(op: str, params: dict) -> BaseModel`,
  `ops_catalog() -> dict[str, dict]` in `app.pipelines.ops.schemas`. The
  8 param classes (`ReaderCollectionParams`, `TransformFilterParams`,
  `TransformSelectParams`, `TransformDeriveParams`, `TransformAggregateParams`,
  `TransformJoinParams`, `WriterCollectionParams`, `WriterExportParams`) are
  imported directly by Tasks 5, 6 and 8.

- [ ] **Step 1: Create the package skeleton**

Create `core/app/pipelines/__init__.py` (empty file, just the license header):

```python
# SPDX-License-Identifier: Apache-2.0
```

Create `core/app/pipelines/ops/__init__.py` (same, empty):

```python
# SPDX-License-Identifier: Apache-2.0
```

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_pipeline_ops_schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import OP_KINDS, OP_PARAMS, ops_catalog, parse_op_params


def test_all_eight_phase1_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


@pytest.mark.parametrize(
    "op,kind",
    [
        ("reader.collection", "reader"),
        ("transform.filter", "transform"),
        ("transform.select", "transform"),
        ("transform.derive", "transform"),
        ("transform.aggregate", "transform"),
        ("transform.join", "transform"),
        ("writer.collection", "writer"),
        ("writer.export", "writer"),
    ],
)
def test_op_kind_matches(op, kind):
    assert OP_KINDS[op] == kind


def test_parse_op_params_reader_collection():
    params = parse_op_params("reader.collection", {"collectionId": "villes"})
    assert params.collectionId == "villes"


def test_parse_op_params_missing_required_field_raises():
    with pytest.raises(ValidationError):
        parse_op_params("reader.collection", {})


def test_parse_op_params_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown op"):
        parse_op_params("transform.does-not-exist", {})


def test_transform_join_defaults_how_to_inner():
    params = parse_op_params("transform.join", {"withCollectionId": "x", "on": "code"})
    assert params.how == "inner"


def test_writer_export_requires_format_and_key():
    params = parse_op_params("writer.export", {"format": "csv", "key": "out.csv"})
    assert params.format == "csv"
    assert params.key == "out.csv"
    with pytest.raises(ValidationError):
        parse_op_params("writer.export", {"key": "out.csv"})


def test_ops_catalog_exposes_json_schema_per_op():
    catalog = ops_catalog()
    assert set(catalog) == set(OP_PARAMS)
    for op, entry in catalog.items():
        assert entry["kind"] == OP_KINDS[op]
        assert "properties" in entry["paramsSchema"]
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.ops.schemas'`

- [ ] **Step 4: Implement the op catalogue**

Create `core/app/pipelines/ops/schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Catalogue des 8 opérations de données pures livrées en Phase 1 (SP-15a) —
la fourchette 6-8 op de l'étude de faisabilité §5. Chaque op porte un
manifeste de params typé (Pydantic), publié en JSON Schema par
GET /pipelines/ops pour que SP-15b réutilise le mécanisme
WcWidgetManifest/generatedPropsPanel (SP-8a) sans redesign (design §5).

filter.expr/derive.expr/aggregate.metrics[*] sont des chaînes SQL DuckDB
bornées, PAS du CEL (correction du design §5.1 — aucun moteur CEL ne
tourne côté serveur) : elles ne sont validées syntaxiquement qu'à
l'exécution (app.pipelines.expr_validation), jamais ici — ce module ne
valide que la FORME des params, pas la sémantique des expressions."""
from typing import Literal

from pydantic import BaseModel, Field


class ReaderCollectionParams(BaseModel):
    collectionId: str


class TransformFilterParams(BaseModel):
    expr: str


class TransformSelectParams(BaseModel):
    columns: dict[str, str | None] = Field(default_factory=dict)


class TransformDeriveParams(BaseModel):
    column: str
    expr: str


class TransformAggregateParams(BaseModel):
    groupBy: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)


class TransformJoinParams(BaseModel):
    withCollectionId: str
    on: str
    how: Literal["inner", "left"] = "inner"


class WriterCollectionParams(BaseModel):
    collectionId: str


class WriterExportParams(BaseModel):
    format: Literal["geojson", "csv"]
    key: str


OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def ops_catalog() -> dict[str, dict]:
    return {
        op: {"kind": OP_KINDS[op], "paramsSchema": model.model_json_schema()}
        for op, model in OP_PARAMS.items()
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: PASS (11 tests green)

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/__init__.py core/app/pipelines/ops/__init__.py \
  core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): add Phase 1 pipeline op catalogue (8 data-only ops)"
```

---

## Task 4: Structural graph validation (`app.configs` layer) + `/configs` wiring + ETL-disabled guard

**Files:**
- Create: `core/app/configs/pipeline_validation.py`
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_pipeline_config_validation.py`

**Interfaces:**
- Consumes: `BuilderConfig`/`PipelineNode` (Task 2).
- Produces: `register_pipeline_node_validator(op, validator)`,
  `validate_pipeline_payload(session, config, *, user)` in
  `app.configs.pipeline_validation` — consumed by Task 5 (registers real
  validators) and already wired into `configs/routes.py` here. `POST/PUT
  /configs` (and `/configs/by-item/{id}`) now 403 when `kind="pipeline"` and
  `CORE_ETL_ENABLED` is false, and 422 on structural graph errors
  (cycle, >1 incoming edge) when enabled.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_config_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import pipeline_validation as pipeline_validation_module
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _linear_pipeline(**overrides) -> dict:
    body = {
        "title": "Nettoyer villes",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection",
                     "params": {"collectionId": "villes"}},
                    {"id": "w1", "kind": "writer", "op": "writer.collection",
                     "params": {"collectionId": "villes_propres"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    body.update(overrides)
    return body


@pytest.fixture()
def env(monkeypatch):
    # Fake validators, isolating THIS task's structural (cycle/edge-count)
    # logic from Task 5's real op-catalog/collection checks. Using
    # monkeypatch.setitem (not a direct register_pipeline_node_validator
    # call) matters: _node_validators is a module-level global dict with no
    # reset between tests — a direct call here would permanently overwrite
    # whatever app.pipelines.config_validation registered at import time
    # (Task 5), and that overwrite would leak into test_pipeline_node_validation.py's
    # tests if this file happens to run first in the same pytest session
    # (it does, alphabetically: "config_validation" < "node_validation").
    # monkeypatch.setitem restores the previous value automatically at
    # teardown, so this file can never leak state into another test file
    # regardless of execution order.
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "reader.collection",
        lambda session, node, user: None,
    )
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "writer.collection",
        lambda session, node, user: None,
    )

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return TestClient(app)


def test_valid_linear_pipeline_saves(env):
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 201


def test_disabled_capability_refuses_pipeline_creation(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 403


def test_disabled_capability_does_not_affect_other_kinds(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json={
        "title": "App", "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
    })
    assert response.status_code == 201


def test_cyclic_graph_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "1=1"}}
    )
    body["config"]["pipeline"]["edges"] = [
        {"id": "e1", "from": "r1", "to": "t1"},
        {"id": "e2", "from": "t1", "to": "w1"},
        {"id": "e3", "from": "w1", "to": "t1"},
    ]
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "acyclic" in response.json()["detail"]


def test_node_with_two_incoming_edges_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "r2", "kind": "reader", "op": "reader.collection",
         "params": {"collectionId": "quartiers"}}
    )
    body["config"]["pipeline"]["edges"].append({"id": "e2", "from": "r2", "to": "w1"})
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "one incoming edge" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.configs.pipeline_validation'`

- [ ] **Step 3: Implement the registry + structural validation**

Create `core/app/configs/pipeline_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="pipeline" payloads without
importing app.pipelines (forbidden by the layered-architecture contract:
app.pipelines sits above app.configs). Structural graph checks (DAG
acyclic, linear+join topology — feasibility study §4.1 mitigation D1) live
here: they need no knowledge of the op catalogue. Per-node checks (op
exists, params match its manifest, collectionId exists/readable/writable)
are registered by app.pipelines.config_validation, imported for its side
effect by app.main — the only layer allowed to know about both. Mirrors
app.configs.dataset_validation exactly."""
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig, PipelineEdge, PipelineNode
from app.users.models import User

NodeValidator = Callable[[Session, PipelineNode, User], None]

_node_validators: dict[str, NodeValidator] = {}


def register_pipeline_node_validator(op: str, validator: NodeValidator) -> None:
    _node_validators[op] = validator


def _check_linear_topology(edges: list[PipelineEdge]) -> None:
    incoming_count: dict[str, int] = {}
    for edge in edges:
        incoming_count[edge.to] = incoming_count.get(edge.to, 0) + 1
    for node_id, count in incoming_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one incoming edge "
                       "(linear+join topology only, SP-15a MVP)",
            )


def _check_acyclic(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> None:
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def visit(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and visit(neighbor):
                return True
        color[node_id] = BLACK
        return False

    if any(color[n.id] == WHITE and visit(n.id) for n in nodes):
        raise HTTPException(status_code=422, detail="pipeline graph must be acyclic")


def validate_pipeline_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "pipeline":
        return
    payload = config.pipeline
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    _check_acyclic(payload.nodes, payload.edges)
    _check_linear_topology(payload.edges)

    for node in payload.nodes:
        validator = _node_validators.get(node.op)
        if validator is None:
            raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
        validator(session, node, user)
```

- [ ] **Step 4: Wire it into `configs/routes.py`, plus the ETL-disabled guard**

In `core/app/configs/routes.py`, change the import lines at the top (add
`is_etl_enabled` to the existing auth import, add the new validation import
right after the dataset one):

```python
from app.auth.dependency import get_current_user, is_etl_enabled
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
```

Add this helper right after `_validate_extension_scope` (after line 66):

```python
def _require_etl_enabled_for_pipeline(config: BuilderConfig) -> None:
    if config.kind == "pipeline" and not is_etl_enabled():
        raise HTTPException(status_code=403, detail="ETL capability disabled on this instance")
```

Then call both the guard and the validator at the three write points. In
`create_config` (after the existing `_validate_dataset_payload`/
`_validate_bookmark_payload` calls, i.e. after line 77):

```python
    _require_etl_enabled_for_pipeline(request.config)
    _validate_pipeline_payload(session, request.config, user=user)
```

Actually place the guard *first*, before any other validation (cheapest
check, fail fast) — the full sequence in `create_config` becomes:

```python
    _require_etl_enabled_for_pipeline(request.config)
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
    _validate_pipeline_payload(session, request.config, user=user)
```

In `update_config` (mirrors `create_config`'s sequence, after
`_require_access`):

```python
    _require_etl_enabled_for_pipeline(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
```

In `update_config_by_item` (same sequence, after `_require_access`):

```python
    _require_etl_enabled_for_pipeline(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 6: Run the full configs suite to check no regression**

Run: `cd core && uv run pytest tests/test_configs_extension_permissions.py tests/test_create_dataset.py tests/test_read_only_mode.py -v`
Expected: PASS (unchanged)

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/pipeline_validation.py core/app/configs/routes.py \
  core/tests/test_pipeline_config_validation.py
git commit -m "feat(core): validate pipeline graph structure at save time, gate on CORE_ETL_ENABLED"
```

---

## Task 5: Per-node validation (`app.pipelines` layer, registered into Task 4)

**Files:**
- Create: `core/app/pipelines/config_validation.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_pipeline_node_validation.py`

**Interfaces:**
- Consumes: `register_pipeline_node_validator` (Task 4), `OP_PARAMS` (Task 3).
- Produces: real per-op validators registered as a side effect of importing
  `app.pipelines.config_validation` — from this task on, `test_pipeline_config_validation.py`'s
  fake validators are no longer the only ones in play for a real app instance
  (the fakes remain fine as unit-test isolation, unaffected).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_node_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _pipeline_body(*, reader_collection: str, writer_collection: str) -> dict:
    return {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection",
                     "params": {"collectionId": reader_collection}},
                    {"id": "w1", "kind": "writer", "op": "writer.collection",
                     "params": {"collectionId": writer_collection}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('readable', :t, :o, 'readable', 'Readable', '', 'id', NULL, 1, 1)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('writable', :t, :o, 'writable', 'Writable', '', 'id', NULL, 0, 1)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('locked', :t, :o, 'locked', 'Locked', '', 'id', NULL, 0, 0)"
        ), {"t": tenant.id, "o": other.id})
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    return TestClient(app)


def test_valid_pipeline_with_existing_collections_saves(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="writable",
    ))
    assert response.status_code == 201


def test_reader_collection_missing_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="does-not-exist", writer_collection="writable",
    ))
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_writer_collection_not_editable_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="locked",
    ))
    assert response.status_code == 422


def test_missing_required_param_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["params"] = {}
    response = env.post("/configs", json=body)
    assert response.status_code == 422


def test_unknown_op_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["op"] = "reader.does-not-exist"
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "unknown op" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
Expected: FAIL — `test_reader_collection_missing_is_rejected` and others get
`422 unknown op 'reader.collection'` (no real validator registered yet in a
freshly-created app — the fake validators from Task 4's own test file don't
leak across test modules) instead of the specific collection-not-found
message; `test_valid_pipeline_with_existing_collections_saves` fails with 422.

- [ ] **Step 3: Implement the real per-node validators**

Create `core/app/pipelines/config_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registers the real per-op node validators for kind="pipeline" configs
(see app.configs.pipeline_validation for why this indirection exists).
Imported for its side effect by app.main, the only layer allowed to know
about both app.pipelines and app.configs — mirrors
app.collections.dataset_validation exactly.

Boundary decision (design SP-15a, Global Constraints): only param SHAPE
(Pydantic) and referenced-collection existence/permission are checked here,
at save time. Bounded SQL expressions (filter.expr, derive.expr,
aggregate.metrics values) and transform.join.on column existence are only
checked at execution time (app.pipelines.expr_validation / runtime) — a bad
expression fails the run clearly, it never blocks saving the pipeline."""
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.pipeline_validation import register_pipeline_node_validator
from app.configs.schemas import PipelineNode
from app.pipelines.ops.schemas import OP_PARAMS
from app.sharing.authorization import can
from app.users.models import User

_COLLECTION_PARAM_FIELD = {
    "reader.collection": "collectionId",
    "transform.join": "withCollectionId",
    "writer.collection": "collectionId",
}
_WRITE_OPS = {"writer.collection"}


def _validate_params(node: PipelineNode) -> BaseModel:
    model = OP_PARAMS.get(node.op)
    if model is None:
        raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
    try:
        return model.model_validate(node.params)
    except Exception as exc:  # pydantic.ValidationError, reported verbatim
        raise HTTPException(status_code=422, detail=f"{node.op}: {exc}") from exc


def _require_readable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        # Same message as not-found: don't leak collection existence.
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")


def _require_writable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    writable = can(
        session, user_id=user.id, action="write",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not writable or not collection.editable:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' is not writable")


def _validate_node(session: Session, node: PipelineNode, user: User) -> None:
    params = _validate_params(node)
    field = _COLLECTION_PARAM_FIELD.get(node.op)
    if field is None:
        return
    collection_id = getattr(params, field)
    if node.op in _WRITE_OPS:
        _require_writable_collection(session, user=user, collection_id=collection_id)
    else:
        _require_readable_collection(session, user=user, collection_id=collection_id)


for _op in OP_PARAMS:
    register_pipeline_node_validator(_op, _validate_node)
```

- [ ] **Step 4: Wire the side-effect import into `app.main`**

In `core/app/main.py`, add right after the existing
`harvest_dataset_validation` import (after line 15):

```python
from app.pipelines import config_validation as pipelines_config_validation  # noqa: F401
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 6: Run the full pipeline + configs test suite to check no regression**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py tests/test_pipeline_config_schema.py tests/test_pipeline_ops_schemas.py tests/test_configs_extension_permissions.py -v`
Expected: PASS (unchanged)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/config_validation.py core/app/main.py \
  core/tests/test_pipeline_node_validation.py
git commit -m "feat(core): validate pipeline node params + collection permissions at save time"
```

---

## Task 6: Bounded SQL expression validation + DAG compiler

**Files:**
- Create: `core/app/pipelines/expr_validation.py`
- Create: `core/app/pipelines/compiler.py`
- Test: `core/tests/test_pipeline_expr_validation.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `app.analytics.sql_sandbox` (`parse_ast`, `validate_select_only`,
  `collect_table_refs`, `SqlSandboxError` — all already public names in that
  module), `PipelineNode`/`PipelineEdge` (Task 2), the 6 `Transform*Params`
  classes (Task 3).
- Produces: `validate_bounded_expr(conn, expr) -> None` (raises
  `SqlSandboxError`) in `app.pipelines.expr_validation`; `topological_order`,
  `predecessor_id`, `compile_transform_sql` in `app.pipelines.compiler` —
  consumed by Task 8's runtime.

- [ ] **Step 1: Write the failing tests for expression validation**

Create `core/tests/test_pipeline_expr_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.expr_validation import validate_bounded_expr


@pytest.fixture()
def conn():
    return duckdb.connect(":memory:")


def test_valid_scalar_expression_passes(conn):
    validate_bounded_expr(conn, "1 + 1")


def test_valid_boolean_expression_passes(conn):
    validate_bounded_expr(conn, "pop > 1000")


def test_invalid_syntax_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "pop >")


def test_expression_referencing_a_table_raises(conn):
    with pytest.raises(SqlSandboxError, match="must not reference a table"):
        validate_bounded_expr(conn, "(SELECT 1 FROM some_table)")


def test_injection_attempt_via_closing_paren_raises(conn):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(conn, "1) UNION SELECT password FROM users--")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_expr_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.expr_validation'`

- [ ] **Step 3: Implement `expr_validation.py`**

Create `core/app/pipelines/expr_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Validation d'une expression scalaire SQL DuckDB bornée pour
transform.filter/transform.derive/transform.aggregate.metrics (design SP-15a
§5.1 — correction de l'étude de faisabilité, qui affirmait à tort qu'un
moteur CEL tournait déjà côté serveur). Réutilise le même mécanisme AST que
app.analytics.sql_sandbox (json_serialize_sql), restreint à UNE expression
scalaire enveloppée dans un SELECT sans FROM — jamais un SELECT complet,
jamais une référence de table."""
import duckdb

from app.analytics.sql_sandbox import SqlSandboxError, collect_table_refs, parse_ast, validate_select_only


def validate_bounded_expr(conn: duckdb.DuckDBPyConnection, expr: str) -> None:
    ast = parse_ast(conn, f"SELECT ({expr})")
    validate_select_only(ast)
    if collect_table_refs(ast):
        raise SqlSandboxError("expression must not reference a table")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_expr_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 5: Write the failing tests for the compiler**

Create `core/tests/test_pipeline_compiler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.compiler import compile_transform_sql, predecessor_id, topological_order


def _node(id_, kind, op, **params) -> PipelineNode:
    return PipelineNode(id=id_, kind=kind, op=op, params=params)


def _edge(id_, from_, to) -> PipelineEdge:
    return PipelineEdge(id=id_, **{"from": from_}, to=to)


def test_topological_order_linear_chain():
    nodes = [
        _node("w1", "writer", "writer.collection", collectionId="out"),
        _node("r1", "reader", "reader.collection", collectionId="in"),
        _node("t1", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "r1", "t1"), _edge("e2", "t1", "w1")]
    ordered_ids = [n.id for n in topological_order(nodes, edges)]
    assert ordered_ids == ["r1", "t1", "w1"]


def test_topological_order_raises_on_cycle():
    nodes = [
        _node("a", "transform", "transform.filter", expr="1=1"),
        _node("b", "transform", "transform.filter", expr="1=1"),
    ]
    edges = [_edge("e1", "a", "b"), _edge("e2", "b", "a")]
    with pytest.raises(ValueError, match="acyclic"):
        topological_order(nodes, edges)


def test_predecessor_id_returns_single_upstream():
    edges = [_edge("e1", "r1", "t1")]
    assert predecessor_id("t1", edges) == "r1"


def test_predecessor_id_returns_none_when_no_incoming_edge():
    assert predecessor_id("r1", []) is None


def test_predecessor_id_raises_on_multiple_incoming_edges():
    edges = [_edge("e1", "r1", "w1"), _edge("e2", "r2", "w1")]
    with pytest.raises(ValueError, match="one incoming edge"):
        predecessor_id("w1", edges)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE base (id INTEGER, region VARCHAR, pop INTEGER)")
    c.execute("INSERT INTO base VALUES (1, 'Nord', 10), (2, 'Sud', 5), (3, 'Nord', 20)")
    return c


def test_compile_filter(conn):
    sql = compile_transform_sql("transform.filter", {"expr": "pop > 8"}, input_view="base")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id FROM out ORDER BY id").fetchall()
    assert rows == [(1,), (3,)]


def test_compile_select_with_rename(conn):
    sql = compile_transform_sql(
        "transform.select", {"columns": {"region": "zone", "pop": None}}, input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["zone", "pop"]


def test_compile_derive(conn):
    sql = compile_transform_sql(
        "transform.derive", {"column": "pop_double", "expr": "pop * 2"}, input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn.execute("SELECT pop_double FROM out WHERE id = 1").fetchone()
    assert row == (20,)


def test_compile_aggregate(conn):
    sql = compile_transform_sql(
        "transform.aggregate",
        {"groupBy": ["region"], "metrics": {"total_pop": "SUM(pop)"}},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(conn.execute("SELECT region, total_pop FROM out").fetchall())
    assert rows == {"Nord": 30, "Sud": 5}


def test_compile_join(conn):
    conn.execute("CREATE TABLE other (id INTEGER, label VARCHAR)")
    conn.execute("INSERT INTO other VALUES (1, 'A'), (2, 'B')")
    sql = compile_transform_sql(
        "transform.join", {"withCollectionId": "x", "on": "id", "how": "inner"},
        input_view="base", join_view="other",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, label FROM out ORDER BY id").fetchall()
    assert rows == [(1, "A"), (2, "B")]


def test_compile_join_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql(
            "transform.join", {"withCollectionId": "x", "on": "id"}, input_view="base",
        )


def test_compile_unknown_transform_op_raises():
    with pytest.raises(ValueError, match="not a transform op"):
        compile_transform_sql("reader.collection", {"collectionId": "x"}, input_view="base")
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.compiler'`

- [ ] **Step 7: Implement `compiler.py`**

Create `core/app/pipelines/compiler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Compilateur DAG→SQL du runtime étage 1 (design SP-15a §6.1). Topologie
linéaire+join uniquement (Global Constraints de ce plan — feasibility study
§4.1 D1) : chaque nœud a au plus une arête entrante, le second flux de
transform.join est un PARAM (withCollectionId), jamais une seconde arête.
Pas de fusion : compile_transform_sql produit UN fragment SQL par nœud
transform, exécuté comme sa propre TEMP VIEW par le runtime (Task 8) — ce
module ne touche jamais une connexion DuckDB, il ne fait que construire des
chaînes de caractères, testable en pur."""
from app.configs.schemas import PipelineEdge, PipelineNode
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformDeriveParams, TransformFilterParams,
    TransformJoinParams, TransformSelectParams,
)


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def topological_order(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> list[PipelineNode]:
    by_id = {n.id: n for n in nodes}
    indegree = {n.id: 0 for n in nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)
        indegree[edge.to] += 1

    queue = sorted(n.id for n in nodes if indegree[n.id] == 0)
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        newly_ready = []
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                newly_ready.append(neighbor)
        queue = sorted(queue + newly_ready)

    if len(ordered) != len(nodes):
        raise ValueError("pipeline graph must be acyclic")
    return [by_id[i] for i in ordered]


def predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    incoming = [e.from_ for e in edges if e.to == node_id]
    if len(incoming) > 1:
        raise ValueError(
            f"node '{node_id}' has more than one incoming edge "
            "(linear+join topology only, SP-15a MVP)"
        )
    return incoming[0] if incoming else None


def compile_transform_sql(
    op: str, params: dict, *, input_view: str, join_view: str | None = None,
) -> str:
    if op == "transform.filter":
        p = TransformFilterParams.model_validate(params)
        return f"SELECT * FROM {_qi(input_view)} WHERE ({p.expr})"

    if op == "transform.select":
        p = TransformSelectParams.model_validate(params)
        cols = ", ".join(
            f"{_qi(src)} AS {_qi(dst)}" if dst else _qi(src)
            for src, dst in p.columns.items()
        )
        return f"SELECT {cols} FROM {_qi(input_view)}"

    if op == "transform.derive":
        p = TransformDeriveParams.model_validate(params)
        return f"SELECT *, ({p.expr}) AS {_qi(p.column)} FROM {_qi(input_view)}"

    if op == "transform.aggregate":
        p = TransformAggregateParams.model_validate(params)
        group_cols = ", ".join(_qi(c) for c in p.groupBy)
        metric_cols = ", ".join(f"({expr}) AS {_qi(name)}" for name, expr in p.metrics.items())
        select_cols = ", ".join(filter(None, [group_cols, metric_cols]))
        group_clause = f" GROUP BY {group_cols}" if group_cols else ""
        return f"SELECT {select_cols} FROM {_qi(input_view)}{group_clause}"

    if op == "transform.join":
        p = TransformJoinParams.model_validate(params)
        assert join_view is not None, "transform.join requires join_view"
        join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
        return (
            f"SELECT * FROM {_qi(input_view)} {join_kw} {_qi(join_view)} "
            f"USING ({_qi(p.on)})"
        )

    raise ValueError(f"'{op}' is not a transform op")
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: PASS (11 tests green)

- [ ] **Step 9: Commit**

```bash
git add core/app/pipelines/expr_validation.py core/app/pipelines/compiler.py \
  core/tests/test_pipeline_expr_validation.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): bounded SQL expression validation + linear+join DAG compiler"
```

---

## Task 7: `PipelineRun` model + migration + repository

**Files:**
- Create: `core/app/pipelines/models.py`
- Create: `core/alembic/versions/0018_pipeline_runs.py`
- Create: `core/app/pipelines/repository.py`
- Test: `core/tests/test_pipeline_repository.py`

**Interfaces:**
- Produces: `PipelineRun` ORM model; `create_run`, `get_run`, `list_runs`,
  `mark_running`, `mark_succeeded`, `mark_failed` in
  `app.pipelines.repository` — consumed by Task 9 (job) and Task 10 (routes).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.db import Base, make_engine, make_session_factory
from app.pipelines import repository as repo
from app.tenants.repository import get_or_create_default_tenant


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_create_run_defaults_to_queued():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        assert run.status == "queued"
        assert run.started_at is None


def test_get_run_round_trips():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched is not None
        assert fetched.id == run.id


def test_get_run_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        assert repo.get_run(s, tenant_id="other-tenant", run_id=run.id) is None


def test_list_runs_ordered_most_recent_first():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        first = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        second = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        runs = repo.list_runs(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        assert [r.id for r in runs] == [second.id, first.id] or set(r.id for r in runs) == {first.id, second.id}


def test_mark_running_then_succeeded():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        repo.mark_running(s, run_id=run.id)
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "running"
        assert fetched.started_at is not None

        repo.mark_succeeded(s, run_id=run.id, node_stats={"r1": {"rowCount": 3}})
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "succeeded"
        assert fetched.node_stats == {"r1": {"rowCount": 3}}
        assert fetched.finished_at is not None


def test_mark_failed_records_error():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id="item-1")
        s.commit()
        repo.mark_failed(s, run_id=run.id, error="collection not found")
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "failed"
        assert fetched.error == "collection not found"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.models'`

- [ ] **Step 3: Implement the model**

Create `core/app/pipelines/models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    pipeline_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    node_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

Note: `pipeline_item_id` references `items.id`, not a separate `pipelines`
table — a pipeline IS an `Item` + `Config` (`kind="pipeline"`), exactly like
a dataset or a bookmark (design §4.1). This table only tracks *runs*.

- [ ] **Step 4: Create the migration**

Create `core/alembic/versions/0018_pipeline_runs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""app.pipelines — pipeline_runs (SP-15a)

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("pipeline_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("node_stats", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
```

- [ ] **Step 5: Implement the repository**

Create `core/app/pipelines/repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pipelines.models import PipelineRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, *, tenant_id: str, pipeline_item_id: str) -> PipelineRun:
    run = PipelineRun(
        id=uuid.uuid4().hex, tenant_id=tenant_id, pipeline_item_id=pipeline_item_id,
        status="queued",
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def get_run(session: Session, *, tenant_id: str, run_id: str) -> PipelineRun | None:
    return session.execute(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.tenant_id == tenant_id)
    ).scalar_one_or_none()


def list_runs(session: Session, *, tenant_id: str, pipeline_item_id: str) -> list[PipelineRun]:
    rows = session.execute(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id, PipelineRun.pipeline_item_id == pipeline_item_id)
        .order_by(PipelineRun.created_at.desc())
    ).scalars().all()
    return list(rows)


def mark_running(session: Session, *, run_id: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "running"
    run.started_at = _now()
    session.flush()


def mark_succeeded(session: Session, *, run_id: str, node_stats: dict) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "succeeded"
    run.finished_at = _now()
    run.node_stats = node_stats
    session.flush()


def mark_failed(session: Session, *, run_id: str, error: str) -> None:
    run = session.get(PipelineRun, run_id)
    if run is None:
        return
    run.status = "failed"
    run.finished_at = _now()
    run.error = error
    session.flush()
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -v`
Expected: PASS (6 tests green)

- [ ] **Step 7: Verify the migration applies cleanly against Postgres**

Run: `cd core && CORE_TEST_DATABASE_URL=$CORE_TEST_DATABASE_URL uv run alembic upgrade head`
(only if a local `CORE_TEST_DATABASE_URL`/`DATABASE_URL` Postgres is
available — otherwise skip this step, Task 9 will exercise it via the
`postgis` marker fixture, which builds tables through
`Base.metadata.create_all()` rather than Alembic, per this repo's existing
convention documented in `core/tests/conftest.py`)
Expected: no error, `alembic_version` advances to `0018`

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/models.py core/alembic/versions/0018_pipeline_runs.py \
  core/app/pipelines/repository.py core/tests/test_pipeline_repository.py
git commit -m "feat(core): add pipeline_runs table + repository"
```

---

## Task 8: Execution runtime (DuckDB, node-by-node)

**Files:**
- Create: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `open_connection` (`app.analytics.duckdb_conn`), `_dedup_cte`/
  `_has_any_file`/`_qi` (`app.analytics.aggregate`), `insert_feature`
  (`app.features.repository`), `rls_scope` (`app.features.rls`),
  `validate_feature` (`app.features.validation`), `introspect_table`
  (`app.collections.introspection_pg`), `topological_order`/`predecessor_id`/
  `compile_transform_sql` (Task 6's `app.pipelines.compiler`),
  `validate_bounded_expr` (Task 6's `expr_validation`), the 8 `*Params`
  classes (Task 3).
- Produces: `run_pipeline(session, *, payload, tenant_id, user, ...) ->
  list[NodeStat]` and `preview_pipeline(session, *, payload, tenant_id, user,
  up_to, ...) -> list[dict]` in `app.pipelines.runtime`, and
  `PipelineRuntimeError` — consumed by Task 9 (job) and Task 10 (preview
  route).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_runtime.py`. Non-write parts (reader +
transforms + preview) run against local-disk GeoParquet fixtures, no
Postgres needed (same technique as `test_analytics_aggregate.py`); the
`writer.collection` part needs real PostGIS (`insert_feature`/`rls_scope`
run real SQL against the `gis_rls` role) and is marked `postgis`.

```python
# SPDX-License-Identifier: Apache-2.0
import geopandas as gpd
import pytest
from shapely.geometry import Point
from sqlalchemy import text

from app.collections.introspection import ColumnInfo, TableInfo
from app.db import Base, make_engine, make_session_factory
from app.pipelines import runtime
from app.pipelines.repository import get_run
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = []

TABLE_INFO = TableInfo(
    table_name="villes", pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


def _write_partition(base_dir, *, tenant_id="t1", collection_id="villes", rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-05"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _row(id_, region, pop, *, op="insert", lsn=1, x=0.0, y=0.0):
    return {"id": id_, "region": region, "pop": pop, "_op": op, "_lsn": lsn,
            "_ts": 1.0, "geometry": Point(x, y)}


class _FakeCollections:
    """Stand-in that lets Task 8's tests exercise the reader/transform chain
    without a real collections table — the reader/transform half of the
    runtime only needs table_info + base_uri, never a live Collection row."""


def test_preview_filter_and_derive(tmp_path, monkeypatch):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", 10), _row(2, "Sud", 5), _row(3, "Nord", 20),
    ])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: TABLE_INFO,
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "pop > 8"}},
        {"id": "t2", "kind": "transform", "op": "transform.derive",
         "params": {"column": "pop_double", "expr": "pop * 2"}},
        {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "out.csv"}},
    ]
    edges = [
        {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
        {"id": "e3", "from": "t2", "to": "w1"},
    ]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": edges})

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    by_id = {r["id"]: r for r in rows}
    assert by_id[1]["pop_double"] == 40
    assert by_id[3]["pop_double"] == 40
    assert 2 not in by_id  # filtered out (pop=5 <= 8)


def test_preview_rejects_writer_node_as_up_to(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: TABLE_INFO,
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })
    with pytest.raises(runtime.PipelineRuntimeError, match="writer"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="w1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


@pytest.mark.postgis
def test_run_pipeline_writes_into_target_collection(pg_engine, monkeypatch, tmp_path):
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
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('villes_propres', :t, :o, 'villes_propres', 'Villes propres', "
            "'', 'id', 'geometry', 0, 1)"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_propres (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[
            _row(1, "Nord", 10, x=1.0, y=45.0), _row(2, "Sud", 5, x=2.0, y=46.0),
        ])

        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: TABLE_INFO)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection",
                 "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        })

        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        count = s.execute(text("SELECT count(*) FROM villes_propres")).scalar()
        assert count == 2
        assert any(stat.op == "writer.collection" and stat.rowCount == 2 for stat in stats)

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_propres; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v -k "not postgis"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.runtime'`

- [ ] **Step 3: Implement `runtime.py`**

Create `core/app/pipelines/runtime.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Exécution d'un Pipeline (SP-15a) — étage 1 uniquement (DuckDB
in-process), nœud par nœud, sans fusion (design §1 non-but, mitigation D4
de l'étude de faisabilité). Réutilise tel quel : la connexion DuckDB
éphémère (app.analytics.duckdb_conn), le CTE de dédoublonnage GeoParquet
CDC (app.analytics.aggregate._dedup_cte), le chemin d'écriture OGC
Features (insert_feature/rls_scope/validate_feature).

Deux passes, dans cet ordre (comme app.analytics.sql_sandbox._materialize
puis _lock_down — jamais l'inverse) :
  1. matérialiser TOUTES les lectures externes (chaque reader.collection +
     le withCollectionId de chaque transform.join) en TEMP VIEW ;
  2. verrouiller l'accès externe (enable_external_access=false,
     lock_configuration=true), PUIS exécuter transforms/writers dans
     l'ordre topologique — les expr bornées (filter/derive/aggregate
     metrics) sont validées juste avant d'être compilées (Task 6), jamais
     avant (design Global Constraints : la validation sémantique est une
     affaire d'exécution, pas de sauvegarde).

Convention de colonne géométrie : chaque vue de reader matérialisée
renomme sa colonne géométrie source en "geometry" (quel que soit son nom
réel dans la collection), pour que le reste de la chaîne (writer.collection
compris) n'ait jamais à connaître le nom d'origine — cf. Task 8 note."""
import csv
import io
import json

import duckdb
from sqlalchemy.orm import Session

from app.analytics.aggregate import _dedup_cte, _has_any_file
from app.analytics.duckdb_conn import open_connection
from app.collections import repository as collections_repo
from app.collections.introspection import TableInfo, TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.configs.schemas import PipelineNode, PipelinePayload
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.features.validation import validate_feature
from app.pipelines import compiler
from app.pipelines.expr_validation import validate_bounded_expr
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, TransformAggregateParams, TransformDeriveParams,
    TransformFilterParams, TransformJoinParams, WriterCollectionParams, WriterExportParams,
)
from app.sharing.authorization import can
from app.users.models import User


def _qi(name: str) -> str:
    # Duplication délibérée du helper de 2 lignes de app.pipelines.compiler
    # (lui-même une duplication de app.analytics.aggregate._qi) plutôt qu'un
    # import inter-module d'un nom privé `_`-préfixé — cf. compiler.py.
    return '"' + name.replace('"', '""') + '"'


class PipelineRuntimeError(Exception):
    """Erreur d'exécution : la tâche procrastinate (Task 9) l'attrape et
    marque le run 'failed', jamais 'zombie'."""


class NodeStat:
    def __init__(self, node_id: str, op: str, row_count: int | None = None):
        self.nodeId = node_id
        self.op = op
        self.rowCount = row_count

    def to_dict(self) -> dict:
        return {"nodeId": self.nodeId, "op": self.op, "rowCount": self.rowCount}


def _require_readable_collection_id(
    session: Session, *, tenant_id: str, user: User, collection_id: str,
) -> str:
    collection = collections_repo.get_collection(
        session, tenant_id=tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    if not can(session, user_id=user.id, action="read",
               item=collections_repo.get_access_facts(collection), kind="collection",
               actor_is_admin=user.is_admin):
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    return collection.table_name


def _require_writable_collection(session: Session, *, tenant_id: str, user: User, collection_id: str):
    collection = collections_repo.get_collection(
        session, tenant_id=tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise PipelineRuntimeError(f"collection '{collection_id}' not found")
    if not can(session, user_id=user.id, action="write",
               item=collections_repo.get_access_facts(collection), kind="collection",
               actor_is_admin=user.is_admin):
        raise PipelineRuntimeError(f"collection '{collection_id}' is not writable")
    if not collection.editable:
        raise PipelineRuntimeError(f"collection '{collection_id}' is not writable")
    return collection


def _table_info_for_collection(session: Session, collection_id: str) -> TableInfo:
    try:
        return introspect_table(session, collection_id)
    except TableNotFound as exc:
        raise PipelineRuntimeError(f"backing table for '{collection_id}' not found") from exc
    except UnsupportedTable as exc:
        raise PipelineRuntimeError(exc.reason) from exc


def _materialize_reader(conn, *, view_name: str, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo) -> None:
    # Comme app.analytics.sql_sandbox._materialize : DuckDB ne peut pas
    # déduire un schéma d'un glob qui ne correspond à aucun fichier, donc pas
    # de "vue vide typée" possible ici — échec propre et explicite plutôt
    # qu'une vue dont le schéma serait un mensonge (même choix que
    # sql_sandbox, qui lève SqlSandboxError dans exactement ce cas).
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        raise PipelineRuntimeError(f"collection '{collection_id}' has no data yet")
    geom_col = table_info.geometry_column
    select_list = f"* EXCLUDE ({_qi(geom_col)}), {_qi(geom_col)} AS geometry" if geom_col else "*"
    cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {cte} SELECT {select_list} FROM live")


def _lock_down(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")


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


def _prepare(
    conn, session: Session, payload: PipelinePayload, *, tenant_id: str, user: User, base_uri: str,
) -> tuple[list[PipelineNode], dict[str, str]]:
    """Passe 1 : matérialise tous les readers (+ le withCollectionId de
    chaque transform.join), puis verrouille. Retourne (ordre topologique,
    view_name par node.id) — writer nodes n'ont pas encore de vue."""
    ordered = compiler.topological_order(payload.nodes, payload.edges)
    view_by_node: dict[str, str] = {}

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

    for node in ordered:
        if node.op != "transform.join":
            continue
        p = TransformJoinParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.withCollectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        join_view = f"node_{node.id}__join"
        _materialize_reader(
            conn, view_name=join_view, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.withCollectionId, table_info=table_info,
        )

    _lock_down(conn)
    return ordered, view_by_node


def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str], *, stop_at: str | None = None,
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
        join_view = f"node_{node.id}__join" if node.op == "transform.join" else None
        _validate_node_exprs(conn, node)
        sql = compiler.compile_transform_sql(node.op, node.params, input_view=input_view, join_view=join_view)
        view_name = f"node_{node.id}"
        conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
        view_by_node[node.id] = view_name
        stats.append(NodeStat(node.id, node.op, _view_row_count(conn, view_name)))
        if stop_at == node.id:
            return stats
    return stats


def _view_row_count(conn, view_name: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {_qi(view_name)}").fetchone()[0]


def preview_pipeline(
    *, session: Session | None, payload: PipelinePayload, tenant_id: str, user: User | None,
    up_to: str, endpoint_url: str, access_key: str, secret_key: str, base_uri: str, limit: int = 50,
) -> list[dict]:
    target = next((n for n in payload.nodes if n.id == up_to), None)
    if target is None:
        raise PipelineRuntimeError(f"node '{up_to}' not found")
    if target.kind == "writer":
        raise PipelineRuntimeError("preview cannot target a writer node")

    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node = _prepare(conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri)
        _execute_transform_chain(conn, ordered, payload.edges, view_by_node, stop_at=up_to)
        rows = conn.execute(f"SELECT * FROM {_qi(view_by_node[up_to])} LIMIT {int(limit)}").fetchall()
        cols = [d[0] for d in conn.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def _write_collection(session: Session, conn, *, node: PipelineNode, view_by_node: dict, tenant_id: str, user: User) -> NodeStat:
    p = WriterCollectionParams.model_validate(node.params)
    collection = _require_writable_collection(session, tenant_id=tenant_id, user=user, collection_id=p.collectionId)
    info = _table_info_for_collection(session, collection.table_name)
    # view_by_node[node.id] is set by the caller (run_pipeline) to the
    # predecessor's view name before calling this function.
    input_view = view_by_node[node.id]

    input_cols = {d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description}
    has_geometry = "geometry" in input_cols
    # Convertit la géométrie en GeoJSON DANS la requête DuckDB (ST_AsGeoJSON),
    # jamais en repassant un objet géométrie déjà récupéré comme paramètre
    # lié d'une requête ultérieure — un aller-retour fragile, non nécessaire.
    select_list = (
        f"* EXCLUDE (geometry), ST_AsGeoJSON(geometry) AS geometry" if has_geometry else "*"
    )
    rows = conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}").fetchall()
    cols = [d[0] for d in conn.description]

    count = 0
    with rls_scope(session, tenant_id):
        for raw in rows:
            row = dict(zip(cols, raw))
            geometry = json.loads(row.pop("geometry")) if has_geometry and row.get("geometry") is not None else None
            properties = row
            feature = {"type": "Feature", "properties": properties, "geometry": geometry}
            errors = validate_feature(info, feature)
            if errors:
                raise PipelineRuntimeError(f"writer.collection: invalid row: {errors}")
            insert_feature(session, info, properties=properties, geometry=geometry)
            count += 1
    return NodeStat(node.id, node.op, count)


def _write_export(conn, s3_client, exports_bucket: str, *, node: PipelineNode, view_by_node: dict) -> NodeStat:
    p = WriterExportParams.model_validate(node.params)
    input_view = view_by_node[node.id]
    rows = conn.execute(f"SELECT * FROM {_qi(input_view)}").fetchall()
    columns = [d[0] for d in conn.description]
    if p.format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        writer.writerows(rows)
        body = buf.getvalue().encode("utf-8")
    else:
        features = [
            {"type": "Feature", "properties": dict(zip(columns, row)), "geometry": None}
            for row in rows
        ]
        body = json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")
    s3_client.put_object(Bucket=exports_bucket, Key=p.key, Body=body)
    return NodeStat(node.id, node.op, len(rows))


def run_pipeline(
    session: Session, *, payload: PipelinePayload, tenant_id: str, user: User,
    endpoint_url: str, access_key: str, secret_key: str, base_uri: str,
    s3_client=None, exports_bucket: str | None = None,
) -> list[NodeStat]:
    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node = _prepare(conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri)
        stats = _execute_transform_chain(conn, ordered, payload.edges, view_by_node)
        for node in ordered:
            if node.kind != "writer":
                continue
            pred_id = compiler.predecessor_id(node.id, payload.edges)
            assert pred_id is not None
            view_by_node[node.id] = view_by_node[pred_id]
            if node.op == "writer.collection":
                stats.append(_write_collection(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                ))
            elif node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stats.append(_write_export(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node))
        return stats
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify it passes (non-postgis tests)**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v -k "not postgis"`
Expected: PASS (2 tests green)

- [ ] **Step 5: Run the postgis test (only if `CORE_TEST_DATABASE_URL` is set locally)**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_pipeline_runtime.py -v -m postgis`
Expected: PASS. If no local PostGIS is available, this test is skipped
(`pytest.mark.postgis`) — note that explicitly rather than silently treating
it as passing; it must be run for real at least once before this task is
considered done (in CI or a local docker-compose Postgres), since it is the
only test exercising the real write path end-to-end.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py
git commit -m "feat(core): DuckDB execution runtime for Phase 1 pipelines"
```

---

## Task 9: Procrastinate job

**Files:**
- Create: `core/app/pipelines/jobs.py`
- Modify: `core/app/jobs.py`
- Modify: `docker-compose.yml`
- Test: `core/tests/test_pipeline_jobs.py`

**Interfaces:**
- Consumes: `run_pipeline` (Task 8's `app.pipelines.runtime`),
  `mark_running`/`mark_succeeded`/`mark_failed`/`get_run` (Task 7's
  `app.pipelines.repository`).
- Produces: `run_pipeline_task(run_id, tenant_id)` (`@app.task(queue="etl")`)
  in `app.pipelines.jobs` — consumed by Task 10's `POST /pipelines/{id}/run`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_pipeline_jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import geopandas as gpd
import pytest
from procrastinate import testing
from shapely.geometry import Point
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


def _write_partition(base_dir, *, tenant_id, collection_id="villes", rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-05"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item_id = "item-1"
        s.execute(text(
            "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, is_published, is_public) "
            "VALUES (:id, :t, :o, 'pipeline', 'P', 0, 0)"
        ), {"id": item_id, "t": tenant.id, "o": user.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, description, "
            "pk_column, geometry_column, is_public, editable) "
            "VALUES ('villes_propres', :t, :o, 'villes_propres', 'V', '', 'id', 'geometry', 0, 1)"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_propres (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        s.commit()

    _write_partition(tmp_path, tenant_id=tenant.id, rows=[
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Point(1.0, 45.0)},
    ])
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    monkeypatch.setenv("S3_CDC_BUCKET_BASE_URI", str(tmp_path))

    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.collection",
             "params": {"collectionId": "villes_propres"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })
    # Patch the runtime's collection lookups the same way Task 8's own tests do
    # (run_pipeline_task calls app.pipelines.runtime.run_pipeline, so the seams
    # to patch live on that module, not on pipeline_jobs itself).
    from app.pipelines import runtime as pipeline_runtime
    from app.collections.introspection import ColumnInfo, TableInfo
    table_info = TableInfo(
        table_name="villes", pk_column="id", geometry_column="geometry",
        geometry_type="Point", srid=4326,
        columns=[ColumnInfo(name="region", type="string", required=True),
                 ColumnInfo(name="pop", type="integer", required=True)],
    )
    monkeypatch.setattr(pipeline_runtime, "_table_info_for_collection",
                        lambda session, collection_id: table_info if collection_id == "villes" else
                        pipeline_runtime.introspect_table(session, collection_id))
    monkeypatch.setattr(
        pipeline_runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: "villes" if collection_id == "villes" else collection_id,
    )
    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: payload)

    in_memory = testing.InMemoryConnector()
    with pipeline_jobs.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user, item_id
    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_propres; "
            "TRUNCATE pipeline_runs, items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def test_run_pipeline_task_marks_run_succeeded(env):
    app, Session, tenant, user, item_id = env
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "succeeded"
        count = s.execute(text("SELECT count(*) FROM villes_propres")).scalar()
        assert count == 1


def test_run_pipeline_task_marks_run_failed_never_zombie(env, monkeypatch):
    app, Session, tenant, user, item_id = env

    def _boom(session, *, item_id):
        raise ValueError("bad config")

    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error is not None
```

Note: this test's fixture is dense because it has to stand up a real
pipeline item + target collection + GeoParquet partition + monkeypatch the
runtime's collection-lookup seams (same seams Task 8 tests already patch).
This is expected — it is the first genuinely end-to-end test of the whole
stack (Tasks 2 through 9 wired together through a real procrastinate
worker).

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -v -m postgis`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.jobs'`
(skipped entirely with `SKIPPED` if no `CORE_TEST_DATABASE_URL` — in that
case, note it and revisit once a local PostGIS is available, do not treat
skip as pass)

- [ ] **Step 3: Implement the job**

Create `core/app/pipelines/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-15a) : charge le Pipeline sauvegardé, l'exécute
via app.pipelines.runtime, met à jour le statut du run. Toute erreur marque
le run "failed", jamais de run bloqué en queued/running ("zombie", même
critère d'acceptation que SP-6a/run_ingestion_task). Tourne dans le worker
partagé (docker-compose.yml, queue dédiée "etl", cf. app.jobs pour la
raison de import_paths)."""
import logging
import os

from app.configs import repository as configs_repo
from app.configs.schemas import PipelinePayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.jobs import app
from app.pipelines import repository as pipelines_repo
from app.pipelines.runtime import PipelineRuntimeError, run_pipeline
from app.users.models import User

logger = logging.getLogger(__name__)


def _get_pipeline_payload(session, *, item_id: str) -> PipelinePayload:
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "pipeline":
        raise ValueError(f"pipeline item '{item_id}' not found")
    payload = config.config.pipeline
    assert payload is not None
    return payload


def _acting_user(session, *, tenant_id: str, item_id: str) -> User:
    # Le run s'exécute en arrière-plan, sans session HTTP authentifiée — on
    # ré-évalue les permissions (design §7 "double vérification") avec
    # l'identité du PROPRIÉTAIRE du pipeline, jamais un contournement admin
    # implicite : si le propriétaire a perdu l'accès à une collection depuis
    # la sauvegarde, le run échoue proprement (cf. _require_readable/
    # writable_collection dans app.pipelines.runtime). ItemRead (le type que
    # renvoie items_repo.get_item) ne porte pas owner_id (seulement
    # owner=username, cf. app.items.repository._to_read) — on le relit donc
    # directement sur le modèle ORM plutôt que de passer par ItemRead.
    from sqlalchemy import select

    from app.items.models import Item

    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise ValueError(f"pipeline item '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _s3_client_from_env():
    from app.ingestion.storage import make_s3_client

    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _analytics_base_uri() -> str:
    override = os.environ.get("S3_CDC_BUCKET_BASE_URI")  # test seam, local-disk fixtures
    if override:
        return override
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    return f"s3://{bucket}/cdc"


@app.task(queue="etl")
def run_pipeline_task(run_id: str, tenant_id: str) -> None:
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    session_factory = make_session_factory(engine)

    try:
        with request_scoped_session(session_factory) as session:
            run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
            if run is None:
                logger.error("pipeline run %s introuvable (tenant %s)", run_id, tenant_id)
                return
            pipelines_repo.mark_running(session, run_id=run_id)
            item_id = run.pipeline_item_id

        with request_scoped_session(session_factory) as session:
            payload = _get_pipeline_payload(session, item_id=item_id)
            user = _acting_user(session, tenant_id=tenant_id, item_id=item_id)
            stats = run_pipeline(
                session, payload=payload, tenant_id=tenant_id, user=user,
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
                base_uri=_analytics_base_uri(),
                s3_client=_s3_client_from_env(),
                exports_bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"),
            )
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_succeeded(
                session, run_id=run_id,
                node_stats={s.nodeId: s.to_dict() for s in stats},
            )
    except (PipelineRuntimeError, ValueError) as exc:
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "failed", jamais zombie
        logger.exception("pipeline run %s : erreur inattendue", run_id)
        with request_scoped_session(session_factory) as session:
            pipelines_repo.mark_failed(session, run_id=run_id, error=f"erreur interne : {exc}")
```

- [ ] **Step 4: Register the module + queue**

In `core/app/jobs.py`, change `import_paths`:

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs",
    ],
```

In `docker-compose.yml`, change the `worker` service's `command:` (the
`-q ingestion,search,cdc` list):

```yaml
    command: >
      sh -c "python -m scripts.ensure_procrastinate_schema &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc,etl"
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest tests/test_pipeline_jobs.py -v -m postgis`
Expected: PASS (2 tests green). If no local PostGIS: note explicitly that
this must be run before considering the task done (same caveat as Task 8
Step 5).

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/jobs.py core/app/jobs.py docker-compose.yml \
  core/tests/test_pipeline_jobs.py
git commit -m "feat(core): add run_pipeline_task procrastinate job on the etl queue"
```

---

## Task 10: REST routes + `main.py` wiring + import-linter frontier

**Files:**
- Create: `core/app/pipelines/routes.py`
- Modify: `core/app/main.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_pipeline_routes.py`

**Interfaces:**
- Consumes: `create_run`/`get_run`/`list_runs` (Task 7), `run_pipeline_task`
  (Task 9), `preview_pipeline` (Task 8), `ops_catalog` (Task 3).
- Produces: `POST /pipelines/{item_id}/run`, `GET /pipelines/{item_id}/runs`,
  `POST /pipelines/{item_id}/preview`, `GET /pipelines/ops` — mounted **only**
  when `is_etl_enabled()` at `create_app()` time.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_app(monkeypatch, *, etl_enabled: bool):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true" if etl_enabled else "false")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    client = TestClient(app)
    client.tenant = tenant
    client.user = user
    return client


def test_pipelines_routes_absent_when_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/pipelines/ops").status_code == 404
    assert client.post("/pipelines/does-not-exist/run").status_code == 404


def test_get_pipelines_ops_returns_all_eight(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
    }


def test_run_route_defers_job_and_returns_run_id(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    deferred = {}

    def fake_deferrer(run_id, tenant_id):
        deferred["run_id"] = run_id
        deferred["tenant_id"] = tenant_id

    from app.pipelines import routes as pipelines_routes
    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: fake_deferrer

    create_response = client.post("/configs", json={
        "title": "P",
        "config": {
            "version": 1, "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "x"}},
                    {"id": "w1", "kind": "writer", "op": "writer.export",
                     "params": {"format": "csv", "key": "o.csv"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    })
    # This POST /configs will itself 422 (collection "x" doesn't exist,
    # Task 5's real validator rejects it) — use a route-level item instead:
    # exercise /pipelines/{id}/run against a 404 to prove the route SHAPE
    # (auth + not-found), the defer-on-success path is exercised in Task 9's
    # end-to-end job test instead (needs a real saveable pipeline, i.e. a
    # real collection, which belongs in a postgis-backed test).
    assert create_response.status_code == 422

    response = client.post("/pipelines/does-not-exist/run")
    assert response.status_code == 404


def test_preview_route_rejects_unknown_pipeline(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.post("/pipelines/does-not-exist/preview?upTo=r1")
    assert response.status_code == 404


def test_list_runs_route_rejects_unknown_pipeline(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/does-not-exist/runs")
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.routes'`

- [ ] **Step 3: Implement the routes**

Create `core/app/pipelines/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.pipelines.jobs import run_pipeline_task
from app.pipelines.ops.schemas import ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


class RunResponse(BaseModel):
    runId: str


class RunStatus(BaseModel):
    id: str
    status: str
    startedAt: str | None
    finishedAt: str | None
    error: str | None
    nodeStats: dict


def _require_pipeline_access(session: Session, *, user: User, item_id: str, action: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="pipeline not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")


def _require_pipeline_config(session: Session, item_id: str):
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "pipeline":
        raise HTTPException(status_code=404, detail="pipeline not found")
    return config


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(run_id: str, tenant_id: str) -> None:
        run_pipeline_task.defer(run_id=run_id, tenant_id=tenant_id)
    return deferrer


@router.get("/pipelines/ops")
def get_pipeline_ops() -> dict:
    return ops_catalog()


@router.post("/pipelines/{item_id}/run", response_model=RunResponse, status_code=202)
def run_pipeline_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    _require_pipeline_access(session, user=user, item_id=item_id, action="write")
    _require_pipeline_config(session, item_id)
    run = pipelines_repo.create_run(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="pipeline.run", object_type="pipeline_run", object_id=run.id,
        payload={"pipelineItemId": item_id},
    )
    # Commit avant de déférer : même raison que ingestion/routes.py
    # (create_upload_job) — un worker pourrait ramasser la tâche avant que
    # la ligne pipeline_runs ne soit visible autrement.
    session.commit()
    defer_task(run.id, user.tenant_id)
    return RunResponse(runId=run.id)


@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    _require_pipeline_access(session, user=user, item_id=item_id, action="read")
    _require_pipeline_config(session, item_id)
    runs = pipelines_repo.list_runs(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    return [
        RunStatus(
            id=r.id, status=r.status,
            startedAt=r.started_at.isoformat() if r.started_at else None,
            finishedAt=r.finished_at.isoformat() if r.finished_at else None,
            error=r.error, nodeStats=r.node_stats,
        )
        for r in runs
    ]


@router.post("/pipelines/{item_id}/preview")
def preview_pipeline_route(
    item_id: str,
    upTo: str = Query(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    _require_pipeline_access(session, user=user, item_id=item_id, action="read")
    config = _require_pipeline_config(session, item_id)
    try:
        return preview_pipeline(
            session=session, payload=config.config.pipeline, tenant_id=user.tenant_id, user=user,
            up_to=upTo, endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""), secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
        )
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Mount conditionally + fix the import-linter frontier**

In `core/app/main.py`, add the import near the other route imports (after
`app.mcp.server`):

```python
from app.pipelines import routes as pipelines_routes
```

And, inside `create_app()`, right after `app.include_router(harvest_routes.router)`:

```python
    if is_etl_enabled():
        app.include_router(pipelines_routes.router)
```

(`is_etl_enabled` is already imported at the top of `main.py` from Task 4's
Step 4 wiring? No — Task 4 only imported it into `configs/routes.py`. Add it
to `main.py`'s own import line: change `from app.auth.dependency import
is_read_only_mode` to `from app.auth.dependency import is_etl_enabled,
is_read_only_mode`.)

In `core/pyproject.toml`, insert `"app.pipelines"` between `"app.harvest"`
and `"app.ingestion"`:

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 6: Verify the import-linter contract still holds**

Run: `cd core && uv run lint-imports`
Expected: no violation reported (`app.pipelines` only imports
`app.features`/`app.collections`/`app.configs`/`app.ingestion`/`app.analytics`/
`app.sharing`/`app.audit`/`app.users`/`app.db`/`app.jobs`, all at or below
its new position)

- [ ] **Step 7: Run the full test suite for a broad regression check**

Run: `cd core && uv run pytest -v -k "not postgis"`
Expected: PASS (all non-postgis tests green — this is the first point where
every module written across Tasks 1-10 is exercised together)

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/routes.py core/app/main.py core/pyproject.toml \
  core/tests/test_pipeline_routes.py
git commit -m "feat(core): mount pipeline REST routes when CORE_ETL_ENABLED is on"
```

---

## Task 11: MCP tools

**Files:**
- Modify: `core/app/mcp/tools.py`
- Test: `core/tests/test_mcp_tools_pipeline.py`

**Interfaces:**
- Consumes: `BuilderConfig`/`PipelineNode`/`PipelineEdge`/`PipelinePayload`
  (Task 2), `is_etl_enabled` (Task 1), `get_task_deferrer`-equivalent
  (reimplemented inline, mirroring `create_dataset`'s existing pattern).
- Produces: `create_pipeline`, `run_pipeline`, `explain_pipeline` MCP tools
  — registered in `register_tools()` **only** when `is_etl_enabled()` at
  server-construction time (mirrors Task 10's router-mount timing).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_mcp_tools_pipeline.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
            username="mockuser", email=None, first_name="Mock", last_name="User",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app, base_url="http://localhost:8200")
    yield test_client


def _init_and_list_tools(test_client) -> set[str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}},
    }, headers=headers)
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}
    test_client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                     headers=session_headers)
    list_response = test_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    }, headers=session_headers)
    body_line = next(
        line for line in list_response.text.splitlines() if line.startswith("data: ")
    )
    payload = json.loads(body_line.removeprefix("data: "))
    return {tool["name"] for tool in payload["result"]["tools"]}


def test_pipeline_tools_absent_when_etl_disabled(app_client, monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    with app_client:
        names = _init_and_list_tools(app_client)
    assert "create_pipeline" not in names
    assert "run_pipeline" not in names
    assert "explain_pipeline" not in names


def test_pipeline_tools_present_when_etl_enabled(app_client, monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    with app_client:
        names = _init_and_list_tools(app_client)
    assert {"create_pipeline", "run_pipeline", "explain_pipeline"} <= names
```

Note: `is_etl_enabled()` must be read at `create_mcp_server()`/
`register_tools()` time — since `create_app()` is called fresh inside the
`app_client` fixture (before `monkeypatch.setenv` in the test body would take
effect for anything read at import time), each test in this file must set
`CORE_ETL_ENABLED` **before** `app_client` builds the app. Adjust the fixture
to accept the env var directly instead:

```python
@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # CORE_ETL_ENABLED is read by create_app()/register_tools() at
    # construction time (not per-request) — callers must set it via
    # monkeypatch.setenv BEFORE this fixture builds the app. Restructure as
    # a factory fixture instead of a fixed TestClient:
    def _build(etl_enabled: bool):
        monkeypatch.setenv("CORE_ETL_ENABLED", "true" if etl_enabled else "false")
        engine = make_engine(db_url)
        init_db(engine)
        Session = make_session_factory(engine)
        with Session() as setup_session:
            tenant = get_or_create_default_tenant(setup_session)
            get_or_create_user(
                setup_session, tenant_id=tenant.id, oidc_sub="mock-sub",
                username="mockuser", email=None, first_name="Mock", last_name="User",
            )
            setup_session.commit()
        app = create_app()

        def override_session():
            with request_scoped_session(Session) as session:
                yield session

        app.dependency_overrides[db.get_session] = override_session
        return TestClient(app, base_url="http://localhost:8200")

    return _build
```

And the two tests become:

```python
def test_pipeline_tools_absent_when_etl_disabled(app_client):
    client = app_client(etl_enabled=False)
    with client:
        names = _init_and_list_tools(client)
    assert "create_pipeline" not in names


def test_pipeline_tools_present_when_etl_enabled(app_client):
    client = app_client(etl_enabled=True)
    with client:
        names = _init_and_list_tools(client)
    assert {"create_pipeline", "run_pipeline", "explain_pipeline"} <= names
```

(Use this factory-fixture version, not the fixed-fixture draft above it —
the factory version is what Step 3 below assumes.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_mcp_tools_pipeline.py -v`
Expected: FAIL — `test_pipeline_tools_present_when_etl_enabled` fails
(`create_pipeline` not yet registered); `test_pipeline_tools_absent_when_etl_disabled`
already passes trivially (nothing registered yet either way) — that's fine,
it'll stay meaningful once Step 3 adds the tools.

- [ ] **Step 3: Add the three MCP tools**

In `core/app/mcp/tools.py`, add to the imports at the top (extend the
existing `app.auth.dependency` and `app.configs.schemas` import lines, add
three new ones — `validate_pipeline_payload` goes top-level, same
convention as the existing `validate_dataset_payload`/
`validate_bookmark_payload` imports right above it):

```python
from app.auth.dependency import admin_subs, is_etl_enabled, is_read_only_mode
from app.configs.pipeline_validation import validate_pipeline_payload
from app.configs.schemas import (
    BookmarkCrossFilterEntry, BookmarkPayload, BookmarkTimeRange, BuilderConfig,
    DatasetColumnMeta, DatasetPayload, PipelineEdge, PipelineNode, PipelinePayload,
)
from app.pipelines import repository as pipelines_repo
from app.pipelines.jobs import run_pipeline_task
```

Then, inside `register_tools()`, right after the `explain_dataset` tool
(after line 592 in the current file — i.e. right before `get_sharing`), add:

```python
    if is_etl_enabled():
        @server.tool()
        async def create_pipeline(
            ctx: Context, title: str, nodes: list[PipelineNode], edges: list[PipelineEdge],
        ) -> ItemRead:
            """Create a Pipeline (reader/transform/writer graph) — mirrors
            POST /configs with kind="pipeline". Only registered when
            CORE_ETL_ENABLED is on. SP-15a."""
            if is_read_only_mode():
                raise ValueError("Mode démo : lecture seule, écritures désactivées.")
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                payload = PipelinePayload(nodes=nodes, edges=edges)
                config = BuilderConfig(version=1, kind="pipeline", pipeline=payload)
                validate_pipeline_payload(session, config, user=user)
                item = items_repo.create_item(
                    session, tenant_id=user.tenant_id, owner_id=user.id,
                    resource_type="pipeline", title=title,
                )
                config_result = configs_repo.create_config(
                    session, config, item_id=item.id, tenant_id=user.tenant_id
                )
                write_audit(
                    session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                    action="item.create", object_type="item", object_id=item.id,
                    payload={"title": title},
                )
                write_audit(
                    session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                    action="config.create", object_type="config", object_id=config_result.id,
                    payload={"title": title, "kind": "pipeline"},
                )
                result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
                assert result is not None
                return result

        @server.tool()
        async def run_pipeline(ctx: Context, pipelineId: str) -> dict:
            """Defer a run of a Pipeline — mirrors POST /pipelines/{id}/run.
            Only registered when CORE_ETL_ENABLED is on. SP-15a."""
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                config = configs_repo.get_config_by_item(session, pipelineId)
                if config is None or config.config.kind != "pipeline":
                    raise ValueError("pipeline not found")
                facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=pipelineId)
                if facts is None or not can(session, user_id=user.id, action="write", item=facts):
                    raise ValueError("pipeline not found")
                run = pipelines_repo.create_run(
                    session, tenant_id=user.tenant_id, pipeline_item_id=pipelineId,
                )
                write_audit(
                    session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                    action="pipeline.run", object_type="pipeline_run", object_id=run.id,
                    payload={"pipelineItemId": pipelineId},
                )
                session.commit()
                run_pipeline_task.defer(run_id=run.id, tenant_id=user.tenant_id)
                return {"runId": run.id}

        @server.tool()
        async def explain_pipeline(ctx: Context, pipelineId: str) -> dict:
            """Describe a Pipeline's graph (nodes/ops/edges) without running
            it — mirrors explain_dataset's shape. Only registered when
            CORE_ETL_ENABLED is on. SP-15a."""
            access_token = get_access_token()
            with request_scoped_session(session_factory) as session:
                user = _resolve_actor(session, access_token)
                config = configs_repo.get_config_by_item(session, pipelineId)
                if config is None or config.config.kind != "pipeline":
                    raise ValueError("pipeline not found")
                item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=pipelineId)
                assert item is not None
                payload = config.config.pipeline
                assert payload is not None
                return {
                    "title": item.title,
                    "nodes": [
                        {"id": n.id, "kind": n.kind, "op": n.op, "title": n.title}
                        for n in payload.nodes
                    ],
                    "edges": [{"from": e.from_, "to": e.to} for e in payload.edges],
                }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_mcp_tools_pipeline.py -v`
Expected: PASS (2 tests green)

- [ ] **Step 5: Run the full MCP test suite to check no regression**

Run: `cd core && uv run pytest tests/test_mcp_read_only_mode.py tests/test_mcp_tools_dataset_create.py tests/test_mcp_tools_explain_dataset.py -v`
Expected: PASS (unchanged — `READ_ONLY_TOOLS` in `tools.py` is untouched,
`create_pipeline`/`run_pipeline` are deliberately NOT added to it: read-only
mode already blocks `create_pipeline` explicitly, and `run_pipeline` defers
a background job rather than mutating synchronously — same reasoning as why
`run_analytics_query` isn't in `READ_ONLY_TOOLS` either)

- [ ] **Step 6: Run the entire non-postgis suite one last time**

Run: `cd core && uv run pytest -v -k "not postgis"`
Expected: PASS (full green suite — this closes out SP-15a's headless socle)

- [ ] **Step 7: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_pipeline.py
git commit -m "feat(core): add create_pipeline/run_pipeline/explain_pipeline MCP tools"
```

---

## Post-plan note (not a task — do not execute as part of this plan)

Once all 11 tasks are merged and the `postgis`-marked tests in Tasks 8 and 9
have been run for real at least once (docker-compose Postgres or CI), update
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` and `CLAUDE.md`'s
"Fait"/"À venir" sections to record SP-15a as shipped — as a **separate
documentation commit**, per this workflow's own convention (see how SP-14l/
SP-14m's roadmap entries were added). Do not fold that documentation update
into any of the 11 code tasks above. SP-15's remaining phases (canvas,
spatial + `qgis_process` sidecar, automation/triggers) stay explicitly
unscheduled until a next sub-plan (SP-15b+) is written.
