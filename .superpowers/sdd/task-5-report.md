# Task 5 report — Wire reader.connector.rest/postgres into runtime dispatch

## Summary

Implemented exactly as briefed: `core/app/pipelines/runtime.py`'s `_prepare()`
reader-materialization loop now dispatches on `node.op` (`reader.collection`,
`reader.connector.rest`, `reader.connector.postgres`, else raises
`PipelineRuntimeError(f"unknown reader op '{node.op}'")`), translating
`connector_runtime.ConnectorRuntimeError` → `PipelineRuntimeError` at each of
the two new branches — the same translation pattern already used for
`compiler.transform_output_srid`'s `ValueError` in
`_execute_transform_chain`.

This is the terminal task of the SP-15f plan (reader.connector dlt REST +
Postgres). Commit: `7341d35`.

## Pre-flight: confirming the brief's snapshot

Read the current `core/app/pipelines/runtime.py` before touching anything.
Its imports and `_prepare()` body matched the brief's "before" block
verbatim — no other task had touched this file since the plan was written.
Proceeded without asking.

## Deviations from the brief (both are test-code bugs in the brief, found
independently, not implementation choices)

1. **Import style**: merged `from app.pipelines import connector_runtime`
   into the existing `from app.pipelines import compiler` line
   (`from app.pipelines import compiler, connector_runtime`) instead of a
   separate import statement. Functionally identical; avoids a duplicate
   `from app.pipelines import ...` line. Everything else in the import block
   matches the brief exactly (alphabetized `ops.schemas` import list).

2. **Test 2 (`test_preview_reader_connector_missing_secret_raises_...`)**:
   the brief's exact test code builds a `PipelinePayload` with only a reader
   node and no writer, and empty edges. `app/configs/schemas.py`'s
   `PipelinePayload._validate_graph` (pre-existing, unrelated to SP-15f) has
   always required at least one writer node — this raises a pydantic
   `ValidationError` *before* `runtime.preview_pipeline` is ever called,
   regardless of Task 5's implementation. Verified this independently by
   running the brief's literal test code first (see RED evidence below) —
   the traceback showed the payload itself failing to construct, not
   `_prepare()`. Fixed by adding a `w1` writer node (`writer.export`) wired
   by an edge from `r1`; the writer is never reached because
   `preview_pipeline(up_to="r1")` stops the execution chain at `r1`, and
   `_prepare()` (which processes all reader nodes up front, including the
   one with the missing secret) raises before any writer node is touched.
   Test intent (missing-secret → `PipelineRuntimeError` matching "not found")
   is unchanged.

