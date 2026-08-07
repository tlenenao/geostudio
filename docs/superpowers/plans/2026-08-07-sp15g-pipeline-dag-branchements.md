# SP-15g — Canvas visuel DAG : branchements & fusion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the Pipeline runtime's "linear+join" topology to a true DAG — official fan-out support, a new arrow-based fan-in mechanism (`PipelineEdge.role="secondary"`) for `transform.join`/`intersection`/`countWithin` plus a new `transform.merge` op — and add two accompanying UX features: live per-node progress on the canvas during a run, and a map view alongside the existing tabular preview.

**Architecture:** Backend: `PipelineEdge` gains an optional `role` field; the compiler/runtime resolve a binary op's second input either from the existing `withCollectionId` param or from a `role="secondary"` edge (mutually exclusive, enforced at save time); a callback hook (`on_node_complete`) lets the procrastinate job commit `PipelineRun.node_stats` incrementally instead of only at the end. Frontend: React Flow canvas gains a second, visually distinct target handle for binary ops, dashed rendering for secondary edges, live progress badges/spinners sourced from the already-polled `PipelineRun`, and a MapLibre-based alternative to the tabular preview.

**Tech Stack:** Python/FastAPI/Pydantic/DuckDB/SQLAlchemy (`core/`), React/TypeScript/`@xyflow/react`/`maplibre-gl`/Vitest/Playwright (`shell/`).

## Global Constraints

- **Reference spec:** `docs/superpowers/specs/2026-08-07-sp15g-pipeline-dag-branchements-design.md` (read it first — this plan implements it verbatim).
- **Never more than 2 inputs per node** (`primary`+`secondary` at most) — no 3-way join/merge.
- **`edge.when` (CEL conditional routing) stays untouched** — accepted-but-uninterpreted, out of scope.
- **`transform.sql`** stays out of scope (deferred, "Phase 4" in the feasibility-study vocabulary).
- **No new MCP tool** — `create_pipeline`/`run_pipeline`/`explain_pipeline` already accept generic `nodes`/`edges`; `role` and `transform.merge` pass through unchanged.
- **No Alembic migration** — `Pipeline` is a JSON document (`BuilderConfig.pipeline`), all new fields are optional and backward-compatible.
- **Progress stays on the existing 1.5s poll** — no WebSocket.
- **Preserve exact existing error-message substrings** where tests assert on them (see Task 6 note on `"one incoming edge"`).
- Every new/changed Python file keeps the project's `# SPDX-License-Identifier: Apache-2.0` header line.
- `core` tests run with `cd core && uv run pytest`; `shell` unit tests with `cd shell && npm run test`; `shell` E2E with `cd shell && npm run e2e` (needs `VITE_AUTH_MODE=mock`).

---

## Task 1: Prove fan-out already works (runtime regression test)

Nothing in the schema, compiler, or runtime blocks a node from feeding more than one downstream node today — `predecessor_id` only ever counts *incoming* edges. This task adds the first explicit test for that behavior. No production code changes.

**Files:**
- Modify: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `app.pipelines.runtime.run_pipeline` (existing), `app.configs.schemas.PipelinePayload` (existing).
- Produces: nothing new — this is a pure regression test.

- [ ] **Step 1: Write the failing-if-broken test**

Add to `core/tests/test_pipeline_runtime.py` (end of file, after the last `reader.connector` test):

```python
@pytest.mark.postgis
def test_run_pipeline_fan_out_one_reader_feeds_two_writers(pg_engine, monkeypatch, tmp_path):
    """Régression SP-15g §1 : rien n'empêche aujourd'hui un nœud d'alimenter
    plusieurs nœuds avals (fan-out) — ce test en fait une capacité officielle,
    testée explicitement pour la première fois. Un seul reader.collection
    alimente deux writer.collection distincts (deux collections cibles)."""
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        for name in ("villes_out_a", "villes_out_b"):
            s.execute(text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, geometry_column, is_public, editable, "
                "created_at, updated_at) "
                f"VALUES ('{name}', :t, :o, '{name}', '{name}', "
                "'', 'id', 'geometry', false, true, now(), now())"
            ), {"t": tenant.id, "o": user.id})
            s.execute(text(
                f"CREATE TABLE {name} (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
            ))
            apply_collection_ddl(s, name)
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[
            _row(1, "Nord", 10, x=1.0, y=45.0), _row(2, "Sud", 5, x=2.0, y=46.0),
        ])

        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_out_a"}},
                {"id": "w2", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_out_b"}},
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "w1"},
                {"id": "e2", "from": "r1", "to": "w2"},
            ],
        })

        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        count_a = s.execute(text("SELECT count(*) FROM villes_out_a")).scalar()
        count_b = s.execute(text("SELECT count(*) FROM villes_out_b")).scalar()
        assert count_a == 2
        assert count_b == 2
        writer_stats = {stat.nodeId: stat.rowCount for stat in stats if stat.op == "writer.collection"}
        assert writer_stats == {"w1": 2, "w2": 2}

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out_a; DROP TABLE villes_out_b; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

- [ ] **Step 2: Run it (requires the `postgis` marker — a real Postgres, cf. `docker compose up -d postgis` or the project's test-Postgres recipe)**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py::test_run_pipeline_fan_out_one_reader_feeds_two_writers -v -m postgis`
Expected: PASS (no production code change was needed — this proves the claim).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_pipeline_runtime.py
git commit -m "test(core): prove pipeline fan-out (one node, two writers) already works"
```

---

## Task 2: `PipelineEdge.role`

**Files:**
- Modify: `core/app/configs/schemas.py:180-188`
- Modify: `core/tests/test_pipeline_config_schema.py`

**Interfaces:**
- Produces: `PipelineEdge.role: Literal["primary", "secondary"] | None` — consumed by Task 4 (compiler), Task 5 (runtime), Task 6 (structural validation), Task 7 (op validation).

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_pipeline_config_schema.py`:

```python
def test_pipeline_edge_role_defaults_to_none():
    edge = PipelineEdge(id="e1", **{"from": "a"}, to="b")
    assert edge.role is None


def test_pipeline_edge_accepts_secondary_role():
    edge = PipelineEdge(id="e1", **{"from": "a"}, to="b", role="secondary")
    assert edge.role == "secondary"


def test_pipeline_edge_rejects_unknown_role():
    with pytest.raises(ValidationError):
        PipelineEdge(id="e1", **{"from": "a"}, to="b", role="tertiary")
```

Check the top of the file already imports `PipelineEdge`, `pytest`, and `ValidationError` (from `pydantic`); if not, add:

```python
import pytest
from pydantic import ValidationError

from app.configs.schemas import PipelineEdge
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -k pipeline_edge_role -v`
Expected: FAIL with `TypeError` / `AttributeError` (no `role` field yet).

- [ ] **Step 3: Add the field**

In `core/app/configs/schemas.py`, replace the `PipelineEdge` class:

```python
class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None       # CEL, routage conditionnel — accepté mais non
                                   # interprété par le compilateur avant Phase 3/4
    role: Literal["primary", "secondary"] | None = None  # None ≡ "primary" ;
        # "secondary" = seconde entrée d'un op binaire (SP-15g §2.2), sans
        # effet sur tout autre op (rejeté à la validation, app.pipelines.
        # config_validation)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: PASS (all tests in the file, including the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_pipeline_config_schema.py
git commit -m "feat(core): pipelines — PipelineEdge.role for fan-in inputs"
```

---

## Task 3: Ops catalog — optional `withCollectionId`, `transform.merge`, `acceptsSecondaryInput`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py:43-46,67-77,158-211`
- Modify: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TransformMergeParams` (Pydantic model), `BINARY_OPS: set[str]` (importable as `from app.pipelines.ops.schemas import BINARY_OPS` — consumed by Task 7), `ops_catalog()` entries now carry `"acceptsSecondaryInput": bool`.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_pipeline_ops_schemas.py`:

```python
def test_transform_join_with_collection_id_is_now_optional():
    params = parse_op_params("transform.join", {"on": "code"})
    assert params.withCollectionId is None


def test_transform_intersection_with_collection_id_is_now_optional():
    params = parse_op_params("transform.intersection", {})
    assert params.withCollectionId is None


def test_transform_count_within_with_collection_id_is_now_optional():
    params = parse_op_params("transform.countWithin", {})
    assert params.withCollectionId is None


def test_transform_merge_accepts_no_params():
    params = parse_op_params("transform.merge", {})
    assert params.withCollectionId is None


def test_transform_merge_accepts_with_collection_id():
    params = parse_op_params("transform.merge", {"withCollectionId": "x"})
    assert params.withCollectionId == "x"


def test_transform_merge_is_kind_transform_and_registered():
    assert OP_KINDS["transform.merge"] == "transform"
    assert "transform.merge" in OP_PARAMS


def test_all_eighteen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "writer.dataset",
        "transform.qgis", "reader.connector.rest", "reader.connector.postgres",
        "transform.merge",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


def test_binary_ops_accept_secondary_input_in_catalog():
    catalog = ops_catalog()
    for op in ("transform.join", "transform.intersection", "transform.countWithin", "transform.merge"):
        assert catalog[op]["acceptsSecondaryInput"] is True


def test_non_binary_ops_do_not_accept_secondary_input_in_catalog():
    catalog = ops_catalog()
    for op in ("reader.collection", "transform.filter", "writer.collection", "transform.buffer"):
        assert catalog[op]["acceptsSecondaryInput"] is False


def test_binary_ops_set_matches_catalog_flag():
    from app.pipelines.ops.schemas import BINARY_OPS
    assert BINARY_OPS == {
        "transform.join", "transform.intersection", "transform.countWithin", "transform.merge",
    }
```

Note: this task **replaces** `test_all_seventeen_ops_are_registered` — the total is now 18. Delete the old `test_all_seventeen_ops_are_registered` function (its assertion set is a strict subset of the new `test_all_eighteen_ops_are_registered` minus `transform.merge`, so keeping both would be redundant, not contradictory — remove the old one to avoid two near-duplicate "list every op" tests drifting apart over time).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL (`transform.merge` unknown, `withCollectionId` still required, `acceptsSecondaryInput` KeyError, `BINARY_OPS` ImportError).

- [ ] **Step 3: Implement**

In `core/app/pipelines/ops/schemas.py`, replace the three existing classes (lines 43-46, 67-77) and add `TransformMergeParams` + `BINARY_OPS`:

```python
class TransformJoinParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"
```

