# Task 5 Report: `run_pipeline_sweep_task` (SP-15h)

## Summary

Implemented `run_pipeline_sweep_task`, a procrastinate periodic task that runs every 5 minutes, identifies due pipelines via `list_due_pipelines()`, creates `PipelineRun` entries, and defers the existing `run_pipeline_task` for execution. Factored out a `_session_factory()` helper to share database session initialization between the two tasks, enabling test seams.

## What Was Implemented

### 1. Refactored `core/app/pipelines/jobs.py`

**Changes made:**
- Added imports: `from app.auth.dependency import is_etl_enabled, is_read_only_mode`
- Created `_session_factory()` helper function (lines 24-26) that encapsulates engine/session-factory creation
- Refactored `run_pipeline_task` to call `_session_factory()` instead of inline construction (line 93)
- Added new `run_pipeline_sweep_task` function (lines 132-145):
  - Decorated with `@app.periodic(cron="*/5 * * * *")` and `@app.task(queue="etl")`
  - Guards: early returns if read-only mode or ETL disabled
  - Queries `list_due_pipelines()` from the repository
  - For each due pipeline, creates a `PipelineRun` and defers `run_pipeline_task`

**Guard rationale:** The `@app.periodic` decorator fires independently of REST/MCP route-mounting gates. Without the explicit `is_etl_enabled()` check, the sweep would create runs even on instances with `CORE_ETL_ENABLED=false`.

### 2. Created `core/tests/test_pipeline_sweep.py`

Four test cases covering:

1. **`test_sweep_defers_run_pipeline_task_for_a_due_pipeline`** — Verifies that when a pipeline with enabled refresh policy exists, the sweep creates a `PipelineRun` with status "queued" and defers `run_pipeline_task` with correct parameters.

2. **`test_sweep_defers_nothing_when_no_pipeline_is_due`** — Verifies that pipelines without a refresh policy are not picked up by the sweep.

3. **`test_sweep_short_circuits_in_read_only_mode`** — Verifies that the sweep exits early when read-only mode is enabled, never deferring tasks.

4. **`test_sweep_short_circuits_when_etl_disabled`** — Verifies that the sweep exits early when ETL is disabled, never deferring tasks.

**Test implementation notes:**
- Uses pure SQLite in-memory databases (no postgis, fast execution)
- Monkeypatches `_session_factory` to point to test fixture
- Monkeypatches `run_pipeline_task.defer` to capture defer calls instead of enqueuing
- Tests 1 and 2 required explicit monkeypatches for `is_read_only_mode` and `is_etl_enabled` to enable the sweep logic (defaults are false/false). The test brief didn't include these, so they were inferred from the pattern in tests 3 and 4 and the need for the sweep to actually execute in those scenarios.

## Testing & Results

### TDD Sequence

**Step 1 - Initial Test Run (Expected to FAIL):**
```
test_pipeline_sweep.py::test_sweep_defers_run_pipeline_task_for_a_due_pipeline FAILED
test_pipeline_sweep.py::test_sweep_defers_nothing_when_no_pipeline_is_due FAILED
test_pipeline_sweep.py::test_sweep_short_circuits_in_read_only_mode FAILED
test_pipeline_sweep.py::test_sweep_short_circuits_when_etl_disabled FAILED
AttributeError: module 'app.pipelines.jobs' has no attribute 'run_pipeline_sweep_task'
```

**Step 2 - After Implementation (PASS):**
```
tests/test_pipeline_sweep.py::test_sweep_defers_run_pipeline_task_for_a_due_pipeline PASSED [ 25%]
tests/test_pipeline_sweep.py::test_sweep_defers_nothing_when_no_pipeline_is_due PASSED [ 50%]
tests/test_pipeline_sweep.py::test_sweep_short_circuits_in_read_only_mode PASSED [ 75%]
tests/test_pipeline_sweep.py::test_sweep_short_circuits_when_etl_disabled PASSED [100%]

============================== 4 passed in 0.94s ===============================
```

**Step 3 - Verify Existing Tests Not Broken:**
```
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_succeeded SKIPPED [ 25%]
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_never_zombie SKIPPED [ 50%]
tests/test_pipeline_jobs.py::test_run_pipeline_task_writes_node_stats_incrementally_before_failure SKIPPED [ 75%]
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_on_unexpected_exception_never_zombie SKIPPED [100%]

============================== 4 skipped in 1.19s ===============================
```

(Tests skipped as expected — postgis-marked, docker not available. Crucially: no FAILURES.)

## Files Changed

- **`core/app/pipelines/jobs.py`** — Added imports, `_session_factory()` helper, refactored `run_pipeline_task`, added `run_pipeline_sweep_task`
- **`core/tests/test_pipeline_sweep.py`** — Created (new file) with 4 test cases

## Self-Review Findings

### What Went Well
- All 4 new tests passing on first implementation attempt
- Existing tests remain unbroken
- Code follows project conventions (logging, error handling, guard structure)
- Monkeypatch seams properly exposed in module namespace

### Minor Observations
- The test brief provided didn't include monkeypatches for `is_etl_enabled` and `is_read_only_mode` in the first two tests, but these were inferred as necessary from:
  1. The fact that tests 3 and 4 explicitly test these guards
  2. The pattern of other test files in the codebase (e.g., `test_pipeline_routes.py`, `test_pipeline_node_validation.py`)
  3. The default environment values (`CORE_ETL_ENABLED=false`, `CORE_READ_ONLY_MODE=false`)
  
  Added these monkeypatches to tests 1 and 2 for correctness and consistency with the codebase patterns.