3. **Test 3 (`test_run_pipeline_reader_connector_rest_never_leaks_secret_value`)**:
   the brief's exact test code passes `created_by="u1"` (a literal string) to
   `secrets_repo.create_secret`. `connector_secrets.created_by` is a real FK
   to `users.id` (`app/secrets/models.py`); under SQLite with
   `PRAGMA foreign_keys=ON` this raises `sqlalchemy.exc.IntegrityError`. This
   exact defect is already documented and fixed in Task 3/4's own test file
   (`core/tests/test_pipeline_connector_runtime.py`'s `user` fixture docstring:
   *"contrairement au brief initial qui passait une chaîne littérale 'u1',
   il faut un utilisateur réel"*) — applied the identical fix here: create a
   real user via `get_or_create_user(...)` and pass `author.id`. Also has the
   same missing-writer-node issue as (2); fixed the same way (added `w1`
   writer + edge, never reached since `up_to="r1"`).

No other code paths were touched. `app/pipelines/connector_runtime.py`
(Tasks 3/4) was read to confirm signatures
(`materialize_rest_connector(conn, *, session, tenant_id, node_id, params,
view_name)`, `materialize_postgres_connector(...)` same shape,
`ConnectorRuntimeError`) — matched what Task 5's dispatch code assumes,
no changes needed there.

## TDD evidence

### RED

```
cd core && uv run pytest tests/test_pipeline_runtime.py -k reader_connector -v
```
All 3 failed as expected, for the expected reason (before any test-code
fixes were applied, confirming the brief's own claim):
```
FAILED test_preview_reader_connector_rest_feeds_downstream_filter
  pydantic_core._pydantic_core.ValidationError: 1 validation error for ReaderCollectionParams
  (app/pipelines/runtime.py:195 — hard-coded ReaderCollectionParams.model_validate)
FAILED test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error
  (initially: pydantic ValidationError on PipelinePayload itself — "pipeline requires at
  least one writer node" — a brief test-code bug found independently, fixed per
  deviation #2 above; after the fix, still RED for the right reason pre-wiring:
  ReaderCollectionParams.model_validate ValidationError)
FAILED test_run_pipeline_reader_connector_rest_never_leaks_secret_value
  (initially: sqlite3.IntegrityError FK constraint on created_by="u1" — a brief
  test-code bug found independently, fixed per deviation #3 above; after the fix,
  still RED for the right reason pre-wiring)
```

```
cd core && uv run pytest tests/test_pipeline_config_validation.py -k reader_connector -v
```
Result: **1 passed** — independently confirmed the brief's claim that this
regression test needs no code change to `config_validation.py`, rather than
assuming it.

### GREEN

```
cd core && uv run pytest tests/test_pipeline_runtime.py -v
```
```
18 passed, 7 skipped in 3.44s
```
(7 skipped = pre-existing postgis-marked / qgis end-to-end tests that need
docker/sidecar, unrelated to this task.) All 3 new `reader_connector` tests
pass.

```
cd core && uv run pytest tests/test_pipeline_config_validation.py -v
```
```
6 passed in 2.16s
```

## Lint-imports

```
cd core && uv run lint-imports
```
```
Analyzed 146 files, 420 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```
Matches brief's expectation exactly.

## Full core suite (with live Postgres, postgis-marked tests executing)

```
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" uv run pytest -v
```
```
1237 passed, 5 skipped in 93.52s (0:01:33)
```
Zero FAILED/ERROR lines (`grep -E "FAILED|ERROR"` on the full log — no
matches). The 5 skips are the pre-existing, already-documented
`@pytest.mark.qgis` sidecar tests (`test_execute_qgis_transform_computes_centroids`,
`test_transform_qgis_end_to_end_dissolve_then_write`,
`test_qgis_worker_sidecar.py`'s 3 tests) — carried over from SP-15d, unrelated
to this task, still pending a real sidecar+`/scratch` environment per
CLAUDE.md's tracked open item.

## Files changed

- `core/app/pipelines/runtime.py` — dispatch wiring (+54/-15 net incl. new
  branches), imports updated.
- `core/tests/test_pipeline_runtime.py` — 3 new tests (+108 lines, with the
  fixes described in Deviations 2/3 above).
- `core/tests/test_pipeline_config_validation.py` — 1 new regression test
  (+15 lines, verbatim from brief, no fix needed).

Commit: `7341d35` — "feat(core): pipelines — wire reader.connector.rest/postgres
into runtime dispatch"

## Self-review

- **`reader.collection` unchanged behavior**: yes — the `if node.op ==
  "reader.collection":` branch is byte-for-byte the same logic as before
  (same calls to `_require_readable_collection_id`, `_table_info_for_collection`,
  `_materialize_reader`, same srid fallback), just re-indented under the
  dispatch. All pre-existing `reader.collection`-based tests in
  `test_pipeline_runtime.py` and the full suite still pass unchanged.
- **`ConnectorRuntimeError` → `PipelineRuntimeError` translation**: yes, for
  both new branches, via `try/except connector_runtime.ConnectorRuntimeError
  as exc: raise PipelineRuntimeError(str(exc)) from exc` — verified live by
  `test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error`
  (asserts `pytest.raises(runtime.PipelineRuntimeError, match="not found")`
  around a `reader.connector.postgres` node whose secret doesn't exist —
  `connector_runtime._resolve_secret` raises `ConnectorRuntimeError(f"secret
  '{secret_name}' not found")`, correctly re-raised and matched).
- **Unrecognized `node.op` for a reader node**: yes — the `else:` branch
  raises `PipelineRuntimeError(f"unknown reader op '{node.op}'")`, matching
  the brief exactly. Not separately unit-tested by the brief (no test case
  requested for this branch specifically), but it's a straightforward
  one-line fallback identical in shape to the pattern already exercised
  elsewhere in this file.
- **Secret-leak test meaningful**: yes — it round-trips a real encrypted
  secret through `app.secrets.crypto.encrypt`/the `connector_secrets` table,
  configures `httpserver` to require the exact `Authorization: Bearer
  s3cr3t-leak-check` header (so the test fails outright if the auth header
  is missing or wrong — not vacuous), then asserts the plaintext token
  string never appears anywhere in the returned preview rows
  (`assert "s3cr3t-leak-check" not in str(rows)`). This is a real assertion
  against the actual row payload, not a tautology.
- **`srid_by_node[node.id] = 4326` harmless for connector reads**: confirmed
  by inspecting `app/pipelines/compiler.py` — every spatial transform SQL
  (`transform.buffer/reproject/intersection/countWithin/h3Aggregate`)
  references a `geometry` column by name directly in the generated SQL
  (e.g. `ST_Buffer(geometry, ...)`, `ST_Intersects(t.geometry, o.geometry)`).
  A connector-materialized view has no `geometry` column (dlt/REST/Postgres
  rows carry no geometry in v0), so DuckDB raises a clean binder error
  ("column geometry not found" or similar) at `conn.execute()` the moment a
  spatial transform is chained directly after a connector reader — never a
  silently-wrong SRID being applied to nonexistent geometry.
- **Full suite clean**: yes, `1237 passed, 5 skipped`, zero regressions; the
  5 skips are pre-existing and already tracked as an open item in CLAUDE.md
  (qgis sidecar tests never run for real).
- **Test output pristine**: yes for the target files
  (`test_pipeline_runtime.py`, `test_pipeline_config_validation.py`) and for
  the full suite — no warnings beyond a pre-existing, unrelated
  `ResourceWarning: unclosed database` noise line that appears in the RED
  run only (an artifact of `sqlite3` connection teardown timing in a failing
  test, not present in the GREEN run's output for these files).

## Concerns

None blocking. Two independently-found bugs in the brief's exact test code
(missing writer node breaking `PipelinePayload` construction; literal
`created_by="u1"` violating a real FK) were fixed using the same fix already
established in the prior task's test file for the FK issue, and a minimal,
intent-preserving addition (an unreached writer node) for the missing-writer
issue. Both are documented inline in the test file as comments explaining
why the extra node exists / why a real user is created, so a future reader
won't mistake them for arbitrary embellishment.
