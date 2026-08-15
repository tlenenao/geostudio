# Task 8 report — `build_app_export_task` branches on `mode="standalone"`

## What I did

Followed TDD per the brief:

1. Read `core/app/appexport/jobs.py` and `core/tests/test_appexport_jobs.py`
   to confirm current state before editing (the file to be replaced starts
   with an "SP-18a/b" docstring, no `standalone` mode support yet).
2. Verified the exact signatures of the two consumed functions against the
   real (already-merged) source:
   - `write_snapshot(session, *, tenant_id, config, snapshot_dir, max_records_per_source=50_000) -> list[CollectionSnapshotEntry]`
     in `core/app/appexport/snapshot.py`.
   - `build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes`
     in `core/app/appexport/bundler.py`.
   Both match the brief's call sites verbatim.
3. **Step 1** — Appended the two new tests
   (`test_standalone_job_with_no_data_sources_succeeds`,
   `test_standalone_job_with_private_source_marks_error`) to
   `core/tests/test_appexport_jobs.py`, verbatim from the brief.
4. **Step 2** — Ran `cd core && uv run pytest tests/test_appexport_jobs.py -v`
   *before* touching `jobs.py`. Result: all 7 tests passed, including both
   new ones — this is the empirical outcome the brief explicitly flagged as
   possible (the "wrong" static-fallback path succeeds for the no-sources
   case, and the private-source case is rejected by the guard before mode
   branching regardless of implementation). No regression signal expected
   at this point; the real check is Step 4.
5. **Step 3** — Replaced the full contents of `core/app/appexport/jobs.py`
   with the brief's verbatim text (via `Write`, after `Read`).
6. **Step 4** — Re-ran the same test file. All 7 passed again, this time
   exercising the real `mode == "standalone"` branch (`_build_zip_bytes`
   → `tempfile.TemporaryDirectory()` → `write_snapshot` →
   `build_standalone_bundle_zip`).
7. Ran the three dependency suites (Tasks 1/4/7) with a real Postgres to
   confirm imports pulled in by the full-file replacement of `jobs.py`
   still resolve and nothing broke:
   `CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5432/gis_test" uv run pytest tests/test_appexport_guard.py tests/test_appexport_snapshot.py tests/test_appexport_bundler.py -v`
   — found a locally running `ci-postgres` container already exposing
   `gis`/`gis`/`gis_test` on `localhost:5432` (matched the brief's fallback
   value exactly), used it instead of starting a new container.
8. Self-reviewed `git diff` for both files — matches the brief's intended
   change exactly, no stray edits.
9. Staged **only** `core/app/appexport/jobs.py` and
   `core/tests/test_appexport_jobs.py` explicitly (verified via
   `git status --short` before and after `git add` that no
   `.superpowers/sdd/*` scratch files were swept in — those were already
   modified in the working tree before I started, from the controller's
   session bookkeeping, and I left them untouched).
10. Committed as `1c13c7e`.

## Test output

### Run 1 — `core/tests/test_appexport_jobs.py` (sqlite in-memory, no
Postgres env needed — `_setup` uses `sqlite+pysqlite:///:memory:` directly)

Pre-implementation (Step 2, tests appended, `jobs.py` untouched):
```
tests/test_appexport_jobs.py::test_job_disabled_flag_marks_error PASSED
tests/test_appexport_jobs.py::test_job_succeeds_and_marks_done PASSED
tests/test_appexport_jobs.py::test_job_guard_rejection_marks_error PASSED
tests/test_appexport_jobs.py::test_connected_job_skips_freezing_and_embeds_core_base_url PASSED
tests/test_appexport_jobs.py::test_connected_job_with_private_source_marks_error PASSED
tests/test_appexport_jobs.py::test_standalone_job_with_no_data_sources_succeeds PASSED
tests/test_appexport_jobs.py::test_standalone_job_with_private_source_marks_error PASSED
============================== 7 passed in 0.99s ===============================
```
Both new tests passed *before* the implementation change — the empirical
outcome the brief called out as possible (unrecognized `mode` string falls
through to the `static`/`freeze_config` branch, which succeeds trivially
with no data sources present, and the guard rejects the private-source case
before mode branching is ever reached). Not a red flag; matches the brief's
Step 2 guidance exactly.

Post-implementation (Step 4, `jobs.py` replaced):
```
tests/test_appexport_jobs.py::test_job_disabled_flag_marks_error PASSED
tests/test_appexport_jobs.py::test_job_succeeds_and_marks_done PASSED
tests/test_appexport_jobs.py::test_job_guard_rejection_marks_error PASSED
tests/test_appexport_jobs.py::test_connected_job_skips_freezing_and_embeds_core_base_url PASSED
tests/test_appexport_jobs.py::test_connected_job_with_private_source_marks_error PASSED
tests/test_appexport_jobs.py::test_standalone_job_with_no_data_sources_succeeds PASSED
tests/test_appexport_jobs.py::test_standalone_job_with_private_source_marks_error PASSED
============================== 7 passed in 1.08s ===============================
```
All 7 passing, now genuinely exercising `write_snapshot` +
`build_standalone_bundle_zip` for the standalone mode.

### Run 2 — dependency suites (Tasks 1/4/7), real Postgres

`CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5432/gis_test" uv run pytest tests/test_appexport_guard.py tests/test_appexport_snapshot.py tests/test_appexport_bundler.py -v`

```
28 passed in 3.19s
```
All of `test_appexport_guard.py` (17), `test_appexport_snapshot.py` (4),
and `test_appexport_bundler.py` (7) pass — confirms the imports pulled into
the fully-replaced `jobs.py` (`build_standalone_bundle_zip`, `write_snapshot`)
still resolve correctly and nothing in those modules regressed.

## Deviations from the brief

None. Test code, implementation file content, and commit message are all
verbatim from the brief. The only judgment call was choosing to use the
already-running `ci-postgres` container (credentials `gis`/`gis`/`gis_test`
on `localhost:5432`, matching the brief's suggested
`CORE_TEST_DATABASE_URL` value exactly) instead of starting a new container
— purely an environment convenience, no effect on test content or code.

## Self-review notes

- Full-file `Write` diff (`git diff`) shows exactly the expected delta:
  docstring update (SP-18a/b → SP-18a/b/c, mentions standalone/GeoParquet/
  docker-compose.yml), new `tempfile` import and `write_snapshot`/
  `build_standalone_bundle_zip` imports, new `_build_zip_bytes` helper
  centralizing the mode dispatch, and the call site in
  `build_app_export_task` simplified to call `_build_zip_bytes` — no
  incidental changes to error handling, job status transitions, or the
  disabled-flag/missing-job early-return paths.
- `git status --short` before and after `git add` confirms the commit
  contains exactly `core/app/appexport/jobs.py` and
  `core/tests/test_appexport_jobs.py` — none of the pre-existing modified
  `.superpowers/sdd/*.md` bookkeeping files were staged or committed.
- Public signature of `build_app_export_task(job_id: str, tenant_id: str) -> None`
  unchanged, as required by the brief's "Produces" contract.
- No `@pytest.mark.postgis` marker was needed for
  `test_appexport_jobs.py` since its `_setup` fixture uses an in-memory
  sqlite engine directly, consistent with the brief's guidance to check
  fixture DB usage before assuming Postgres is required.

## Commit

`1c13c7e` — `feat(core): app export job branches on mode=standalone (SP-18c)`
