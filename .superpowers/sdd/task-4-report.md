# Task 4 report — `AlertEvaluation` model + migration

## What was implemented

- `core/app/alerts/__init__.py` (empty, SPDX header only) — new package.
- `core/app/alerts/models.py` — `AlertEvaluation` ORM model (table
  `alert_evaluations`), exactly as dictated in the brief: `id`, `tenant_id`
  (FK `tenants.id`), `alert_rule_item_id` (FK `items.id`), `value` (nullable
  float), `state`, `transitioned` (bool, default False), `error` (nullable
  string), `created_at` (default `_now()`). Style matches the sibling
  `app/pipelines/models.py` (same `_now()` helper pattern, same import
  layout).
- `core/alembic/versions/0020_alert_evaluations.py` — migration matching the
  model column-for-column, same shape as `0018_pipeline_runs.py`/
  `0019_connector_secrets.py` (added the SPDX header line the brief's
  snippet omitted, to match every other file in `alembic/versions/`).
- `core/tests/test_alert_models.py` — the round-trip test verbatim from the
  brief.

### Addendum 1 (user-approved): import-linter layers contract

Added `"app.alerts"` to `core/pyproject.toml`'s `[tool.importlinter]`
`layers` list, between `"app.pipelines"` and `"app.secrets"`, per the plan's
Global Constraints. Ran `uv run lint-imports` — first run **broke** two
different ways (see Self-review below), fixed, then confirmed 0 broken
contracts.

### Addendum 2 (found during verification, not in the brief): `app.db` registration

While verifying the brief's code against the current codebase, I checked
how other model modules become known to `Base.metadata` outside of the
test's own `from app.alerts.models import AlertEvaluation` import line.
`app/db.py::core_table_names()` explicitly imports every model module
(`app.audit.models`, `app.pipelines.models`, `app.secrets.models`, etc.) —
this is documented in its own docstring as "Source de vérité de la denylist
du registre de collections" and is exactly what `init_db()` relies on to
populate `Base.metadata` before `create_all()` on the SQLite path, and what
`app/collections/routes.py` uses as the denylist so a user-created
collection can't collide with a core table name.

The brief's test would still pass without this fix, because the test module
itself does `from app.alerts.models import AlertEvaluation` at import time,
which registers the model on `Base.metadata` as a side effect before
`init_db()` runs. But in any code path that reaches `init_db()`/
`core_table_names()` without first importing `app.alerts.models` directly
(any other test, any app startup path, the collections denylist check),
`alert_evaluations` would have been silently invisible — not created by
`create_all()` on SQLite, and not excluded from collection names. This is
the same class of "looks right in isolation, wrong once wired into the
whole app" gap the brief warned about for prior tasks (DuckDB sandbox
bypass in Task 1, discriminated-union gap in Task 2).

Fix: added `from app.alerts import models as alerts_models  # noqa: F401`
to `core_table_names()` in `app/db.py`, alphabetically before `app.audit`
(matches the existing alphabetical-ish ordering of that import block).

## What was tested and results

- RED: `PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run pytest -q tests/test_alert_models.py`
  → `ModuleNotFoundError: No module named 'app.alerts'` (collection error,
  1 error), confirmed before writing any implementation code.
- GREEN (same command after implementation): `1 passed in 0.41s`.
- Full non-postgis suite after all changes:
  `PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run pytest -q -m "not postgis"`
  → `1236 passed, 6 skipped, 125 deselected in 83.45s`. No regressions from
  the `app/db.py` edit.
- `uv run alembic heads` before writing the migration: `0019 (head)`,
  matching the brief and the dispatcher's confirmation. After adding the
  migration: `uv run alembic heads` → `0020 (head)`.
- `uv run lint-imports`: first run after adding `"app.alerts"` to `layers`
  **broke** 6+ contracts (`app.items`/`app.extensions`/`app.auth`/
  `app.sharing`/`app.features`/`app.stac` "not allowed to import
  app.alerts", all routed through `app.db -> app.alerts.models`) — because
  `core_table_names()` now imports `app.alerts.models`, and every module
  transitively imports `app.db`. This exact pattern already exists for
  every other model module (`app.db -> app.pipelines.models`, `app.db ->
  app.secrets.models`, etc.) via an `ignore_imports` allowlist. Added
  `"app.db -> app.alerts.models"` to that list. Re-ran: `Contracts: 1 kept,
  0 broken.`
- Real Postgres migration apply: `docker compose ps` showed no running
  containers (no `.env`, all vars defaulting blank, no services listed) —
  did not start new services per instructions. Not run; covered by the
  `postgis`-marked CI job per the brief's stated caveat, same as prior
  migrations in this repo.

## TDD Evidence

RED:
```
ImportError while importing test module '.../tests/test_alert_models.py'.
E   ModuleNotFoundError: No module named 'app.alerts'
1 error in 0.10s
```

GREEN:
```
tests/test_alert_models.py .                                          [100%]
1 passed in 0.41s
```

## Files changed

- `core/app/alerts/__init__.py` (new)
- `core/app/alerts/models.py` (new)
- `core/alembic/versions/0020_alert_evaluations.py` (new)
- `core/tests/test_alert_models.py` (new)
- `core/app/db.py` (1-line addition: register `app.alerts.models` in
  `core_table_names()`)
- `core/pyproject.toml` (2-line addition: `"app.alerts"` in the layers list;
  `"app.db -> app.alerts.models"` in `ignore_imports`)

## Self-review findings

- **Model vs. migration**: column-for-column match confirmed by inspection
  (types, nullability, FKs, default handling — `transitioned` uses
  `server_default=sa.false()` in the migration matching the Python-side
  `default=False`, same pattern as no other boolean column in this repo
  needed to diverge from).
- **Style**: matches `app/pipelines/models.py` (`_now()` helper, import
  ordering, `Mapped`/`mapped_column` conventions). No fields added beyond
  the brief.
- **Discipline**: did not add anything beyond the brief's model/migration
  except the two addenda explicitly scoped (import-linter layers entry,
  user-approved; `app.db` registration, self-found and justified above).
  Did not touch `app/alerts/repository.py` or anything belonging to Task 5.
- **Testing**: the test genuinely exercises persistence — two separate
  `Session()` contexts (write-then-commit, then a fresh session to reload
  by primary key), not just in-memory construction. Confirmed it fails for
  the right reason (`ModuleNotFoundError`, not some unrelated setup error)
  before implementing.
- **Import-linter**: verified the *before* state of `pyproject.toml` matched
  the dispatch description exactly before editing, and verified the
  contract still holds (`1 kept, 0 broken`) after — not just "no error",
  actually inspected the failure output on the first attempt to understand
  *why* it broke rather than reflexively adding an ignore rule.

## Issues or concerns

- None blocking. The one non-trivial judgment call was fixing the
  `core_table_names()` gap (Addendum 2) — it wasn't in the brief or the
  dispatcher's explicit addendum, but leaving it out would have produced a
  model that passes its own test while being invisible to the rest of the
  app's table-name bookkeeping. Flagging clearly here in case a reviewer
  disagrees with in-scope-ness; it's a 1-line, low-risk, immediately
  necessary correctness fix and easy to revert independently if desired
  (`core/app/db.py`, one `noqa: F401` import line).
- Real-Postgres `alembic upgrade head` was not exercised (no stack running,
  consistent with the brief's stated caveat and the existing CLAUDE.md note
  that this repo's default compose Postgres volume has a pre-existing,
  unrelated `alembic_version` stamping problem).
