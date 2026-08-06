# Task 3 report — Data model + migration (`connector_secrets`)

## What I implemented

- `core/app/secrets/models.py` — SQLAlchemy model `ConnectorSecret` mapped to
  table `connector_secrets`: `id` (PK), `tenant_id` (FK `tenants.id`), `name`,
  `kind`, `ciphertext` (`LargeBinary`), `nonce` (`LargeBinary`), `created_by`
  (FK `users.id`), `created_at`/`updated_at` (`DateTime`, UTC defaults via
  `_now()`), unique constraint `uq_connector_secrets_tenant_name` on
  `(tenant_id, name)`.
- `core/alembic/versions/0019_connector_secrets.py` — migration creating the
  `connector_secrets` table, `down_revision = "0018"` (confirmed `0018` is
  the current head), mirrors the model schema, `downgrade()` drops the table.
- `core/app/db.py` — registered `from app.secrets import models as
  secrets_models  # noqa: F401` in `core_table_names()`, inserted
  alphabetically between `app.pipelines` and `app.sharing`, exactly as the
  brief specified.
- `core/pyproject.toml` — added `"app.db -> app.secrets.models",` to the
  `ignore_imports` list in the `[[tool.importlinter.contracts]]` block,
  mirroring the 10 existing per-module exemptions.
- `core/tests/test_secrets_models.py` — the exact 3-test file from the brief
  (table registration, row round-trip, unique-per-tenant constraint).

Transcribed verbatim from the brief; no design decisions made.

## TDD evidence

**RED** — before creating `models.py`:
```
$ cd core && uv run pytest tests/test_secrets_models.py -v
...
ImportError while importing test module '.../tests/test_secrets_models.py'.
E   ModuleNotFoundError: No module named 'app.secrets.models'
Interrupted: 1 error during collection
```
Matches the brief's expected failure exactly.

**GREEN** — after implementing `models.py`, `db.py`, `pyproject.toml`, and the
migration:
```
$ cd core && uv run pytest tests/test_secrets_models.py -v
tests/test_secrets_models.py::test_connector_secrets_table_is_registered PASSED [ 33%]
tests/test_secrets_models.py::test_connector_secret_row_round_trip PASSED [ 66%]
tests/test_secrets_models.py::test_connector_secret_unique_name_per_tenant PASSED [100%]
3 passed in 0.16s
```

**Import-linter**:
```
$ cd core && uv run lint-imports
Analyzed 142 files, 401 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

**Full suite regression check** (not required by the brief, ran as extra
diligence):
```
$ cd core && uv run pytest -q
1051 passed, 127 skipped in 68.23s
```
No regressions; skip count matches the usual postgis/qgis-marked baseline.

## Files changed

- `core/app/secrets/models.py` (new)
- `core/alembic/versions/0019_connector_secrets.py` (new)
- `core/app/db.py` (modified — 1 line added)
- `core/pyproject.toml` (modified — 1 line added)
- `core/tests/test_secrets_models.py` (new)

Commit: `58e4276` — `feat(core): secrets module — connector_secrets table + migration`
(5 files changed, 127 insertions(+))

## Self-review findings

- Content matches the brief verbatim in all four code files — diffed
  mentally against the brief's fenced blocks, no deviations.
- `db.py` insertion point confirmed correct before editing: read the
  surrounding `core_table_names()` function first, found `pipelines_models`
  and `sharing_models` exactly where the brief said, inserted between them.
- `0018` confirmed as the actual alembic head (`down_revision = "0018"` in
  `0018_pipeline_runs.py`) before writing `0019`'s `down_revision`.
- Nothing else touched: `git status --short core/` before commit showed only
  the 5 intended files; `git add` listed them explicitly (no `-A`/`.`).
- No destructive git commands used; untouched `.superpowers/sdd/*` working-
  tree modifications (pre-existing, unrelated to this task) were left alone
  per instructions.
- Scope discipline: no other model, migration, or module touched; Task 4/5
  concerns (repository, routes, admin gate) not started.

## Issues or concerns

None. All steps in the brief completed exactly as specified, tests pass
cleanly (3/3 target tests, 1051/1051 non-skipped in the full suite), and
`lint-imports` is clean.
