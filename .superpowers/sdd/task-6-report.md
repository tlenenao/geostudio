# Task 6 report — routes.py + jobs.py: env var wiring + algorithm catalogue resource

## What was implemented

1. Added `GET /pipelines/ops/qgis-algorithms` route in
   `core/app/pipelines/routes.py`, right after the existing
   `GET /pipelines/ops` route. It imports `QGIS_ALGORITHMS` from
   `app.pipelines.ops.qgis_algorithms` and returns it verbatim. Since it's
   registered on the same `router` as the rest of `app.pipelines.routes`,
   it inherits the existing `CORE_ETL_ENABLED` router mount/unmount gating
   with no extra code.
2. Threaded `QGIS_WORKER_URL`/`QGIS_WORKER_TIMEOUT_SECONDS` env vars (with
   the same defaults `""`/`600` as the underlying kwargs) through:
   - `preview_pipeline_route` in `core/app/pipelines/routes.py` → the
     `preview_pipeline(...)` call now passes `qgis_worker_url=` and
     `qgis_worker_timeout_seconds=`.
   - `run_pipeline_task` in `core/app/pipelines/jobs.py` → the
     `run_pipeline(...)` call now passes the same two kwargs.
3. Added the two tests specified by the brief to
   `core/tests/test_pipeline_routes.py`:
   `test_get_qgis_algorithms_returns_full_allowlist` and
   `test_get_qgis_algorithms_absent_when_etl_disabled`, both using the
   existing local `_make_app(monkeypatch, *, etl_enabled)` helper (the note
   about the helper's reference test being renamed to
   `test_get_pipelines_ops_returns_all_fifteen` was correct and didn't
   affect this task — the helper itself is untouched).

## TDD evidence

RED (before Step 3, route didn't exist):

```
tests/test_pipeline_routes.py::test_get_qgis_algorithms_returns_full_allowlist FAILED
tests/test_pipeline_routes.py::test_get_qgis_algorithms_absent_when_etl_disabled PASSED
...
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code
1 failed, 1 passed, 5 deselected in 1.64s
```

(The "absent when disabled" test trivially passed even before the route
existed, since a nonexistent route also 404s — expected, and it's the
"returns_full_allowlist" test that proves the RED state.)

GREEN (after Steps 3, 5, 6):

```
tests/test_pipeline_routes.py::test_get_qgis_algorithms_returns_full_allowlist PASSED
tests/test_pipeline_routes.py::test_get_qgis_algorithms_absent_when_etl_disabled PASSED
2 passed, 5 deselected in 1.55s
```

Full route/jobs test files (Step 7):

```
tests/test_pipeline_routes.py::test_pipelines_routes_absent_when_disabled PASSED
tests/test_pipeline_routes.py::test_get_pipelines_ops_returns_all_fifteen PASSED
tests/test_pipeline_routes.py::test_run_route_defers_job_and_returns_run_id PASSED
tests/test_pipeline_routes.py::test_preview_route_rejects_unknown_pipeline PASSED
tests/test_pipeline_routes.py::test_list_runs_route_rejects_unknown_pipeline PASSED
tests/test_pipeline_routes.py::test_get_qgis_algorithms_returns_full_allowlist PASSED
tests/test_pipeline_routes.py::test_get_qgis_algorithms_absent_when_etl_disabled PASSED
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_succeeded SKIPPED
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_never_zombie SKIPPED
tests/test_pipeline_jobs.py::test_run_pipeline_task_marks_run_failed_on_unexpected_exception_never_zombie SKIPPED
7 passed, 3 skipped in 2.28s
```

(The 3 skips are the pre-existing `postgis`-marked tests requiring docker,
unrelated to this task.)

Full core suite (`cd core && uv run pytest -q`):

```
1025 passed, 126 skipped in 62.40s (0:01:02)
```

Baseline stated in the task was 1023 passed / 126 skipped; result is 1025
passed (+2, matching the two new tests) / 126 skipped (unchanged) — no
collateral regressions.

## Files changed

- `core/app/pipelines/routes.py` — new import (`QGIS_ALGORITHMS`), new
  `GET /pipelines/ops/qgis-algorithms` route, two new kwargs on the
  `preview_pipeline(...)` call in `preview_pipeline_route`.
- `core/app/pipelines/jobs.py` — two new kwargs on the `run_pipeline(...)`
  call in `run_pipeline_task`.
- `core/tests/test_pipeline_routes.py` — two new tests appended, verbatim
  as specified in the brief.

Diff matches the brief's exact Step 3/5/6 code blocks, character for
character (verified via `git diff` before commit).

Commit: `1295502 feat(core): wire QGIS_WORKER_URL env + publish the algorithm catalogue resource` (3 files changed, 25 insertions, 0 deletions).

## Self-review

- Completeness: all 8 steps done — failing tests written, RED confirmed,
  route added, GREEN confirmed, both env-var threading sites updated, full
  route/jobs files re-run, full suite re-run, committed.
- Quality: implementation is byte-for-byte the code given in the brief's
  Steps 3/5/6 (import placement alphabetical among `app.pipelines.*`
  imports, route placed immediately after `GET /pipelines/ops` as
  instructed).
- Discipline: no files touched outside the three listed
  (`git status --short` shows only routes.py, jobs.py,
  test_pipeline_routes.py modified). No behavior change for pipelines
  without a `transform.qgis` node — confirmed by the unchanged pass/skip
  counts on `test_pipeline_routes.py`/`test_pipeline_jobs.py` and the full
  suite; existing tests don't set `QGIS_WORKER_URL`, so the two new kwargs
  resolve to `""`/`600`, identical to the kwargs' own defaults from Task 5.
- Testing: ran each test file in isolation and the full suite; output
  captured above is from real `uv run pytest` invocations, not fabricated.

## Issues or concerns

None. The task was a small, self-contained wiring task; brief's assumed
shapes for `GET /pipelines/ops`, `preview_pipeline_route`, and
`run_pipeline_task` all matched the actual code exactly, so no escalation
was needed.