```python
class TransformIntersectionParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    how: Literal["inner", "left"] = "inner"
    outputGeometry: Literal["left", "intersection"] = "left"


class TransformCountWithinParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    countColumn: str = "count"
    predicate: Literal["intersects", "contains"] = "intersects"


class TransformMergeParams(BaseModel):
    """Empile deux flux ligne à ligne (UNION ALL BY NAME, design SP-15g §3.2).
    Comme les 3 op binaires ci-dessus, sa seconde entrée vient soit de
    `withCollectionId` (collection brute), soit d'une arête `role="secondary"`
    (sortie déjà calculée d'une autre branche du pipeline) — jamais les deux à
    la fois, jamais ni l'un ni l'autre (app.pipelines.config_validation)."""
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
```

At the end of the file, after `OP_PARAMS` (before `parse_op_params`), add:

```python
# Op dont la seconde entrée peut venir soit de `withCollectionId`, soit d'une
# arête `role="secondary"` (design SP-15g §2.2/§4.2). Exporté (pas
# `_`-préfixé) : importé directement par app.pipelines.config_validation,
# même package app.pipelines, aucune frontière de couches à traverser.
BINARY_OPS = {
    "transform.join", "transform.intersection", "transform.countWithin", "transform.merge",
}
```

Update `OP_KINDS`/`OP_PARAMS` (add one line each, right after the `transform.join`/`transform.countWithin` entries respectively — exact position doesn't matter, dict order is not semantic here):

```python
OP_KINDS["transform.merge"] = "transform"
OP_PARAMS["transform.merge"] = TransformMergeParams
```

(Place these two lines directly after the existing `OP_KINDS = {...}` and `OP_PARAMS = {...}` dict literals, as separate assignment statements — simplest diff, no need to re-order the dict literals themselves.)

Update `ops_catalog()`:

```python
def ops_catalog() -> dict[str, dict]:
    return {
        op: {
            "kind": OP_KINDS[op],
            "paramsSchema": model.model_json_schema(),
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
        for op, model in OP_PARAMS.items()
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: PASS (all tests, including pre-existing ones — `test_transform_intersection_defaults`/`test_transform_count_within_defaults` still pass since they always pass `withCollectionId`, which remains a valid value for the now-optional field).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): pipelines — transform.merge op, optional withCollectionId on binary ops"
```

---

## Task 4: Compiler — `secondary_predecessor_id`, `transform.merge` SQL/SRID

**Files:**
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `TransformMergeParams` (Task 3), `PipelineEdge.role` (Task 2).
- Produces: `compiler.secondary_predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_pipeline_compiler.py`:

```python
def test_secondary_predecessor_id_returns_none_without_secondary_edge():
    edges = [_edge("e1", "r1", "t1")]
    assert compiler.secondary_predecessor_id("t1", edges) is None


def test_secondary_predecessor_id_returns_the_secondary_source():
    edges = [
        _edge("e1", "r1", "t1"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    assert compiler.secondary_predecessor_id("t1", edges) == "r2"


def test_secondary_predecessor_id_raises_on_multiple_secondary_edges():
    edges = [
        PipelineEdge(id="e1", **{"from": "r1"}, to="t1", role="secondary"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    with pytest.raises(ValueError, match="secondary incoming edge"):
        compiler.secondary_predecessor_id("t1", edges)


def test_predecessor_id_ignores_secondary_edges():
    # Un nœud binaire avec 1 arête primaire + 1 arête secondaire n'est PAS "2
    # arêtes entrantes" pour predecessor_id — seule secondary_predecessor_id
    # voit la seconde. predecessor_id doit continuer à ne compter que la
    # primaire, exactement comme si l'arête secondaire n'existait pas.
    edges = [
        _edge("e1", "r1", "t1"),
        PipelineEdge(id="e2", **{"from": "r2"}, to="t1", role="secondary"),
    ]
    assert predecessor_id("t1", edges) == "r1"


def test_compile_merge(conn):
    conn.execute("CREATE TABLE other (id INTEGER, pop INTEGER)")
    conn.execute("INSERT INTO other VALUES (10, 99)")
    sql = compile_transform_sql("transform.merge", {}, input_view="base", join_view="other")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, region, pop FROM out ORDER BY id").fetchall()
    assert rows == [(1, "Nord", 10), (2, "Sud", 5), (3, "Nord", 20), (10, None, 99)]


def test_compile_merge_without_join_view_raises():
    with pytest.raises(AssertionError):
        compile_transform_sql("transform.merge", {}, input_view="base")


def test_transform_output_srid_merge_raises_on_mismatch():
    with pytest.raises(ValueError, match="transform.reproject"):
        compiler.transform_output_srid(
            "transform.merge", {}, input_srid=4326, join_srid=3857,
        )


def test_transform_output_srid_merge_passes_on_match():
    srid = compiler.transform_output_srid(
        "transform.merge", {}, input_srid=4326, join_srid=4326,
    )
    assert srid == 4326
```

Add `PipelineEdge` to the existing import line if not already imported with that exact name (it already is, per the file's line 5: `from app.configs.schemas import PipelineEdge, PipelineNode`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: FAIL (`secondary_predecessor_id` doesn't exist; `transform.merge` unknown to `compile_transform_sql`/`transform_output_srid`).

- [ ] **Step 3: Implement**

In `core/app/pipelines/compiler.py`, replace `predecessor_id` (currently lines 48-55):

```python
def predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    incoming = [e.from_ for e in edges if e.to == node_id and e.role != "secondary"]
    if len(incoming) > 1:
        raise ValueError(
            f"node '{node_id}' has more than one incoming edge "
            "(linear+join topology only, SP-15a MVP)"
        )
    return incoming[0] if incoming else None


def secondary_predecessor_id(node_id: str, edges: list[PipelineEdge]) -> str | None:
    """Résout la seconde entrée (SP-15g §3.1) d'un op binaire — l'alternative
    additive à son paramètre `withCollectionId`. Ignoré pour tout autre op
    (une arête secondaire y est de toute façon rejetée à la sauvegarde,
    app.pipelines.config_validation)."""
    incoming = [e.from_ for e in edges if e.to == node_id and e.role == "secondary"]
    if len(incoming) > 1:
        raise ValueError(f"node '{node_id}' has more than one secondary incoming edge")
    return incoming[0] if incoming else None
```

Add the import for `TransformMergeParams` at the top import block (extend the existing `from app.pipelines.ops.schemas import (...)`):

```python
from app.pipelines.ops.schemas import (
    TransformAggregateParams, TransformBufferParams, TransformCountWithinParams,
    TransformDeriveParams, TransformFilterParams, TransformH3AggregateParams,
    TransformIntersectionParams, TransformJoinParams, TransformMergeParams, TransformQgisParams,
    TransformReprojectParams, TransformSelectParams,
)
```

In `compile_transform_sql`, add a new branch right before the final `raise ValueError(f"'{op}' is not a transform op")`:

```python
    if op == "transform.merge":
        TransformMergeParams.model_validate(params)  # forme seulement, aucun autre champ à lire
        assert join_view is not None, "transform.merge requires join_view"
        return (
            f"SELECT * FROM {_qi(input_view)} "
            f"UNION ALL BY NAME SELECT * FROM {_qi(join_view)}"
        )
```

In `transform_output_srid`, extend the existing tuple check (currently `if op in ("transform.intersection", "transform.countWithin"):`) to include `transform.merge`:

```python
    if op in ("transform.intersection", "transform.countWithin", "transform.merge"):
        assert join_srid is not None, f"{op} requires join_srid"
        if input_srid != join_srid:
            raise ValueError(
                f"'{op}': input CRS (EPSG:{input_srid}) and joined collection CRS "
                f"(EPSG:{join_srid}) differ — insert transform.reproject first"
            )
        return input_srid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -v`
Expected: PASS (all tests, including pre-existing ones — `predecessor_id`'s message/behavior for the no-secondary-edge case is byte-for-byte unchanged).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/compiler.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): pipelines — compiler support for transform.merge and secondary edges"
```

---

## Task 5: Runtime — resolve fan-in via secondary edge, add progress-callback plumbing point

This task wires the compiler primitives from Task 4 into `_prepare`/`_execute_transform_chain`. The `on_node_complete` callback signature is introduced here (threaded through, but not yet driven by `jobs.py` — that's Task 8) so `run_pipeline`'s public signature only changes once.

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `compiler.secondary_predecessor_id` (Task 4), `TransformMergeParams`/`BINARY_OPS`... (only `_JOIN_PARAM_MODELS`, a runtime-local dict, needs a new entry — no need to import `BINARY_OPS` here).
- Produces: `run_pipeline(..., on_node_complete: Callable[[NodeStat], None] | None = None)`, `_execute_transform_chain(..., on_node_complete=None)` — consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_pipeline_runtime.py`:

```python
def test_preview_merge_via_secondary_edge(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="a", rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
    _write_partition(tmp_path, collection_id="b", rows=[_row(2, "Sud", 5, x=2.0, y=46.0)])
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
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "a"}},
            {"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "b"}},
            {"id": "t1", "kind": "transform", "op": "transform.merge", "params": {}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"},
            {"id": "e2", "from": "r2", "to": "t1", "role": "secondary"},
            {"id": "e3", "from": "t1", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path),
    )
    assert {r["id"] for r in rows} == {1, 2}


def test_preview_join_via_secondary_edge_matches_with_collection_id(tmp_path, monkeypatch):
    # Régression : transform.join via arête secondaire doit produire le même
    # résultat que le chemin withCollectionId existant, pour la même donnée.
    _write_partition(tmp_path, collection_id="base", rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
    _write_partition(tmp_path, collection_id="labels", rows=[_row(1, "x", 0, x=9.0, y=9.0)])
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
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "base"}},
            {"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "labels"}},
            {"id": "t1", "kind": "transform", "op": "transform.join", "params": {"on": "id"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"},
            {"id": "e2", "from": "r2", "to": "t1", "role": "secondary"},
            {"id": "e3", "from": "t1", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path),
    )
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["region"] == "Nord"  # from r1 — proves the join actually matched on id=1


def test_execute_transform_chain_invokes_on_node_complete_per_node(tmp_path, monkeypatch):
    _write_partition(tmp_path, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "1=1"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })
    seen: list[str] = []

    conn = runtime.open_connection(endpoint_url="http://localhost:9000", access_key="x", secret_key="y")
    ordered, view_by_node, srid_by_node, join_srid_by_node = runtime._prepare(
        conn, None, payload, tenant_id="t1", user=None, base_uri=str(tmp_path),
    )
    runtime._execute_transform_chain(
        conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
        on_node_complete=lambda stat: seen.append(stat.nodeId),
    )
    assert seen == ["r1", "t1"]  # writer node (w1) is handled by run_pipeline, not this function
```

Also add a `join_srid_by_node` fixture/helper isn't needed (already covered by existing `_table_info_srid` used above).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k "secondary_edge or on_node_complete" -v`
Expected: FAIL (`transform.merge`/secondary-edge joins raise/behave as if the second input were missing; `on_node_complete` kwarg not accepted).

- [ ] **Step 3: Implement**

In `core/app/pipelines/runtime.py`:

Add `Callable` import (top of file, alongside the existing `import` block):

```python
from collections.abc import Callable
```

Extend `_JOIN_PARAM_MODELS` (currently lines 61-65):

```python
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, ReaderConnectorPostgresParams, ReaderConnectorRestParams,
    TransformAggregateParams, TransformCountWithinParams, TransformDeriveParams,
    TransformFilterParams, TransformH3AggregateParams, TransformIntersectionParams,
    TransformJoinParams, TransformMergeParams, TransformQgisParams, WriterCollectionParams,
    WriterDatasetParams, WriterExportParams,
)
from app.sharing.authorization import can
from app.users.models import User

_JOIN_PARAM_MODELS: dict[str, type] = {
    "transform.join": TransformJoinParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.merge": TransformMergeParams,
}
```

In `_prepare`, the second loop (materializing the `withCollectionId` join view — currently lines 232-247) gains a guard for the secondary-edge case:

```python
    join_srid_by_node: dict[str, int] = {}
    for node in ordered:
        model = _JOIN_PARAM_MODELS.get(node.op)
        if model is None:
            continue
        if compiler.secondary_predecessor_id(node.id, payload.edges) is not None:
            # La seconde entrée vient d'un nœud du pipeline déjà (ou bientôt)
            # matérialisé par le reste de l'exécution — rien à matérialiser
            # ici (design SP-15g §3.3).
            continue
        p = model.model_validate(node.params)
        if p.withCollectionId is None:
            raise PipelineRuntimeError(
                f"'{node.op}': requires either 'withCollectionId' or a secondary input edge"
            )
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
```

In `_execute_transform_chain`, change the signature and the join-view/join-srid resolution:

```python
def _execute_transform_chain(
    conn, ordered: list[PipelineNode], edges, view_by_node: dict[str, str],
    srid_by_node: dict[str, int], join_srid_by_node: dict[str, int],
    *, stop_at: str | None = None, qgis_worker_url: str = "",
    qgis_worker_timeout_seconds: int = 600,
    on_node_complete: Callable[["NodeStat"], None] | None = None,
) -> list["NodeStat"]:
    stats: list[NodeStat] = []
    scratch_run_id = uuid.uuid4().hex
    for node in ordered:
        if node.kind == "reader":
            stat = NodeStat(node.id, node.op, _view_row_count(conn, view_by_node[node.id]))
            stats.append(stat)
            if on_node_complete is not None:
                on_node_complete(stat)
            if stop_at == node.id:
                return stats
            continue
        if node.kind != "transform":
            break  # writer nodes are handled by the caller, not here
        pred_id = compiler.predecessor_id(node.id, edges)
        assert pred_id is not None
        input_view = view_by_node[pred_id]
        input_srid = srid_by_node[pred_id]
        join_view = None
        join_srid = None
        if node.op in _JOIN_PARAM_MODELS:
            secondary_pred = compiler.secondary_predecessor_id(node.id, edges)
            if secondary_pred is not None:
                join_view = view_by_node[secondary_pred]
                join_srid = srid_by_node[secondary_pred]
            else:
                join_view = f"node_{node.id}__join"
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
        stat = NodeStat(node.id, node.op, _view_row_count(conn, view_name))
        stats.append(stat)
        if on_node_complete is not None:
            on_node_complete(stat)
        if stop_at == node.id:
            return stats
    return stats
```

In `run_pipeline`, thread the new parameter through the call to `_execute_transform_chain` and call the callback after each writer:

```python
def run_pipeline(
    session: Session, *, payload: PipelinePayload, tenant_id: str, user: User,
    endpoint_url: str, access_key: str, secret_key: str, base_uri: str,
    s3_client=None, exports_bucket: str | None = None,
    qgis_worker_url: str = "", qgis_worker_timeout_seconds: int = 600,
    on_node_complete: Callable[["NodeStat"], None] | None = None,
) -> list[NodeStat]:
    conn = open_connection(endpoint_url=endpoint_url, access_key=access_key, secret_key=secret_key)
    try:
        ordered, view_by_node, srid_by_node, join_srid_by_node = _prepare(
            conn, session, payload, tenant_id=tenant_id, user=user, base_uri=base_uri,
        )
        stats = _execute_transform_chain(
            conn, ordered, payload.edges, view_by_node, srid_by_node, join_srid_by_node,
            qgis_worker_url=qgis_worker_url, qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
            on_node_complete=on_node_complete,
        )
        for node in ordered:
            if node.kind != "writer":
                continue
            pred_id = compiler.predecessor_id(node.id, payload.edges)
            assert pred_id is not None
            view_by_node[node.id] = view_by_node[pred_id]
            if node.op == "writer.collection":
                stat = _write_collection(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                )
            elif node.op == "writer.export":
                assert s3_client is not None and exports_bucket is not None
                stat = _write_export(conn, s3_client, exports_bucket, node=node, view_by_node=view_by_node)
            elif node.op == "writer.dataset":
                stat = _write_dataset(
                    session, conn, node=node, view_by_node=view_by_node, tenant_id=tenant_id, user=user,
                )
            stats.append(stat)
            if on_node_complete is not None:
                on_node_complete(stat)
        return stats
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: PASS (all tests in the file, including every pre-existing `withCollectionId`-based join/intersection/countWithin test — unaffected, since `secondary_predecessor_id` returns `None` for all of them and the `else` branch is byte-identical to the old code).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py
git commit -m "feat(core): pipelines — runtime resolves binary-op second input from secondary edges"
```

---

## Task 6: Structural validation — role-aware `_check_topology`

**Files:**
- Modify: `core/app/configs/pipeline_validation.py`
- Modify: `core/tests/test_pipeline_config_validation.py`

**Interfaces:**
- Consumes: `PipelineEdge.role` (Task 2).
- Produces: `_check_topology` (renamed from `_check_linear_topology`) — internal to the module, not consumed elsewhere. `NodeValidator` type alias widened — consumed by Task 7.

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_pipeline_config_validation.py`:

```python
def test_node_with_two_secondary_incoming_edges_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"] += [
        {"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "quartiers"}},
        {"id": "r3", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "quartiers2"}},
    ]
    body["config"]["pipeline"]["edges"] += [
        {"id": "e2", "from": "r2", "to": "w1", "role": "secondary"},
        {"id": "e3", "from": "r3", "to": "w1", "role": "secondary"},
    ]
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "one secondary incoming edge" in response.json()["detail"]


def test_node_with_one_primary_and_one_secondary_incoming_edge_is_not_a_topology_error(env):
    # Régression : ce n'est PAS "2 arêtes entrantes" au sens de la garde de
    # topologie (une primaire + une secondaire est la forme normale d'un op
    # binaire) — la sauvegarde peut échouer pour une AUTRE raison (op non
    # binaire, Task 7), mais jamais sur _check_topology elle-même.
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "quartiers"}}
    )
    body["config"]["pipeline"]["edges"].append(
        {"id": "e2", "from": "r2", "to": "w1", "role": "secondary"}
    )
    response = env.post("/configs", json=body)
    # w1 est writer.collection (pas un op binaire) : Task 7 le rejette, mais
    # PAS avec le message de _check_topology — on vérifie juste l'absence de
    # "one secondary incoming edge" / "one incoming edge" ici, la garde de
    # forme (Task 7) est testée séparément dans test_pipeline_node_validation.py.
    assert "incoming edge" not in response.json().get("detail", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -k secondary_incoming -v`
Expected: FAIL — the second test in particular will currently report `422` with `"has more than one incoming edge"` because today's `_check_linear_topology` counts *all* incoming edges regardless of role.

- [ ] **Step 3: Implement**

In `core/app/configs/pipeline_validation.py`, replace `_check_linear_topology`:

```python
def _check_topology(edges: list[PipelineEdge]) -> None:
    primary_count: dict[str, int] = {}
    secondary_count: dict[str, int] = {}
    for edge in edges:
        bucket = secondary_count if edge.role == "secondary" else primary_count
        bucket[edge.to] = bucket.get(edge.to, 0) + 1
    for node_id, count in primary_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one incoming edge "
                       "(linear+join topology only, SP-15a MVP)",
            )
    for node_id, count in secondary_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one secondary incoming edge",
            )