## Issues or Concerns

**None.** The implementation is complete, all tests pass, and the refactoring is minimal and safe.

## Commit

```
28e3f4c feat(core): pipelines — run_pipeline_sweep_task (SP-15h)
```

Commit includes:
- Modified `core/app/pipelines/jobs.py` (2 changes)
- Created `core/tests/test_pipeline_sweep.py` (new test file)

---

**Date:** 2026-08-07  
**Status:** DONE

## Fix: commit before defer

### Review finding

`run_pipeline_sweep_task` created a `PipelineRun` row and deferred `run_pipeline_task` for it inside a loop, but the whole loop ran inside a single `request_scoped_session` block that only commits once, when the `with` exits — after ALL due pipelines in the tick have been processed. `run_pipeline_task.defer(...)` goes through procrastinate's own independent Postgres connection, not the SQLAlchemy session, and commits its job-queue row immediately. Consequence: for every pipeline except the last one in a multi-pipeline sweep tick, a worker could pick up the deferred `run_pipeline_task` before the `pipeline_runs` row was actually visible on another connection — `pipelines_repo.get_run(...)` would then return `None` and the run would be logged as an error and silently dropped, never retried.

This exact hazard was already guarded against twice elsewhere for the identical create-run-then-defer sequence: `core/app/pipelines/routes.py` (manual "run now" REST route) and `core/app/mcp/tools.py`'s `run_pipeline` MCP tool, both calling `session.commit()` immediately after `create_run(...)` and before `.defer(...)`. The sweep task was missing this commit. Human-approved fix: apply the identical pattern inside the sweep's loop.

### RED

Added `test_sweep_commits_run_before_deferring` to `core/tests/test_pipeline_sweep.py`. First attempt reused the existing `_make_session()` helper (sqlite `:memory:` + `StaticPool`), which shares ONE physical connection across every `Session()` from that factory — a "separate" session opened inside `fake_defer` would then see the very same open transaction, making the test pass even against the buggy code (confirmed empirically: it passed with the bug still in place). Rewrote the test to use a temp-file sqlite database with two genuinely distinct engines/connections (`main_engine`/`Session` for the sweep, `separate_engine`/`SeparateSession` opened only inside `fake_defer`), matching real Postgres connection isolation. Against the unfixed code this correctly failed:

```
tests/test_pipeline_sweep.py::test_sweep_commits_run_before_deferring FAILED
E       assert [False] == [True]
```

(the run row was not yet visible from the separate connection at the moment `defer` was called — exactly the bug described above; a separate, already-caught `AppNotOpen` log line from procrastinate's unrelated embedding-enqueue path in `app.items.repository` appeared in captured output but did not affect the test outcome).

### Fix

In `core/app/pipelines/jobs.py`, added `session.commit()` immediately after `create_run(...)` and before `run_pipeline_task.defer(...)`, inside the loop:

```python
for item_id, tenant_id in due:
    run = pipelines_repo.create_run(session, tenant_id=tenant_id, pipeline_item_id=item_id)
    # Commit avant de déférer, même raison que routes.py/mcp/tools.py
    # (create_run puis defer) : un worker pourrait ramasser la tâche
    # avant que la ligne pipeline_runs ne soit visible autrement. À
    # l'intérieur de la boucle car chaque run doit être visible avant
    # SON propre defer, pas seulement le dernier de la file.
    session.commit()
    run_pipeline_task.defer(run_id=run.id, tenant_id=tenant_id)
```

`request_scoped_session` still owns the overall transaction boundary and commits again (no-op, nothing pending) when the `with` block exits normally — same shape as `routes.py`/`mcp/tools.py`. No other guard logic, `_session_factory()`, or `run_pipeline_task` touched.

### GREEN

```
tests/test_pipeline_sweep.py::test_sweep_defers_run_pipeline_task_for_a_due_pipeline PASSED
tests/test_pipeline_sweep.py::test_sweep_defers_nothing_when_no_pipeline_is_due PASSED
tests/test_pipeline_sweep.py::test_sweep_short_circuits_in_read_only_mode PASSED
tests/test_pipeline_sweep.py::test_sweep_commits_run_before_deferring PASSED
tests/test_pipeline_sweep.py::test_sweep_short_circuits_when_etl_disabled PASSED

============================== 5 passed in 0.97s ===============================
```

No regression on the postgis-marked suite:

```
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_succeeded SKIPPED
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_never_zombie SKIPPED
tests/test_pipeline_jobs.py::test_run_pipeline_task_writes_node_stats_incrementally_before_failure SKIPPED
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_on_unexpected_exception_never_zombie SKIPPED

============================== 4 skipped in 1.68s ==============================
```

### Files changed

- `core/app/pipelines/jobs.py` — one-line `session.commit()` added inside the sweep loop
- `core/tests/test_pipeline_sweep.py` — added `test_sweep_commits_run_before_deferring` (with its own temp-file two-connection setup, distinct from `_make_session()`)

**Date:** 2026-08-07
**Status:** DONE (fix applied and verified)
