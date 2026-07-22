# Task 3 Report: Repository `harvest_sources`/`harvest_records` (SP-12c)

## Implementation

Created `core/app/harvest/repository.py` implementing CRUD for `HarvestSource`/
`HarvestRecord` (models landed in Task 1) exactly per the brief's verbatim code:

- `create_source`/`get_source`/`list_sources`/`update_source`/`delete_source`
- `mark_running` (sets `last_status="running"` for a given tenant/source, no-op
  if source not found)
- `get_record`/`create_record`/`update_record`
- `mark_missing_as_stale(session, *, tenant_id, source_id, seen_external_ids)` —
  flips `is_stale=True` on records of that source whose `external_id` is not in
  the seen set (idempotent: skips records already stale)
- `list_due_sources(session)` — global scan (no tenant filter, matches the
  brief's interface `list_due_sources(session) -> list[HarvestSource]`) of
  enabled sources with a non-null `interval_minutes`, due if `last_run_at is
  None` or `last_run_at + interval_minutes <= now`

Created `core/tests/test_harvest_repository.py` verbatim from the brief: 7
always-run tests against SQLite in-memory (`app.db.make_engine("sqlite+pysqlite
:///:memory:")` + `init_db`), plus 1 `@pytest.mark.postgis` test using the
repo's existing `pg_engine` fixture (from `tests/conftest.py`), which asserts
the DB-level unique constraint `uq_harvest_records_tenant_source_external`
(declared on `HarvestRecord` in Task 1) raises `IntegrityError` on a duplicate
`(tenant_id, source_id, external_id)` insert — real-Postgres-only per the
brief, marked `postgis` and skipped by default.

## TDD evidence

### RED (Step 2)

```
$ cd core && uv run pytest tests/test_harvest_repository.py -v
...
ImportError: cannot import name 'repository' from 'app.harvest'
(/home/lenen/projets/geostudio/core/app/harvest/__init__.py)
=========================== short test summary info ============================
ERROR tests/test_harvest_repository.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.10s ===============================
```

(`ImportError` rather than literally `ModuleNotFoundError` because the parent
package `app.harvest` already exists from Task 1/2 — only the submodule
`repository` was missing. Same root cause the brief anticipated: the file
didn't exist yet.)

### GREEN (Step 4)

```
$ cd core && uv run pytest tests/test_harvest_repository.py -v
...
tests/test_harvest_repository.py::test_create_get_list_source PASSED     [ 12%]
tests/test_harvest_repository.py::test_get_source_cross_tenant_returns_none PASSED [ 25%]
tests/test_harvest_repository.py::test_update_source_patches_fields PASSED [ 37%]
tests/test_harvest_repository.py::test_delete_source_cascades_to_records PASSED [ 50%]
tests/test_harvest_repository.py::test_mark_running_sets_status PASSED   [ 62%]
tests/test_harvest_repository.py::test_mark_missing_as_stale_flags_unseen_records_only PASSED [ 75%]
tests/test_harvest_repository.py::test_list_due_sources_includes_never_run_and_overdue_enabled_sources PASSED [ 87%]
tests/test_harvest_repository.py::test_unique_constraint_rejects_duplicate_external_id_for_same_source SKIPPED [100%]

========================= 7 passed, 1 skipped in 0.16s =========================
```

Matches the brief's expected result exactly: 7 passed, 1 skipped (no
`CORE_TEST_DATABASE_URL` in this environment — Step 5's real-Postgres
validation was not run, consistent with the task instructions: "do not try to
make it run unless a disposable Postgres is available").

### Regression check (full core suite)

```
$ cd core && uv run pytest -q
627 passed, 88 skipped in 36.11s
```

No regressions.

### Import-linter (module boundaries)

```
$ cd core && uv run lint-imports
Analyzed 107 files, 256 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

## Files changed

- `core/app/harvest/repository.py` (new) — first line `# SPDX-License-Identifier: Apache-2.0`
- `core/tests/test_harvest_repository.py` (new)

## Commit

```
534c3b6 feat(core): CRUD harvest_sources/harvest_records + due-sources (SP-12c)
 2 files changed, 307 insertions(+)
```

Only these two files were staged/committed (verified via `git status` before
committing) — the working tree has numerous unrelated pre-existing
uncommitted changes from other sessions/tasks, left untouched.

## Self-review

- Followed the brief's code verbatim (interfaces, test bodies, docstring-level
  behavior) — no deviation needed.
- Confirmed the module's only dependency is `app.harvest.models`
  (`HarvestRecord`, `HarvestSource`) — `lint-imports` confirms no contract
  breakage (`app.harvest` layering unaffected).
- All queries in the repository filter on `tenant_id` (tenant-scoped by
  construction), consistent with the project's tenant-isolation discipline
  elsewhere, even though RLS policies for these tables are out of scope for
  this task (owned by Tasks 1/2's schema/migration).
- Verified the `mark_missing_as_stale` idempotence guard
  (`not record.is_stale`) doesn't change test-observable behavior vs. an
  unconditional set — it's a no-op optimization, matches the brief's code
  exactly.

## Concerns

- None. Only the 1 `@pytest.mark.postgis` test is unverified against a real
  Postgres in this session (no `CORE_TEST_DATABASE_URL`, no disposable
  Postgres spun up) — expected and explicitly permitted by the task
  instructions. The unique-constraint behavior it covers is a straightforward
  DB-level constraint already declared in Task 1/2's migration; nothing here
  suggests risk.

## Review fix (post-commit, follow-up to 534c3b6)

**Finding (Critical, reproduced empirically)**: `list_due_sources` crashed
with `TypeError: can't compare offset-naive and offset-aware datetimes` on
its first real invocation against any source that had already run once.

**Root cause**: `last_run_at` is a naive `DateTime()` column. The original
test only ever read `last_run_at` off the *same in-memory object* it had
just assigned in the same session — SQLAlchemy's identity map returns that
same tz-aware Python object without re-deserializing from the DB. A real
scheduler runs `list_due_sources` in a fresh session/query against sources
that were updated by a previous (different) job invocation, so
`source.last_run_at` comes back tz-**naive** from the DB while `_now()`
(kept tz-aware, per codebase convention) stays tz-aware — comparing the two
in `threshold <= now` raised the `TypeError`.

**Fix** (`core/app/harvest/repository.py`, `list_due_sources` only — no
column/migration change): normalize `last_run_at` to aware-UTC
(`.replace(tzinfo=timezone.utc)` when `.tzinfo is None`) before computing
`threshold` and comparing to `now`. Comment explains why. No signature or
other function touched.

**Regression test** (`core/tests/test_harvest_repository.py`,
`test_list_due_sources_includes_never_run_and_overdue_enabled_sources`):
changed the trailing `session.flush()` to `session.commit()` and added
`session.expire_all()` immediately before calling `repo.list_due_sources`,
forcing `last_run_at` to be re-deserialized (naive) from the DB instead of
returning the same in-memory aware object — this is exactly the cold-fetch
path a real scheduler (fresh session per job) takes. Existing assertions
(`due_ids == {never_run.id, overdue.id}`, `fresh.id not in due_ids`) kept
unchanged.

Confirmed the test fails against pre-fix code with the exact reported
error (verified by `git stash`-ing only the repository.py fix and
re-running):

```
$ uv run pytest tests/test_harvest_repository.py::test_list_due_sources_includes_never_run_and_overdue_enabled_sources -v
...
    threshold = source.last_run_at + timedelta(minutes=source.interval_minutes)
>   if threshold <= now:
E   TypeError: can't compare offset-naive and offset-aware datetimes
=========================== short test summary info ============================
FAILED tests/test_harvest_repository.py::test_list_due_sources_includes_never_run_and_overdue_enabled_sources
============================== 1 failed in 0.12s ===============================
```

Post-fix:

```
$ cd core && uv run pytest tests/test_harvest_repository.py -v
...
tests/test_harvest_repository.py::test_create_get_list_source PASSED     [ 12%]
tests/test_harvest_repository.py::test_get_source_cross_tenant_returns_none PASSED [ 25%]
tests/test_harvest_repository.py::test_update_source_patches_fields PASSED [ 37%]
tests/test_harvest_repository.py::test_delete_source_cascades_to_records PASSED [ 50%]
tests/test_harvest_repository.py::test_mark_running_sets_status PASSED   [ 62%]
tests/test_harvest_repository.py::test_mark_missing_as_stale_flags_unseen_records_only PASSED [ 75%]
tests/test_harvest_repository.py::test_list_due_sources_includes_never_run_and_overdue_enabled_sources PASSED [ 87%]
tests/test_harvest_repository.py::test_unique_constraint_rejects_duplicate_external_id_for_same_source SKIPPED [100%]

========================= 7 passed, 1 skipped in 0.16s =========================
```

Same result as before the fix (7 passed, 1 skipped) — the postgis test
still skips without `CORE_TEST_DATABASE_URL`, as expected; no regression
introduced, the previously-latent crash is now exercised and fixed.

### Files changed

- `core/app/harvest/repository.py` — `list_due_sources` tz-normalization
- `core/tests/test_harvest_repository.py` — cold-fetch regression coverage

### Commit

```
<filled in after commit — see below>
```
