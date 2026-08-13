# Task 6 report: `ReportRun` model + migration

## What I implemented

- `core/app/reports/__init__.py` — empty marker module (SPDX header only),
  new `app.reports` module.
- `core/app/reports/models.py` — `ReportRun` SQLAlchemy model, table
  `report_runs`: `id` (PK, str), `tenant_id` (SQL FK → `tenants.id`),
  `report_item_id` (SQL FK → `items.id`), `export_job_id` (plain `String`,
  **no SQL FK** to `export_jobs.id` — documented in-line: `app.export` sits
  below `app.reports` in the layer contract, so `export_jobs` rows are
  looked up by id via `export_repo.get_job` at read time, never joined in
  SQL, same discipline as `pipeline_runs`/`get_latest_run`), `notified_at`
  (nullable `DateTime`, defaults to `None`), `created_at` (`DateTime`,
  server-side default via `_now()` returning UTC).
- `core/alembic/versions/0023_report_runs.py` — migration `0022 -> 0023`
  creating `report_runs` with the same columns/FKs as the model, plus index
  `ix_report_runs_tenant_id` on `(tenant_id, id)`. `downgrade()` drops the
  index then the table.
- `core/tests/test_report_models.py` — TDD test verifying a `ReportRun` row
  persists with `notified_at` defaulting to `None` and `created_at` set,
  against an in-memory SQLite engine wired through `init_db`/tenant/user/
  items repositories (mirrors the pattern used by sibling model tests).

Exact code matches the brief verbatim (Steps 1, 3, 5).

## What I tested and results

### TDD (RED then GREEN)

RED — before creating `app/reports/`:
```
$ uv run pytest tests/test_report_models.py -v
...
ImportError while importing test module '/home/lenen/projets/geostudio/core/tests/test_report_models.py'.
tests/test_report_models.py:4: in <module>
    from app.reports.models import ReportRun
E   ModuleNotFoundError: No module named 'app.reports'
=========================== short test summary info ============================
ERROR tests/test_report_models.py
=============================== 1 error in 0.71s ===============================
```
Failed for the expected reason.

GREEN — after creating `__init__.py` + `models.py`:
```
$ uv run pytest tests/test_report_models.py -v
tests/test_report_models.py::test_report_run_persists_and_defaults_notified_at_to_none PASSED [100%]
============================== 1 passed in 0.77s ===============================
```
Pristine — no warnings, no unexpected stderr, 1 passed.

### Alembic chain sanity

```
$ uv run alembic heads
0023 (head)
$ uv run alembic history | head -5
0022 -> 0023 (head), app.reports — report_runs (SP-17b)
0021 -> 0022, app.export — export_jobs.page_id / export_jobs.ctx (SP-17b)
0020 -> 0021, app.export — export_jobs (SP-17a)
0019 -> 0020, app.alerts — alert_evaluations (SP-16b)
0018 -> 0019, app.secrets — connector_secrets (SP-15e)
```
Single head, chain consistent — no branching.

### Real-Postgres migration verification (disposable container
`gis:gis@localhost:55432/gis_migcheck`, confirmed pre-seeded at `0022 (head)`
before starting)

Pre-check:
```
$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55432/gis_migcheck uv run alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0022 (head)
```

Upgrade to head:
```
$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55432/gis_migcheck uv run alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 0022 -> 0023, app.reports — report_runs (SP-17b)
```
No error. Ended at `0023 (head)`.

Downgrade / re-upgrade round-trip:
```
$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55432/gis_migcheck uv run alembic downgrade -1
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 0023 -> 0022, app.reports — report_runs (SP-17b)

$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55432/gis_migcheck uv run alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 0022 -> 0023, app.reports — report_runs (SP-17b)

$ DATABASE_URL=postgresql+psycopg://gis:gis@localhost:55432/gis_migcheck uv run alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0023 (head)
```
Clean round-trip: downgrade dropped the index and table without error,
re-upgrade recreated them, ended at `0023 (head)`.

## Files changed

- `core/app/reports/__init__.py` (new)
- `core/app/reports/models.py` (new)
- `core/alembic/versions/0023_report_runs.py` (new)
- `core/tests/test_report_models.py` (new)

Commit: `5ce6a76 feat(core): report_runs table (SP-17b)` — exactly these 4
files, matching the brief's Step 7 file list and message.

## Self-review findings

- Model matches brief verbatim; `export_job_id` correctly has **no** SQL FK
  to `export_jobs.id`, with the layer-contract rationale preserved in the
  in-line comment.
- Migration matches brief verbatim; upgrade/downgrade both verified against
  real Postgres in both directions (not just SQLite via the model test).
- Test output pristine both RED and GREEN.
- `core/pyproject.toml` not touched — confirmed via `git diff
  core/pyproject.toml` (empty) before committing; `app.reports` wiring into
  the import-linter layer contract is explicitly out of scope for this task
  (Task 12's job).
- `git status --short core/` before staging showed only the 4 new files
  under `core/` as untracked — nothing else in `core/` was modified by this
  work.
- Pre-existing unstaged changes in `.superpowers/sdd/*` (task 1-6 briefs/
  reports, progress.md) and untracked docs under `docs/superpowers/` belong
  to other tasks/sessions and were deliberately left untouched — only the
  4 intended files were `git add`ed and committed.

## Issues or concerns

None. No blockers encountered; the disposable Postgres container was
reachable throughout, confirmed at `0022 (head)` before starting, and
behaved as documented in both directions.
