# Task 11 report — `GET /reports/{item_id}/runs`

## What I implemented

`core/app/reports/routes.py`: a single REST route module for `ReportSchedule`
run history, mirroring `GET /alerts/{id}/evaluations` (SP-16b). CRUD for the
`ReportSchedule` config itself remains entirely the generic `/configs` routes
(kind="report") — this module only adds the one bespoke read.

Contents, exactly per the brief's Step 3:
- `ReportRunStatus` Pydantic response model (`id`, `status`, `resultUrl`,
  `error`, `notifiedAt`, `createdAt`).
- `get_exports_bucket()` — a dependency-override seam reading
  `S3_EXPORTS_BUCKET` from the environment (mirrors `app.export.routes`'
  equivalent by name, not by import, keeping the two overridable
  independently in `app.main`).
- `_require_report_read_access()` — resolves `items_repo.get_access_facts`
  then `sharing.authorization.can(..., action="read", ...)`; raises 404 (not
  403) whenever the item doesn't exist or isn't readable, to avoid leaking
  existence.
- `get_report_runs_route()` — `GET /reports/{item_id}/runs`: checks access,
  lists runs via `reports_repo.list_runs`, resolves each run's joined
  `export_jobs` row via `export_repo.get_job`, and only builds a presigned
  download URL when the job is `status == "done"` and has a `result_key`.

The router is **not** mounted into `app.main` — that's explicitly Task 12's
job per the plan (`Task 12: Wire app.reports into the worker, the API app,
and the layer contract`), including inserting `"app.reports"` into the
import-linter layer contract. I left `core/pyproject.toml` untouched.

## What I tested and results (TDD evidence)

1. **RED**: Wrote `core/tests/test_report_routes.py` verbatim from the
   brief's Step 1 (two tests: happy path with a `done` export job resolving
   to a presigned URL, and a 404 for a report the caller can't read). Ran
   `uv run pytest tests/test_report_routes.py -v` — failed with
   `ModuleNotFoundError: No module named 'app.reports.routes'`, exactly as
   the brief predicted.
2. **GREEN**: Implemented `core/app/reports/routes.py` per Step 3. Re-ran the
   same command — both tests passed:
   ```
   tests/test_report_routes.py::test_get_report_runs_returns_run_with_resolved_status_and_url PASSED
   tests/test_report_routes.py::test_get_report_runs_404s_for_unreadable_report PASSED
   2 passed in 0.97s
   ```
3. **Regression check**: also ran the full report/export/alert test
   neighborhood (`test_report_*.py`, `test_export_routes.py`,
   `test_alert_routes.py`) — all 44 tests passed, output pristine (no
   warnings, no unexpected skips).

## Files changed

- `core/app/reports/routes.py` (new)
- `core/tests/test_report_routes.py` (new)

Commit: `3b9cc20 feat(core): GET /reports/{item_id}/runs (SP-17b)`

## Self-review findings

- 404 (not 403) confirmed for unreadable report: `_require_report_read_access`
  raises 404 uniformly whether the item is missing or merely unreadable —
  never distinguishes, so existence isn't leaked.
- Presigned URL generation confirmed gated on `job.status == "done" and
  job.result_key` — pending/error jobs get `resultUrl: null`.
- Test output pristine on both the new test file alone and the broader
  report/export/alert neighborhood.
- `core/app/main.py` and `core/pyproject.toml` (import-linter layers) left
  untouched, per the brief and the plan's explicit Task 12 scoping.

No defects found in the brief's prescribed code — implemented verbatim, all
pre-verified interfaces (`get_s3_client`, `generate_presigned_get_url`,
`export_repo.get_job`, `items_repo.get_access_facts`, `sharing.authorization
.can`, `reports_repo.list_runs`) matched their actual signatures exactly on
inspection before writing the test/implementation.

## Issues or concerns

None.