```

Update the two call sites in the same file:

1. `validate_pipeline_payload`: replace `_check_linear_topology(payload.edges)` with `_check_topology(payload.edges)`.
2. `NodeValidator` type alias: replace

```python
NodeValidator = Callable[[Session, PipelineNode, User], None]
```

with

```python
NodeValidator = Callable[[Session, PipelineNode, list[PipelineEdge], User], None]
```

3. In `validate_pipeline_payload`'s per-node loop, replace `validator(session, node, user)` with `validator(session, node, payload.edges, user)`.

- [ ] **Step 4: Fix the now-outdated fake validators in the test fixture**

In `core/tests/test_pipeline_config_validation.py`'s `env` fixture, the two `monkeypatch.setitem` calls register 3-argument fakes — update both to 4 arguments (the call site now passes `edges` too):

```python
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "reader.collection",
        lambda session, node, edges, user: None,
    )
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "writer.collection",
        lambda session, node, edges, user: None,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: PASS (all tests — `test_node_with_two_incoming_edges_rejected`'s `"one incoming edge" in detail` assertion still passes unchanged, since the primary-count message text is preserved verbatim).

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/pipeline_validation.py core/tests/test_pipeline_config_validation.py
git commit -m "feat(core): pipelines — role-aware topology check (primary vs secondary incoming edges)"
```

---

## Task 7: Op-level validation — XOR `withCollectionId` / secondary edge

**Files:**
- Modify: `core/app/pipelines/config_validation.py`
- Modify: `core/tests/test_pipeline_node_validation.py`

**Interfaces:**
- Consumes: `BINARY_OPS` (Task 3), `NodeValidator` widened signature (Task 6).
- Produces: nothing new consumed elsewhere — this is the leaf of the validation chain.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_pipeline_node_validation.py`:

```python
def _pipeline_body_binary_op(op: str, params: dict, edges_extra: list[dict] | None = None,
                              nodes_extra: list[dict] | None = None) -> dict:
    nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
        {"id": "t1", "kind": "transform", "op": op, "params": params},
        {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "writable"}},
    ]
    edges = [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}]
    if nodes_extra:
        nodes += nodes_extra
    if edges_extra:
        edges += edges_extra
    return {
        "title": "P",
        "config": {"version": 1, "kind": "pipeline", "pipeline": {"nodes": nodes, "edges": edges}},
    }


def test_transform_merge_with_neither_collection_id_nor_secondary_edge_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body_binary_op("transform.merge", {}))
    assert response.status_code == 422
    assert "requires either" in response.json()["detail"]


def test_transform_merge_with_both_collection_id_and_secondary_edge_is_rejected(env):
    body = _pipeline_body_binary_op(
        "transform.merge", {"withCollectionId": "readable"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "cannot have both" in response.json()["detail"]


def test_transform_merge_via_secondary_edge_saves(env):
    body = _pipeline_body_binary_op(
        "transform.merge", {},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 201


def test_non_binary_op_with_secondary_edge_is_rejected(env):
    body = _pipeline_body_binary_op(
        "transform.filter", {"expr": "1=1"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "does not accept a secondary input edge" in response.json()["detail"]


def test_transform_join_with_only_secondary_edge_and_no_collection_id_saves(env):
    body = _pipeline_body_binary_op(
        "transform.join", {"on": "id"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -k "secondary_edge or transform_merge" -v`
Expected: FAIL (`transform.merge` params currently reject an empty `{}` params dict? No — `withCollectionId` is now optional per Task 3, so `{}` is a *valid* `TransformMergeParams`; the XOR check itself doesn't exist yet, so all of these currently either 201 when they should 422, or vice-versa).

- [ ] **Step 3: Implement**

In `core/app/pipelines/config_validation.py`, add the import and rewrite `_validate_node`:

```python
from app.pipelines.ops.schemas import BINARY_OPS, OP_PARAMS
```

(add `BINARY_OPS` to the existing `from app.pipelines.ops.schemas import OP_PARAMS` import line)

```python
def _validate_node(session: Session, node: PipelineNode, edges: list, user: User) -> None:
    params = _validate_params(node)
    field = _COLLECTION_PARAM_FIELD.get(node.op)
    has_secondary_edge = any(e.to == node.id and e.role == "secondary" for e in edges)

    if node.op in BINARY_OPS:
        collection_id = getattr(params, field)
        if has_secondary_edge and collection_id is not None:
            raise HTTPException(
                status_code=422,
                detail=f"{node.op}: cannot have both '{field}' and a secondary input edge",
            )
        if not has_secondary_edge and collection_id is None:
            raise HTTPException(
                status_code=422,
                detail=f"{node.op}: requires either '{field}' or a secondary input edge",
            )
        if collection_id is not None:
            _require_readable_collection(session, user=user, collection_id=collection_id)
        return

    if has_secondary_edge:
        raise HTTPException(
            status_code=422,
            detail=f"{node.op}: does not accept a secondary input edge",
        )

    if field is None:
        return
    collection_id = getattr(params, field)
    if node.op in _WRITE_OPS:
        _require_writable_collection(session, user=user, collection_id=collection_id)
    else:
        _require_readable_collection(session, user=user, collection_id=collection_id)
```

Add `"transform.merge": "withCollectionId"` to the existing `_COLLECTION_PARAM_FIELD` dict:

```python
_COLLECTION_PARAM_FIELD = {
    "reader.collection": "collectionId",
    "transform.join": "withCollectionId",
    "transform.intersection": "withCollectionId",
    "transform.countWithin": "withCollectionId",
    "transform.merge": "withCollectionId",
    "writer.collection": "collectionId",
    "writer.dataset": "collectionId",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py tests/test_pipeline_config_validation.py -v`
Expected: PASS (all tests, including pre-existing `test_transform_intersection_with_collection_missing_is_rejected` and `test_transform_count_within_with_collection_readable_saves`, both of which always pass a `withCollectionId`, never a secondary edge — unaffected by the new branch).

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/config_validation.py core/tests/test_pipeline_node_validation.py
git commit -m "feat(core): pipelines — XOR validation of withCollectionId vs secondary edge for binary ops"
```

---

## Task 8: Progress callback — `append_node_stat` + `jobs.py` wiring

**Files:**
- Modify: `core/app/pipelines/repository.py`
- Modify: `core/app/pipelines/jobs.py`
- Modify: `core/tests/test_pipeline_repository.py`
- Modify: `core/tests/test_pipeline_jobs.py`

**Interfaces:**
- Consumes: `run_pipeline(..., on_node_complete=...)` (Task 5).
- Produces: `pipelines_repo.append_node_stat(session, *, tenant_id, run_id, node_id, stat)` — internal, not consumed by other tasks in this plan.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_pipeline_repository.py`:

```python
def test_append_node_stat_merges_into_existing_node_stats():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()

        repo.append_node_stat(
            s, tenant_id=tenant.id, run_id=run.id, node_id="r1",
            stat={"nodeId": "r1", "op": "reader.collection", "rowCount": 3},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {"r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 3}}

        repo.append_node_stat(
            s, tenant_id=tenant.id, run_id=run.id, node_id="w1",
            stat={"nodeId": "w1", "op": "writer.collection", "rowCount": 3},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {
            "r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 3},
            "w1": {"nodeId": "w1", "op": "writer.collection", "rowCount": 3},
        }


def test_append_node_stat_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        repo.append_node_stat(
            s, tenant_id="other-tenant", run_id=run.id, node_id="r1", stat={"rowCount": 1},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {}
```

Add to `core/tests/test_pipeline_jobs.py` (needs the `env` fixture already in the file):

```python
def test_run_pipeline_task_writes_node_stats_incrementally_before_failure(env, monkeypatch):
    """Régression du callback de progression (SP-15g §3.5) : node_stats doit
    être visible en base dès qu'un nœud se termine, pas seulement au dernier
    commit de mark_succeeded/mark_failed. Prouvé en faisant échouer le run
    APRÈS que le callback ait déjà écrit un NodeStat — si l'écriture était
    différée à la fin, ce test ne verrait rien avant le statut 'failed'."""
    app, Session, tenant, user, item_id = env
    from app.pipelines.runtime import NodeStat

    def _fake_run_pipeline(session, *, on_node_complete, **kwargs):
        on_node_complete(NodeStat("r1", "reader.collection", 5))
        raise ValueError("boom after first node")

    monkeypatch.setattr(pipeline_jobs, "run_pipeline", _fake_run_pipeline)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.node_stats == {"r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 5}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py -k append_node_stat -v`
Expected: FAIL (`AttributeError: module 'app.pipelines.repository' has no attribute 'append_node_stat'`).

Run: `cd core && uv run pytest tests/test_pipeline_jobs.py -k incrementally -v -m postgis`
Expected: FAIL (`run_pipeline_task` never passes `on_node_complete`, so `_fake_run_pipeline`'s keyword-only param raises `TypeError`).

- [ ] **Step 3: Implement `append_node_stat`**

In `core/app/pipelines/repository.py`, add after `mark_failed`:

```python
def append_node_stat(session: Session, *, tenant_id: str, run_id: str, node_id: str, stat: dict) -> None:
    """Écrit un NodeStat dans PipelineRun.node_stats immédiatement (fusion,
    pas un remplacement) — c'est ce qui permet à la progression d'un run
    d'être visible en base avant sa fin (SP-15g §3.5). Scindé de
    mark_succeeded (qui réécrit node_stats en entier, idempotent) : cette
    fonction est appelée une fois PAR NŒUD, sur sa propre transaction courte
    (jobs.py::_make_progress_callback), jamais dans la même transaction que
    le reste du run."""
    run = session.execute(
        select(PipelineRun).where(PipelineRun.id == run_id, PipelineRun.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if run is None:
        return
    run.node_stats = {**run.node_stats, node_id: stat}
    session.flush()
```

- [ ] **Step 4: Wire the callback in `jobs.py`**

In `core/app/pipelines/jobs.py`, add the import and helper, then pass it to `run_pipeline`:

```python
import logging
import os
from collections.abc import Callable

from app.configs import repository as configs_repo
from app.configs.schemas import PipelinePayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.jobs import app
from app.pipelines import repository as pipelines_repo
from app.pipelines.runtime import NodeStat, PipelineRuntimeError, run_pipeline
from app.users.models import User
```

Add, right before `run_pipeline_task`:

```python
def _make_progress_callback(
    session_factory, *, run_id: str, tenant_id: str,
) -> Callable[[NodeStat], None]:
    def _on_node_complete(stat: NodeStat) -> None:
        with request_scoped_session(session_factory) as s:
            pipelines_repo.append_node_stat(
                s, tenant_id=tenant_id, run_id=run_id, node_id=stat.nodeId, stat=stat.to_dict(),
            )
    return _on_node_complete
```

In `run_pipeline_task`, add `on_node_complete=_make_progress_callback(session_factory, run_id=run_id, tenant_id=tenant_id),` to the existing `run_pipeline(...)` call (right after `qgis_worker_timeout_seconds=...`):

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
                on_node_complete=_make_progress_callback(session_factory, run_id=run_id, tenant_id=tenant_id),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_repository.py tests/test_pipeline_jobs.py -v -m postgis`
Expected: PASS (all tests, including the pre-existing `test_run_pipeline_task_marks_run_succeeded` — unaffected, `on_node_complete` is additive).

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/repository.py core/app/pipelines/jobs.py core/tests/test_pipeline_repository.py core/tests/test_pipeline_jobs.py
git commit -m "feat(core): pipelines — incremental node_stats via on_node_complete callback"
```

---

## Task 9: Routes — ops-catalog count update

**Files:**
- Modify: `core/tests/test_pipeline_routes.py`

**Interfaces:**
- Consumes: `ops_catalog()` output (Task 3).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test change**

In `core/tests/test_pipeline_routes.py`, update `test_get_pipelines_ops_returns_all_seventeen`:

```python
def test_get_pipelines_ops_returns_all_eighteen(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops")
    assert response.status_code == 200
    body = response.json()
    # Phase 1 (8) + spatial (5) + writer.dataset (1) + qgis (1) + connectors (2)
    # + transform.merge (1, SP-15g) = 18 total.
    assert set(body) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "transform.qgis",
        "writer.collection", "writer.export", "writer.dataset",
        "reader.connector.rest", "reader.connector.postgres", "transform.merge",
    }
    for op in ("transform.join", "transform.intersection", "transform.countWithin", "transform.merge"):
        assert body[op]["acceptsSecondaryInput"] is True
    assert body["reader.collection"]["acceptsSecondaryInput"] is False
```

(Rename the test — `test_get_pipelines_ops_returns_all_seventeen` → `_all_eighteen` — and add the two new assertion blocks.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -v`
Expected: FAIL (missing `"transform.merge"` from the set, `KeyError: 'acceptsSecondaryInput'` if Task 3 weren't already merged — should already pass at this point in sequence since Task 3 ran earlier; this step is a final cross-check that the route surfaces it correctly end-to-end).

- [ ] **Step 3: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Full core suite check**

Run: `cd core && uv run pytest -q`
Expected: PASS (606+ tests, minus the ~87 `postgis`/`qgis`-marked ones if no docker available locally — same baseline as before this plan).

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_pipeline_routes.py
git commit -m "test(core): pipelines — ops-catalog route reflects transform.merge and acceptsSecondaryInput"
```

---

## Task 10: Shell types — `role`, `acceptsSecondaryInput`, typed `nodeStats`

**Files:**
- Modify: `shell/src/api/types.ts:434-478`

**Interfaces:**
- Produces: `PipelineEdge.role?`, `PipelineOpEntry.acceptsSecondaryInput?`, `PipelineNodeStat` type, `PipelineRun.nodeStats: Record<string, PipelineNodeStat>` — consumed by Tasks 11-17.

- [ ] **Step 1: Implement (no test — pure type change, verified by `tsc` in Step 2)**

In `shell/src/api/types.ts`, replace lines 434-478:

```typescript
export type PipelineEdge = {
  id: string;
  from: string;
  to: string;
  when?: string | null;
  role?: "primary" | "secondary" | null;
};

export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
};

// Minimal typed subset of JSON Schema actually consumed by
// PipelineNodeInspector (builder/pipeline/PipelineNodeInspector.tsx) — not a
// general JSON Schema type, deliberately narrow to what
// core/app/pipelines/ops/schemas.py's model_json_schema() output is used for.
export type PipelineOpParamProperty = {
  type?: "string" | "number" | "integer" | "boolean" | "array" | "object";
  format?: string;
  enum?: string[];
  default?: unknown;
  items?: { type?: string };
};

export type PipelineOpEntry = {
  kind: PipelineNodeKind;
  paramsSchema: {
    properties: Record<string, PipelineOpParamProperty>;
    required?: string[];
  };
  acceptsSecondaryInput?: boolean;
};

export type PipelineOpsCatalog = Record<string, PipelineOpEntry>;

export type PipelineRunStatus = "queued" | "running" | "succeeded" | "failed";

export type PipelineNodeStat = { nodeId: string; op: string; rowCount: number | null };

export type PipelineRun = {
  id: string;
  status: PipelineRunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  nodeStats: Record<string, PipelineNodeStat>;
};
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: may show pre-existing type errors in files this plan hasn't touched yet (Tasks 11-17 fix those) — but must NOT show new errors caused purely by this type change being *more permissive* than before (all changed fields are additive/optional). If it does show new errors here, they will be resolved by the subsequent tasks; do not attempt to fix unrelated files in this task.

- [ ] **Step 3: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): pipelines — types for edge role, acceptsSecondaryInput, typed node stats"
```

---

## Task 11: `graphOps.ts` — role-aware `hasIncomingEdge`, `insertNodeOnEdge`, new `topologicalOrder`

**Files:**
- Modify: `shell/src/builder/pipeline/graphOps.ts`
- Modify: `shell/src/builder/pipeline/graphOps.test.ts`

**Interfaces:**
- Consumes: `PipelineEdge.role` (Task 10).
- Produces: `hasIncomingEdge(edges, nodeId, role?)`, `topologicalOrder(nodes, edges): string[]` — both consumed by Task 13/14 (`PipelineCanvas.tsx`).

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/builder/pipeline/graphOps.test.ts`:

```typescript
test("hasIncomingEdge defaults to checking for a primary (non-secondary) edge", () => {
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1", role: "secondary" }];
  expect(hasIncomingEdge(edges, "w1")).toBe(false); // only a secondary edge exists, not a primary one
  expect(hasIncomingEdge(edges, "w1", "secondary")).toBe(true);
});

test("hasIncomingEdge distinguishes primary from secondary explicitly", () => {
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
  ];
  expect(hasIncomingEdge(edges, "t1", "primary")).toBe(true);
  expect(hasIncomingEdge(edges, "t1", "secondary")).toBe(true);
});

test("insertNodeOnEdge preserves the original edge's role on the downstream half", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.join", x: 200, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "t1", role: "secondary" }];
  const newNode: PipelineNode = { id: "f1", kind: "transform", op: "transform.filter", x: 100, y: 0, params: {} };

  const result = insertNodeOnEdge(nodes, edges, "e1", newNode);

  const upstream = result.edges.find((e) => e.from === "r1");
  const downstream = result.edges.find((e) => e.from === "f1");
  expect(upstream?.role).toBeUndefined();
  expect(downstream?.role).toBe("secondary");
});

test("topologicalOrder returns nodes in a valid dependency order", () => {
  const nodes: PipelineNode[] = [
    { id: "w1", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "t1", to: "w1" },
  ];
  expect(topologicalOrder(nodes, edges)).toEqual(["r1", "t1", "w1"]);
});

test("topologicalOrder handles fan-out and fan-in deterministically (sorted ties)", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "r2", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.merge", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
  ];
  expect(topologicalOrder(nodes, edges)).toEqual(["r1", "r2", "t1"]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/graphOps.test.ts`
Expected: FAIL (`topologicalOrder` doesn't exist; `hasIncomingEdge` doesn't accept a third argument; role isn't preserved by `insertNodeOnEdge`).

- [ ] **Step 3: Implement**

In `shell/src/builder/pipeline/graphOps.ts`, replace `hasIncomingEdge`:

```typescript
export function hasIncomingEdge(
  edges: PipelineEdge[], nodeId: string, role: "primary" | "secondary" = "primary",
): boolean {
  return edges.some((e) => {
    if (e.to !== nodeId) return false;
    return role === "secondary" ? e.role === "secondary" : e.role !== "secondary";
  });
}
```

Replace `insertNodeOnEdge`:

```typescript
export function insertNodeOnEdge(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  edgeId: string,
  newNode: PipelineNode,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const edge = edges.find((e) => e.id === edgeId);
  if (!edge) return { nodes, edges };
  const rest = edges.filter((e) => e.id !== edgeId);
  const downstream: PipelineEdge = { id: genEdgeId(), from: newNode.id, to: edge.to };
  if (edge.role) downstream.role = edge.role;
  return {
    nodes: [...nodes, newNode],
    edges: [...rest, { id: genEdgeId(), from: edge.from, to: newNode.id }, downstream],
  };
}
```

Add, at the end of the file:

```typescript
// Miroir client de app/pipelines/compiler.py::topological_order (SP-15a) —
// même algorithme de Kahn, tri déterministe des ids à chaque étape pour que
// le "prochain nœud" affiché pendant une exécution (PipelineCanvas, SP-15g
// §5.2) corresponde à l'ordre réel du runtime. Ne lève jamais sur un cycle
// (contrairement à la version serveur) : un pipeline sauvegardé est déjà
// garanti acyclique (validation serveur) au moment où ce calcul sert
// uniquement d'heuristique d'affichage.
export function topologicalOrder(nodes: PipelineNode[], edges: PipelineEdge[]): string[] {
  const indegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    adjacency.get(e.from)?.push(e.to);
    indegree.set(e.to, (indegree.get(e.to) ?? 0) + 1);
  }
  let queue = nodes.filter((n) => indegree.get(n.id) === 0).map((n) => n.id).sort();
  const ordered: string[] = [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    ordered.push(current);
    const newlyReady: string[] = [];
    for (const neighbor of adjacency.get(current) ?? []) {
      indegree.set(neighbor, (indegree.get(neighbor) ?? 0) - 1);
      if (indegree.get(neighbor) === 0) newlyReady.push(neighbor);
    }
    queue = [...queue, ...newlyReady].sort();
  }
  return ordered;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/graphOps.test.ts`
Expected: PASS (all tests, including pre-existing ones — the 2-arg `hasIncomingEdge(edges, "w1")` call from the pre-existing test still resolves to the `role="primary"` default, unchanged behavior for edges without a role).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/graphOps.ts shell/src/builder/pipeline/graphOps.test.ts
git commit -m "feat(shell): pipelines — role-aware graph ops + client-side topological order"
```

---

## Task 12: `validation.ts` — role-aware structural checks + binary-op XOR

**Files:**
- Modify: `shell/src/builder/pipeline/validation.ts`
- Modify: `shell/src/builder/pipeline/validation.test.ts`

**Interfaces:**
- Consumes: `PipelineEdge.role`, `PipelineOpEntry.acceptsSecondaryInput` (Task 10).
- Produces: nothing new consumed elsewhere — leaf of the client validation chain, wired into `PipelineBuilderPage` (already, unchanged call site).

- [ ] **Step 1: Write the failing tests**

Add a binary-op entry to the existing `CATALOG` constant in `shell/src/builder/pipeline/validation.test.ts` (it's optional-field-safe, doesn't affect existing tests):

```typescript
const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.join": {
    kind: "transform",
    paramsSchema: { properties: { withCollectionId: { type: "string", format: "collection-id" }, on: { type: "string" } }, required: ["on"] },
    acceptsSecondaryInput: true,
  },
};
```

Add new tests:

```typescript
function joinNode(id: string, params: Record<string, unknown> = { on: "id" }): PipelineNode {
  return { id, kind: "transform", op: "transform.join", x: 0, y: 0, params };
}

test("a node with two secondary incoming edges is invalid", () => {
  const nodes = [reader("r1"), reader("r2"), reader("r3"), joinNode("t1"), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
    { id: "e3", from: "r3", to: "t1", role: "secondary" },
    { id: "e4", from: "t1", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toContain("Un nœud ne peut avoir qu'une seule arête secondaire entrante (t1).");
});

test("a binary op with neither withCollectionId nor a secondary edge is flagged on that node", () => {
  const nodes = [reader("r1"), joinNode("t1", { on: "id" }), writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "t1" }, { id: "e2", from: "t1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.t1).toContain("transform.join : requiert soit withCollectionId, soit une arête secondaire.");
});

test("a binary op with both withCollectionId and a secondary edge is flagged on that node", () => {
  const nodes = [reader("r1"), reader("r2"), joinNode("t1", { on: "id", withCollectionId: "villes" }), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
    { id: "e3", from: "t1", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.t1).toContain("transform.join : withCollectionId et une arête secondaire ne peuvent pas être renseignés en même temps.");
});

test("a binary op with only a secondary edge (no withCollectionId) is valid", () => {
  const nodes = [reader("r1"), reader("r2"), joinNode("t1", { on: "id" }), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
    { id: "e3", from: "t1", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.t1).toEqual([]);
});

test("a non-binary op with a secondary edge is flagged on that node", () => {
  const nodes = [reader("r1"), reader("r2"), { ...reader("t1"), kind: "transform" as const, op: "transform.filter", params: { expr: "1=1" } }, writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
    { id: "e3", from: "t1", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.t1).toContain("transform.filter n'accepte pas d'arête secondaire.");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/validation.test.ts`
Expected: FAIL (secondary-edge counting and the XOR/rejection messages don't exist yet).

- [ ] **Step 3: Implement**

In `shell/src/builder/pipeline/validation.ts`, replace `validatePipelineGraphLocally`:

```typescript
export function validatePipelineGraphLocally(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  opsCatalog: PipelineOpsCatalog,
): PipelineValidationResult {
  const graphErrors: string[] = [];
  const nodeErrors: Record<string, string[]> = {};

  const primaryCount = new Map<string, number>();
  const secondaryCount = new Map<string, number>();
  for (const e of edges) {
    const bucket = e.role === "secondary" ? secondaryCount : primaryCount;
    bucket.set(e.to, (bucket.get(e.to) ?? 0) + 1);
  }
  for (const [nodeId, count] of primaryCount) {
    if (count > 1) graphErrors.push(`Un nœud ne peut avoir qu'une seule arête entrante (${nodeId}).`);
  }
  for (const [nodeId, count] of secondaryCount) {
    if (count > 1) graphErrors.push(`Un nœud ne peut avoir qu'une seule arête secondaire entrante (${nodeId}).`);
  }

  if (hasCycle(nodes, edges)) {
    graphErrors.push("Le graphe contient un cycle.");
  }

  if (!nodes.some((n) => n.kind === "reader")) graphErrors.push("Le pipeline doit contenir au moins une source.");
  if (!nodes.some((n) => n.kind === "writer")) graphErrors.push("Le pipeline doit contenir au moins une écriture.");

  for (const node of nodes) {
    const entry = opsCatalog[node.op];
    const errors = entry ? validateNodeParamsShape(entry, node.params) : [`Opération inconnue : ${node.op}.`];
    const hasSecondaryEdge = edges.some((e) => e.to === node.id && e.role === "secondary");
    if (entry) {
      if (entry.acceptsSecondaryInput) {
        const withCollectionId = node.params.withCollectionId;
        const hasParam = withCollectionId !== undefined && withCollectionId !== null && withCollectionId !== "";
        if (hasSecondaryEdge && hasParam) {
          errors.push(`${node.op} : withCollectionId et une arête secondaire ne peuvent pas être renseignés en même temps.`);
        } else if (!hasSecondaryEdge && !hasParam) {
          errors.push(`${node.op} : requiert soit withCollectionId, soit une arête secondaire.`);
        }
      } else if (hasSecondaryEdge) {
        errors.push(`${node.op} n'accepte pas d'arête secondaire.`);
      }
    }
    nodeErrors[node.id] = errors;
  }

  return { graphErrors, nodeErrors };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/validation.test.ts`
Expected: PASS (all tests, including pre-existing ones — a node with `withCollectionId` still required for `reader.collection`/`writer.collection` since those have no `acceptsSecondaryInput`, unaffected by the new branch).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/validation.ts shell/src/builder/pipeline/validation.test.ts
git commit -m "feat(shell): pipelines — client-side XOR validation for binary-op secondary inputs"
```

---

## Task 13: `PipelineCanvas.tsx` — secondary handle, role-aware connect, dashed edges, `transform.merge`

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: `hasIncomingEdge(edges, nodeId, role)` (Task 11), `PipelineOpsCatalog` (Task 10).
- Produces: `PipelineCanvas` now requires an `opsCatalog` prop — consumed by Task 17 (`PipelineBuilderPage.tsx`).

- [ ] **Step 1: Write the failing tests**

Update the existing render calls in `shell/src/builder/pipeline/PipelineCanvas.test.tsx` to pass the new required `opsCatalog` prop (add `opsCatalog={{}}` to all 4 existing `<PipelineCanvas .../>` calls — replace each occurrence of `onInsertOnEdge={vi.fn()} />` / `onInsertOnEdge={onInsertOnEdge} />` with `onInsertOnEdge={vi.fn()} opsCatalog={{}} />` / `onInsertOnEdge={onInsertOnEdge} opsCatalog={{}} />` respectively — 4 call sites total).

Add new tests:

```typescript
import type { PipelineOpsCatalog } from "../../api/types";

const BINARY_CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: {} } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: {} } },
  "transform.join": { kind: "transform", paramsSchema: { properties: {} }, acceptsSecondaryInput: true },
};

test("a node whose op accepts a secondary input renders a second target handle", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.join", x: 300, y: 0, params: {}, title: "J" },
  ];
  render(
    <PipelineCanvas nodes={nodes} edges={[]} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={BINARY_CATALOG} />,
  );
  const joinNodeEl = screen.getByText("J").closest(".react-flow__node")!;
  expect(joinNodeEl.querySelectorAll(".react-flow__handle").length).toBe(3); // primary target + secondary target + source
});

test("a node whose op does not accept a secondary input renders only one target handle", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={{}} />,
  );
  const readerNodeEl = screen.getByText("Villes").closest(".react-flow__node")!;
  expect(readerNodeEl.querySelectorAll(".react-flow__handle").length).toBe(2); // target + source
});

test("the edge insertion menu offers Fusionner (transform.merge)", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={{}} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  expect(screen.getByRole("menuitem", { name: "Fusionner" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: FAIL (TS error — `opsCatalog` prop doesn't exist yet; no second handle rendered; no "Fusionner" menu item).

- [ ] **Step 3: Implement**

Replace the full content of `shell/src/builder/pipeline/PipelineCanvas.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";
import {
  Background, Controls, EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider,
  getBezierPath,
  type Edge, type EdgeChange, type EdgeProps, type Node, type NodeChange, type NodeProps, type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PipelineEdge, PipelineNode, PipelineNodeStat, PipelineOpsCatalog } from "../../api/types";
import { genEdgeId, hasIncomingEdge, topologicalOrder, wouldCreateCycle } from "./graphOps";

// Les 6 op transform.* insérables sur une arête (cf. plan Task 6 — clic sur
// le "+" d'une arête, pas de drag-drop précis sur le tracé SVG). SP-15c
// ajoute les 5 op spatiales étage 1 ; SP-15g ajoute transform.merge (fusion
// ligne à ligne). writer.dataset n'y figure jamais (ce n'est pas une op
// transform, jamais candidate à cette liste, cf. design §5).
const INSERTABLE_TRANSFORMS: { op: string; label: string }[] = [
  { op: "transform.filter", label: "Filtrer" },
  { op: "transform.select", label: "Sélectionner" },
  { op: "transform.derive", label: "Dériver" },
  { op: "transform.aggregate", label: "Agréger" },
  { op: "transform.join", label: "Joindre" },
  { op: "transform.merge", label: "Fusionner" },
  { op: "transform.buffer", label: "Buffer" },
  { op: "transform.reproject", label: "Reprojeter" },
  { op: "transform.intersection", label: "Intersection" },
  { op: "transform.countWithin", label: "Compter dans" },
  { op: "transform.h3Aggregate", label: "Agréger H3" },
];

const KIND_COLOR: Record<PipelineNode["kind"], string> = {
  reader: "border-emerald-500 bg-emerald-50",
  transform: "border-amber-500 bg-amber-50",
  writer: "border-sky-500 bg-sky-50",
};

// Bagage porté par le `data` de chaque nœud React Flow (SP-15g) — étend
// PipelineNode (format fil) avec ce que seul le canvas a besoin de savoir
// pour se rendre : accepte-t-il une seconde entrée, où en est-il dans le run
// en cours (§5.1/§5.2 du design).
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
};

function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as CanvasNodeData;
  return (
    <div className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-blue-500" : ""}`}>
      <Handle type="target" position={Position.Left} id="primary" />
      {node.acceptsSecondaryInput && (
        <Handle type="target" position={Position.Top} id="secondary" style={{ borderStyle: "dashed" }} />
      )}
      <div className="font-medium">{node.title ?? node.op}</div>
      <div className="text-[10px] text-slate-500">{node.op}</div>
      <Handle type="source" position={Position.Right} />
      {node.nodeStat && (
        <span
          role="status"
          className="absolute -right-2 -top-2 rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] text-white"
        >
          {node.nodeStat.rowCount ?? "?"}
        </span>
      )}
      {node.isNext && !node.nodeStat && (
        <span
          role="status"
          aria-label="Exécution en cours"
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"
        />
      )}
    </div>
  );
}

function InsertOnEdgeButton({
  id, sourceX, sourceY, targetX, targetY, data, onInsert,
}: EdgeProps & { onInsert: (edgeId: string, op: string) => void }) {
  const [open, setOpen] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const role = (data as { role?: string } | undefined)?.role;
  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        style={role === "secondary" ? { strokeDasharray: "4 4" } : undefined}
      />
      <EdgeLabelRenderer>
        <div style={{ position: "absolute", transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: "all" }}>
          <button
            type="button"
            aria-label="Insérer une étape sur cette arête"
            className="h-5 w-5 rounded-full border border-slate-400 bg-white text-xs leading-none hover:bg-slate-100"
            onClick={() => setOpen((o) => !o)}
          >
            +
          </button>
          {open && (
            <ul role="menu" className="absolute z-10 mt-1 rounded border border-slate-300 bg-white text-xs shadow">
              {INSERTABLE_TRANSFORMS.map((t) => (
                <li key={t.op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-slate-100"
                    onClick={() => { onInsert(id, t.op); setOpen(false); }}
                  >
                    {t.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

function toFlowNode(
  n: PipelineNode, selected: boolean,
  extra: { acceptsSecondaryInput: boolean; nodeStat?: PipelineNodeStat; isNext: boolean },
): Node {
  return {
    id: n.id, position: { x: n.x, y: n.y },
    data: { ...n, ...extra } as unknown as Record<string, unknown>,
    type: "pipelineNode", selected,
  };
}
function toFlowEdge(e: PipelineEdge): Edge {
  return {
    id: e.id, source: e.from, target: e.to, type: "insertable",
    targetHandle: e.role === "secondary" ? "secondary" : "primary",
    data: { role: e.role },
  };
}

function PipelineCanvasInner({
  nodes, edges, selectedNodeId, onSelectNode, onNodesChange, onEdgesChange, onInsertOnEdge,
  opsCatalog, nodeStats, runStatus,
}: {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onNodesChange: (nodes: PipelineNode[]) => void;
  onEdgesChange: (edges: PipelineEdge[]) => void;
  onInsertOnEdge: (edgeId: string, op: string) => void;
  opsCatalog: PipelineOpsCatalog;
  nodeStats?: Record<string, PipelineNodeStat>;
  runStatus?: "queued" | "running" | "succeeded" | "failed";
}) {
  const nodeTypes = { pipelineNode: PipelineNodeBox };
  const edgeTypes = { insertable: (props: EdgeProps) => <InsertOnEdgeButton {...props} onInsert={onInsertOnEdge} /> };

  const onConnect: OnConnect = useCallback((connection) => {
    if (!connection.source || !connection.target) return;
    const role: "primary" | "secondary" = connection.targetHandle === "secondary" ? "secondary" : "primary";
    if (hasIncomingEdge(edges, connection.target, role)) return; // garde §3.4/§4.3 : ≤ 1 arête entrante par rôle
    if (wouldCreateCycle(nodes, edges, { from: connection.source, to: connection.target })) return;
    const newEdge: PipelineEdge = { id: genEdgeId(), from: connection.source, to: connection.target };
    if (role === "secondary") newEdge.role = "secondary";
    onEdgesChange([...edges, newEdge]);
  }, [nodes, edges, onEdgesChange]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    let next = nodes;
    for (const change of changes) {
      if (change.type === "position" && change.position) {
        next = next.map((n) => (n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n));
      }
      if (change.type === "remove") {
        next = next.filter((n) => n.id !== change.id);
      }
      // Ne réagit qu'à l'événement "sélectionné" (jamais "déselectionné") :
      // un clic sur un nouveau nœud émet deux changements dans un ordre non
      // garanti (ancien nœud selected:false, nouveau selected:true) — ne
      // traiter que selected:true rend la sélection robuste à cet ordre.
      // La désélection (clic sur le fond) passe par onPaneClick ci-dessous.
      if (change.type === "select" && change.selected) {
        onSelectNode(change.id);
      }
    }
    if (next !== nodes) onNodesChange(next);
  }, [nodes, onNodesChange, onSelectNode]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removedIds = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
    if (removedIds.size) onEdgesChange(edges.filter((e) => !removedIds.has(e.id)));
  }, [edges, onEdgesChange]);

  const order = topologicalOrder(nodes, edges);
  const nextNodeId = runStatus === "running" ? order.find((id) => !nodeStats?.[id]) : undefined;

  return (
    <div style={{ height: 480 }}>
      <ReactFlow
        nodes={nodes.map((n) => toFlowNode(n, n.id === selectedNodeId, {
          acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
          nodeStat: nodeStats?.[n.id],
          isNext: n.id === nextNodeId,
        }))}
        edges={edges.map(toFlowEdge)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onConnect={onConnect}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onPaneClick={() => onSelectNode(null)}
        deleteKeyCode={["Backspace", "Delete"]}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function PipelineCanvas(props: React.ComponentProps<typeof PipelineCanvasInner>) {
  return (
    <ReactFlowProvider>
      <PipelineCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
```

Note: `Handle` elements always render a DOM node with class `react-flow__handle` regardless of connections — the test's `querySelectorAll(".react-flow__handle")` count assertion (2 vs 3) relies on this DOM structure, consistent with how `@xyflow/react` renders `<Handle>`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: PASS (all tests, including the 4 pre-existing ones now updated with `opsCatalog={{}}`).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "feat(shell): pipelines — secondary input handle on canvas, dashed edges, transform.merge"
```

---

## Task 14: `PipelineCanvas.tsx` — progress badges/spinner from `nodeStats`

This task is intentionally split from Task 13 (which introduced the `nodeStats`/`runStatus`/`isNext`/`nodeStat` plumbing already) — it just adds the dedicated tests proving the progress UI reacts to real data, since Task 13's tests only covered the secondary-handle rendering.

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: `nodeStats`/`runStatus` props (already implemented in Task 13).
- Produces: nothing new.

- [ ] **Step 1: Write the tests**

Add to `shell/src/builder/pipeline/PipelineCanvas.test.tsx`:

```typescript
test("a node present in nodeStats shows its row count as a badge", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={{}}
      nodeStats={{ r1: { nodeId: "r1", op: "reader.collection", rowCount: 42 } }} runStatus="running" />,
  );
  expect(screen.getByText("42")).toBeInTheDocument();
});

test("the first not-yet-completed node in topological order shows a spinner while running", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={{}}
      nodeStats={{}} runStatus="running" />,
  );
  expect(screen.getByRole("status", { name: "Exécution en cours" })).toBeInTheDocument();
});

test("no spinner is shown once the run is no longer 'running'", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} opsCatalog={{}}
      nodeStats={{}} runStatus="succeeded" />,
  );
  expect(screen.queryByRole("status", { name: "Exécution en cours" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they pass** (implementation already landed in Task 13)

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "test(shell): pipelines — canvas progress badge/spinner from nodeStats"
```

---

## Task 15: `PipelineRunPanel.tsx` — `onLatestRunChange`

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.tsx`
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`

**Interfaces:**
- Produces: `onLatestRunChange?: (run: PipelineRun | null) => void` prop — consumed by Task 17 (`PipelineBuilderPage.tsx`).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`:

```typescript
test("calls onLatestRunChange with the newest run whenever the run list is (re)loaded", async () => {
  const onLatestRunChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-0", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null, nodeStats: {} },
    ]),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" onLatestRunChange={onLatestRunChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(onLatestRunChange).toHaveBeenCalledWith(
    expect.objectContaining({ id: "run-0" }),
  ));
});

test("calls onLatestRunChange with null when there is no run yet", async () => {
  const onLatestRunChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" onLatestRunChange={onLatestRunChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(onLatestRunChange).toHaveBeenCalledWith(null));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx`
Expected: FAIL (TS error — no such prop yet).

- [ ] **Step 3: Implement**

In `shell/src/builder/pipeline/PipelineRunPanel.tsx`, change the function signature and the two places that call `setRuns`:

```typescript
export function PipelineRunPanel({
  pipelineId, onLatestRunChange,
}: { pipelineId: string; onLatestRunChange?: (run: PipelineRun | null) => void }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function loadRuns() {
    const latest = await client.getPipelineRuns(pipelineId);
    setRuns(latest);
    onLatestRunChange?.(latest[0] ?? null);
  }

  useEffect(() => {
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  async function poll() {
    for (;;) {
      const latest = await client.getPipelineRuns(pipelineId);
      setRuns(latest);
      onLatestRunChange?.(latest[0] ?? null);
      const status = latest[0]?.status;
      if (status !== "queued" && status !== "running") {
        setRunning(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
```

(the rest of the file — `onRun`/the JSX return — is unchanged)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx`
Expected: PASS (all tests, including the 4 pre-existing ones — the prop is optional, no existing render call needs updating).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.test.tsx
git commit -m "feat(shell): pipelines — PipelineRunPanel exposes the latest run via onLatestRunChange"
```

---

## Task 16: `PipelinePreviewMap.tsx` (new) + `PipelinePreviewPanel.tsx` toggle

**Files:**
- Create: `shell/src/builder/pipeline/PipelinePreviewMap.tsx`
- Create: `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`
- Modify: `shell/src/test/MockMaplibreMap.ts`
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:**
- Produces: `PipelinePreviewMap({ rows }: { rows: Record<string, unknown>[] })` — consumed by `PipelinePreviewPanel.tsx` (this task).

- [ ] **Step 1: Extend the shared MapLibre test double**

In `shell/src/test/MockMaplibreMap.ts`, add a `fitBounds` recorder (additive — doesn't change any existing method):

```typescript
  fitBoundsArgs: unknown[] = [];
```

(add this field declaration next to the existing `flyToArgs: unknown[] = [];`)

```typescript
  fitBounds(bounds: unknown, opts?: unknown) {
    this.fitBoundsArgs.push({ bounds, opts });
  }
```

(add this method next to the existing `flyTo` method)

- [ ] **Step 2: Write the failing test for `PipelinePreviewMap`**

Create `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { mapInstances } from "../../test/MockMaplibreMap";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

beforeEach(() => {
  mapInstances.length = 0;
});

test("adds a geojson source built from the rows carrying a geometry", () => {
  render(<PipelinePreviewMap rows={[
    { id: 1, geometry: { type: "Point", coordinates: [3.0, 45.0] } },
    { id: 2, geometry: null },
  ]} />);
  const map = mapInstances[0];
  const source = map.getSource("pipeline-preview") as { spec: { data: GeoJSON.FeatureCollection } };
  expect(source.spec.data.features).toHaveLength(1); // the null-geometry row is excluded
  expect(source.spec.data.features[0].geometry).toEqual({ type: "Point", coordinates: [3.0, 45.0] });
});

test("fits the map to the bounds of the rendered features", () => {
  render(<PipelinePreviewMap rows={[
    { id: 1, geometry: { type: "Point", coordinates: [1.0, 10.0] } },
    { id: 2, geometry: { type: "Point", coordinates: [3.0, 20.0] } },
  ]} />);
  const map = mapInstances[0];
  expect(map.fitBoundsArgs).toHaveLength(1);
  expect(map.fitBoundsArgs[0]).toEqual({
    bounds: [[1.0, 10.0], [3.0, 20.0]],
    opts: { padding: 20, maxZoom: 16 },
  });
});

test("does not call fitBounds when there are no geometries to show", () => {
  render(<PipelinePreviewMap rows={[{ id: 1, geometry: null }]} />);
  expect(mapInstances[0].fitBoundsArgs).toHaveLength(0);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx`
Expected: FAIL (module doesn't exist yet).

- [ ] **Step 4: Implement `PipelinePreviewMap.tsx`**

Create `shell/src/builder/pipeline/PipelinePreviewMap.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DEFAULT_BASEMAP } from "../../map/basemaps";

const SOURCE_ID = "pipeline-preview";

function collectCoordinates(geometry: GeoJSON.Geometry): [number, number][] {
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates as [number, number]];
    case "MultiPoint":
    case "LineString":
      return geometry.coordinates as [number, number][];
    case "MultiLineString":
    case "Polygon":
      return (geometry.coordinates as [number, number][][]).flat();
    case "MultiPolygon":
      return (geometry.coordinates as [number, number][][][]).flat(2);
    case "GeometryCollection":
      return geometry.geometries.flatMap(collectCoordinates);
    default:
      return [];
  }
}

function computeBounds(features: GeoJSON.Feature[]): [[number, number], [number, number]] | null {
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  for (const f of features) {
    if (!f.geometry) continue;
    for (const [lng, lat] of collectCoordinates(f.geometry)) {
      minLng = Math.min(minLng, lng);
      maxLng = Math.max(maxLng, lng);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }
  }
  return minLng === Infinity ? null : [[minLng, minLat], [maxLng, maxLat]];
}

// Aperçu cartographique d'une étape de pipeline (SP-15g §5.3) — alternative à
// PipelinePreviewPanel's table, construite entièrement côté client à partir
// des lignes déjà décodées en GeoJSON par POST /pipelines/{id}/preview
// (ST_AsGeoJSON côté runtime, aucun appel réseau supplémentaire ici).
export function PipelinePreviewMap({ rows }: { rows: Record<string, unknown>[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const features: GeoJSON.Feature[] = rows
      .filter((r) => r.geometry != null)
      .map((r) => ({ type: "Feature", properties: {}, geometry: r.geometry as GeoJSON.Geometry }));
    const featureCollection: GeoJSON.FeatureCollection = { type: "FeatureCollection", features };

    const map = new maplibregl.Map({
      container: containerRef.current, style: DEFAULT_BASEMAP.style, center: [0, 0], zoom: 1,
    });
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: featureCollection });
      map.addLayer({
        id: `${SOURCE_ID}-fill`, type: "fill", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.4 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`, type: "line", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#2563eb", "line-width": 2 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`, type: "circle", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": "#2563eb", "circle-radius": 5 },
      });
      const bounds = computeBounds(features);
      if (bounds) map.fitBounds(bounds, { padding: 20, maxZoom: 16 });
    });
    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} data-testid="pipeline-preview-map" style={{ height: 300 }} />;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx`
Expected: PASS.

- [ ] **Step 6: Write the failing test for the `PipelinePreviewPanel` toggle**

Add to `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`:

```typescript
test("shows a Tableau/Carte toggle when rows carry a geometry column, and defaults to Tableau", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]));
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  expect(screen.getByRole("table")).toBeInTheDocument();
});

test("hides the toggle and always shows the table when no row has a geometry column", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(previewPipeline).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Carte" })).not.toBeInTheDocument();
});

test("clicking Carte swaps the table for the map view", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]));
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  screen.getByRole("button", { name: "Carte" }).click();
  expect(screen.getByTestId("pipeline-preview-map")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
```

Add the same `vi.mock("maplibre-gl", ...)` stub used in Task 16 Step 2 to the top of this test file (needed transitively now that `PipelinePreviewPanel` can render `PipelinePreviewMap`):

```typescript
vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx`
Expected: FAIL (no toggle rendered yet).

- [ ] **Step 8: Implement the toggle in `PipelinePreviewPanel.tsx`**

Replace the full content of `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { usePipelinePreview } from "../../api/hooks";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

export function PipelinePreviewPanel({ pipelineId, nodeId }: { pipelineId: string; nodeId: string | null }) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId);
  const [view, setView] = useState<"table" | "map">("table");

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">Chargement de l'aperçu…</p>;
  if (previewQuery.isError) return <p role="alert" className="text-sm text-red-600">Aperçu indisponible.</p>;

  const rows = previewQuery.data ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const hasGeometry = columns.includes("geometry");

  return (
    <div className="flex flex-col gap-2">
      {hasGeometry && (
        <div className="flex gap-1 text-xs">
          <button
            type="button" onClick={() => setView("table")}
            className={`rounded px-2 py-1 ${view === "table" ? "bg-slate-200" : ""}`}
          >
            Tableau
          </button>
          <button
            type="button" onClick={() => setView("map")}
            className={`rounded px-2 py-1 ${view === "map" ? "bg-slate-200" : ""}`}
          >
            Carte
          </button>
        </div>
      )}
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap rows={rows} />
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr>{columns.map((c) => <th key={c} className="p-1 text-left">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-slate-200">
                {columns.map((c) => <td key={c} className="p-1">{String(row[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx src/builder/pipeline/PipelinePreviewMap.test.tsx`
Expected: PASS (all tests, including the 3 pre-existing `PipelinePreviewPanel` tests — none of their fixture rows carry a `geometry` column, so the toggle stays hidden and the table renders exactly as before).

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewMap.tsx shell/src/builder/pipeline/PipelinePreviewMap.test.tsx \
        shell/src/test/MockMaplibreMap.ts shell/src/builder/pipeline/PipelinePreviewPanel.tsx \
        shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx
git commit -m "feat(shell): pipelines — map preview alongside the tabular one"
```

---

## Task 17: `PipelineBuilderPage.tsx` — wire it all together

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `PipelineCanvas`'s new `opsCatalog`/`nodeStats`/`runStatus` props (Task 13), `PipelineRunPanel`'s new `onLatestRunChange` prop (Task 15).
- Produces: nothing new consumed elsewhere — this is the top-level wiring point.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/pages/PipelineBuilderPage.test.tsx`:

```typescript
test("persisted mode: a completed run's node stats reach the canvas as a badge", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-1", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null,
        nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 7 } } },
    ]),
  });
  await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: FAIL (`PipelineCanvas` never receives `nodeStats`, no badge rendered).

- [ ] **Step 3: Implement**

In `shell/src/pages/PipelineBuilderPage.tsx`, add state and wire the new props. Replace the imports line for types and add `PipelineRun`:

```typescript
import type { PipelineEdge, PipelineNode, PipelinePayload, PipelineRun } from "../api/types";
```

Add state, right after the existing `useState` declarations:

```typescript
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
```

Update the `<PipelineCanvas>` call:

```tsx
        <PipelineCanvas
          nodes={draft.nodes}
          edges={draft.edges}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
          onNodesChange={setNodes}
          onEdgesChange={setEdges}
          onInsertOnEdge={onInsertOnEdge}
          opsCatalog={catalog}
          nodeStats={latestRun?.nodeStats}
          runStatus={latestRun?.status}
        />
        {pk !== null && <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: PASS (all tests, including the 4 pre-existing ones — unaffected, `opsCatalog`/`nodeStats`/`runStatus` are read from state that defaults to values already computed/`null`).

- [ ] **Step 5: Full shell unit-test suite check**

Run: `cd shell && npm run test`
Expected: PASS (all files).

Run: `cd shell && npm run build`
Expected: PASS (`tsc --noEmit` + vite build, no type errors anywhere in the touched files).

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx
git commit -m "feat(shell): pipelines — wire opsCatalog/nodeStats/runStatus into the canvas"
```

---

## Task 18: E2E — secondary-handle connection + progress visibility

**Files:**
- Modify: `shell/e2e/pipeline-builder.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-17, exercised end-to-end through the real (mocked-backend) app.

- [ ] **Step 1: Extend the mocked ops catalog and add a second collection/reader**

In `shell/e2e/pipeline-builder.spec.ts`, update `OPS_CATALOG` to mark `transform.join` as binary and add its `on` param, and extend `mockPipelineFlow`'s `/collections` mock is already sufficient (it already returns `villes`/`villes_propres` — reuse `villes` as the second reader's source too, no mock change needed there):

```typescript
const OPS_CATALOG = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "transform.join": {
    kind: "transform",
    paramsSchema: { properties: { withCollectionId: { type: "string", format: "collection-id" }, on: { type: "string" } }, required: ["on"] },
    acceptsSecondaryInput: true,
  },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};
```

- [ ] **Step 2: Write the new test**

Append to `shell/e2e/pipeline-builder.spec.ts`:

```typescript
test("un utilisateur relie une seconde source sur la poignée secondaire d'un transform.join", async ({ page }) => {
  await mockCore(page);
  await mockPipelineFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("pipeline");
  await dialog.getByLabel("Titre").fill("Joindre deux sources");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/pipelines\/new$/);

  const canvas = page.locator(".react-flow__pane");
  await page.getByText("reader.collection").dragTo(canvas, { targetPosition: { x: 100, y: 200 } });
  await page.getByText("reader.collection").dragTo(canvas, { targetPosition: { x: 100, y: 50 } });
  await page.getByText("transform.join").dragTo(canvas, { targetPosition: { x: 350, y: 150 } });
  await page.getByText("writer.collection").dragTo(canvas, { targetPosition: { x: 600, y: 150 } });

  const nodes = page.locator(".react-flow__node");
  const primaryReader = nodes.nth(0);
  const secondaryReader = nodes.nth(1);
  const joinNode = nodes.nth(2);
  const writerNode = nodes.nth(3);

  // Primaire : premier reader -> entrée primaire (gauche) du join.
  await primaryReader.locator(".react-flow__handle-right").dragTo(joinNode.locator(".react-flow__handle-left"));
  // Secondaire : second reader -> entrée secondaire (haut) du join.
  await secondaryReader.locator(".react-flow__handle-right").dragTo(joinNode.locator(".react-flow__handle-top"));
  // join -> writer.
  await joinNode.locator(".react-flow__handle-right").dragTo(writerNode.locator(".react-flow__handle-left"));

  await primaryReader.click();
  await page.getByLabel("collectionId").selectOption("villes");
  await secondaryReader.click();
  await page.getByLabel("collectionId").selectOption("villes_propres");
  await joinNode.click();
  await page.getByLabel("on").fill("id");
  await writerNode.click();
  await page.getByLabel("collectionId").selectOption("villes_propres");

  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
});
```

Note: this test only exercises canvas wiring + save-button enablement (no real save/run — the `withCollectionId`-less join is validated client-side by Task 12's logic, which the plan's mocked `OPS_CATALOG` above already supports via `acceptsSecondaryInput: true`).

- [ ] **Step 3: Run the E2E spec**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- pipeline-builder`
Expected: PASS (both the pre-existing test and the new one).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/pipeline-builder.spec.ts
git commit -m "test(e2e): pipelines — connect a secondary input handle on transform.join"
```

---

## Final full-suite check

- [ ] Run `cd core && uv run pytest -q` — expect the pre-existing baseline (606+ passed, ~87 skipped without docker) plus every new test added in Tasks 1-9, all green.
- [ ] Run `cd shell && npm run test` — expect the pre-existing 398+ tests plus every new test added in Tasks 10-17, all green.
- [ ] Run `cd shell && npm run build` — expect a clean `tsc --noEmit` + vite build.
- [ ] Run `cd shell && VITE_AUTH_MODE=mock npm run e2e` — expect all 18+ specs green, including the extended `pipeline-builder.spec.ts`.
- [ ] Update `CLAUDE.md`'s "Fait"/"À venir" sections to record SP-15g as delivered (per the project's existing convention, cf. the SP-15a-f entries) — **do this only after the above four checks are green**, as a final documentation commit.
