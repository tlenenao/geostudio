# Task 12 report — Wire `app.reports` into the worker, the API app, and the layer contract

## What I implemented

The three edits from the brief, plus one edit not mentioned in the brief but
required for it to actually work (see "Deviation from brief" below):

1. **`core/app/jobs.py`** — added `"app.reports.jobs"` to the procrastinate
   `App`'s `import_paths` list (after `"app.export.jobs"`), so the standalone
   worker process (which only imports `app.jobs` to resolve `app.jobs.app`)
   picks up `sweep_report_schedules_task`.

2. **`core/app/main.py`** — added `from app.reports import routes as
   reports_routes` next to the other domain route imports, and mounted
   `app.include_router(reports_routes.router)` unconditionally, right after
   `alerts_routes.router` and before the `is_etl_enabled()` gate — mirrors
   `alerts_routes`, not `pipelines_routes`/`export_routes`. No capability
   flag: a `ReportSchedule` can be created/listed/inspected even with
   `CORE_EXPORT_ENABLED=false`, it just fails cleanly at render time.

3. **`core/pyproject.toml`** — inserted `"app.reports",` into the
   `[tool.importlinter]` `layers` list between `"app.pipelines",` and
   `"app.alerts",`, and added `"app.db -> app.reports.models",` to
   `ignore_imports`, next to the existing `"app.db -> app.export.models",`
   line.

4. **`core/app/db.py`** (not in the brief's file list — see below) — added
   `from app.reports import models as reports_models  # noqa: F401` to
   `core_table_names()`, in alphabetical position between `app.pipelines`
   and `app.secrets`, matching every other domain module already there.

## Deviation from brief

The brief's Step 3 says to add the `ignore_imports` entry `"app.db ->
app.reports.models"` "same reason as every other domain-models exception in
that list" — but it does not list `core/app/db.py` as a file to modify, and
does not mention adding the corresponding import there.

Running `lint-imports` right after making exactly the three specified edits
failed:

```
No matches for ignored import app.db -> app.reports.models.
```

I checked: every one of the 14 pre-existing `"app.db -> app.X.models"`
entries in `ignore_imports` has a matching `from app.X import models as
X_models  # noqa: F401` line inside `core_table_names()` in `core/app/db.py`
— that's what the entry is *for* (import-linter's `ignore_imports` only
accepts entries that match a real edge in the import graph; an entry with no
matching import is itself an error, not a no-op). `app.reports.models` had
no such import anywhere reachable before `create_all()`/`lint-imports`
analysis, so the new `ignore_imports` line had nothing to match.

This also has a real functional consequence beyond lint: `init_db()`
(`core/app/db.py`) calls `core_table_names()` then, for SQLite, `
Base.metadata.create_all(engine)`. Without something importing
`app.reports.models` before that call, `ReportRun`'s table would never
register on `Base.metadata` and would silently not get created in the
SQLite/test path — except that in practice every existing `test_report_*.py`
test happens to import `app.reports.routes`/`repository` (which transitively
import `app.reports.models`) at module level before calling `init_db()`, so
this particular gap was invisible in the current test suite. Wiring
`reports_routes` into `main.py` (Step 2) also happens to import
`app.reports.models` transitively before `create_app()`'s own `init_db()`
call, for the same reason — so production/`main.py` was accidentally safe
too. Adding the explicit import in `core_table_names()` removes this
implicit "someone else imports it first" dependency and makes
`app.reports.models` registration as robust as every other domain module's,
consistent with the established pattern (14/14 prior entries follow it).

This is a one-line, low-risk, mechanical fix that follows an existing,
unambiguous pattern repeated 14 times in the same function — I made the
edit rather than reporting BLOCKED.

## What I tested

1. `cd core && uv run lint-imports`
   ```
   Analyzed 170 files, 526 dependencies.
   layered architecture KEPT
   Contracts: 1 kept, 0 broken.
   ```
   No violation, in particular no complaint about `app.reports` importing
   `app.alerts.notify`/`app.export.repository`/`app.export.jobs`/
   `app.configs`/`app.items`/`app.sharing`/`app.audit`/`app.users`/`app.db`.

2. `cd core && uv run pytest tests/test_jobs.py -v`
   ```
   tests/test_jobs.py::test_jobs_app_is_a_procrastinate_app PASSED
   tests/test_jobs.py::test_ingestion_tasks_reuses_the_shared_app PASSED
   tests/test_jobs.py::test_import_paths_registers_all_domain_tasks PASSED
   3 passed in 2.53s
   ```
   `test_import_paths_registers_all_domain_tasks` runs the worker's
   `App.perform_import_paths()` in a fresh subprocess and verifies every
   domain task is registered — passes with `app.reports.jobs` now in the
   list.

3. `cd core && uv run pytest -q` (full suite)
   ```
   1359 passed, 137 skipped in 90.76s
   ```
   No regressions. All `postgis`-marked tests skipped (no
   `CORE_TEST_DATABASE_URL` locally) — expected.

## Files changed

- `core/app/jobs.py` — registered `app.reports.jobs` in `import_paths`.
- `core/app/main.py` — imported and unconditionally mounted
  `reports_routes.router` after `alerts_routes.router`.
- `core/pyproject.toml` — inserted `app.reports` into the import-linter
  `layers` list (between `app.pipelines` and `app.alerts`) and added the
  `app.db -> app.reports.models` `ignore_imports` entry.
- `core/app/db.py` — added `app.reports.models` import to
  `core_table_names()` (not in the brief's file list; required for the
  `ignore_imports` entry to match anything and for `ReportRun`'s table to
  register on `Base.metadata` independent of import order — see "Deviation
  from brief" above).

## Self-review

- All three edits from the brief made exactly as specified (plus the one
  necessary `db.py` addition, explained above).
- `lint-imports` passes clean.
- Full suite passes, no regressions (1359 passed, 137 skipped, same skip
  reason — no `CORE_TEST_DATABASE_URL` locally).
- Router mount is unconditional (no `is_etl_enabled()`/`is_export_enabled()`
  gate), confirmed by re-reading the diff: `reports_routes.router` sits
  right after `alerts_routes.router` and before the `if is_etl_enabled():`
  line, at the same indentation, with no `if` wrapping it.

## Concerns

None blocking. The one open item: the brief's Step 3 was incomplete (missing
the `db.py` companion import that every other domain-models `ignore_imports`
entry requires) — flagged above in detail so future task-brief authors for
this plan know to include the `db.py` edit alongside any new `ignore_imports`
entry.
