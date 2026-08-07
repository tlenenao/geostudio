# Task 3 Report: `POST /collections/{id}/export` (aggregate mode, collection-backed)

## Summary

Implemented the new `POST /collections/{collection_id}/export?format=csv|xlsx` route in
`core/app/features/routes.py`, reusing `run_collection_aggregate`/`AggregateRequestBody`/
`get_readable_collection` (all pre-existing) plus the Task 2 serialization module
`app.analytics.export` (`EXPORT_MEDIA_TYPES`, `export_filename`, `rows_to_format`,
`features_to_format`). Followed the brief's Step 1b corrected fixture/test (7-tuple `env`
fixture returning the `Session` factory, real-session audit-log assertion) rather than the
broken initial Step 1 version.

## What I implemented

- `core/app/features/routes.py`:
  - Import line broadened: `from app.analytics.export import EXPORT_MEDIA_TYPES,
    export_filename, features_to_format, rows_to_format` (`features_to_format` isn't used by
    this route yet — it's consumed by Task 4's raw-features export route added to the same
    file later in the plan; importing it now matches the brief's Step 3 instruction verbatim).
  - `RESERVED_QUERY_PARAMS` gained `"format"` so it isn't treated as an attribute filter by
    `_collect_filters` (not directly exercised by this route, but shared module state with
    `list_features`).
  - New `EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}` and
    `export_collection_aggregate()` route: validates `format`, resolves the collection via
    `get_readable_collection` (404-before-403 semantics — see Self-review below), introspects
    the table, runs the aggregate via `run_collection_aggregate`, serializes with
    `rows_to_format`, writes an `export.run` audit row, and returns a `Response` with
    `Content-Disposition: attachment`.

- `core/tests/test_features_export_routes.py` (new, 6 tests): mirrors
  `test_features_aggregate_routes.py`'s fixture, using the Step 1b corrected `env` fixture
  (7-tuple, includes the `Session` factory).

## Deviation from the brief (found and fixed before implementing)

`test_export_aggregate_denies_a_user_without_read_access` in both the task brief and the
plan document (`docs/superpowers/plans/2026-08-07-sp16a-export-serveur.md`) asserts
`status_code == 403` for a non-owner hitting a private collection. That contradicts the
actual, reused-verbatim permission check: `get_readable_collection`
(`core/app/collections/routes.py:133-151`) is deliberately **404-before-403** — its docstring
reads "404 avant 403 : une collection illisible est indistinguable d'une absente" — and the
sibling test for the existing `/aggregate` route
(`test_aggregate_on_private_collection_by_non_owner_returns_404` in
`test_features_aggregate_routes.py`) already encodes this as 404, not 403. The plan itself
also says (Task 3 preamble, plan line 17): "Reuse existing permission checks verbatim — no
new authorization logic." Implementing a 403 would have required inventing a new check that
contradicts the stated design and the plan's own instruction.

I fixed the assertion in my test file to expect **404** (with a comment explaining why),
matching real system behavior. I did not touch the brief/plan files themselves (out of scope
for this task; flagging here for whoever compiles the final report/reviews the plan).

## Tests and results

Ran `cd core && uv run pytest tests/test_features_export_routes.py -v`.

### RED (before Step 3 — route did not exist)

```
tests/test_features_export_routes.py::test_export_aggregate_csv_returns_a_csv_attachment FAILED
tests/test_features_export_routes.py::test_export_aggregate_xlsx_returns_an_xlsx_attachment FAILED
tests/test_features_export_routes.py::test_export_aggregate_rejects_unknown_format FAILED
tests/test_features_export_routes.py::test_export_aggregate_requires_authentication FAILED
tests/test_features_export_routes.py::test_export_aggregate_denies_a_user_without_read_access PASSED
tests/test_features_export_routes.py::test_export_aggregate_writes_an_audit_log_row FAILED
5 failed, 1 passed in 4.05s
```

(The one "pass" is a coincidence: with no route registered, FastAPI returns 404 for any
path/method combination, and 404 happens to be exactly what that particular test expects —
confirming it was asserting the right thing for the wrong reason at RED, and the right thing
for the right reason at GREEN.)

### GREEN (after Step 3)

```
tests/test_features_export_routes.py::test_export_aggregate_csv_returns_a_csv_attachment PASSED
tests/test_features_export_routes.py::test_export_aggregate_xlsx_returns_an_xlsx_attachment PASSED
tests/test_features_export_routes.py::test_export_aggregate_rejects_unknown_format PASSED
tests/test_features_export_routes.py::test_export_aggregate_requires_authentication PASSED
tests/test_features_export_routes.py::test_export_aggregate_denies_a_user_without_read_access PASSED
tests/test_features_export_routes.py::test_export_aggregate_writes_an_audit_log_row PASSED
6 passed in 2.71s
```

Also ran the full suite to check for regressions: `cd core && uv run pytest -q` →
`1192 passed, 131 skipped in 76.61s` (skips are the pre-existing postgis-marked tests, per
CLAUDE.md). And `uv run lint-imports` → `layered architecture KEPT` (the new
`app.features → app.analytics.export` dependency doesn't break the import-linter contract;
`app.features` already depended on `app.analytics` via `aggregate`/`sql_sandbox`).

## Files changed

- `core/app/features/routes.py` (modified)
- `core/tests/test_features_export_routes.py` (new)

Commit: `684379e feat(core): SP-16a — POST /collections/{id}/export (mode agrégé CSV/XLSX)`

## Self-review

- **Completeness**: all 6 tests from the corrected Step 1b version are present and pass; the
  route matches the brief's Step 3 code exactly except for the one status-code fix above.
- **Quality**: route mirrors `aggregate_features` closely (same dependency shapes, same
  try/finally on `conn.close()`, same `_validation_error` helper for 400s). Renamed the
  aggregate's `category_key` local to `_category_key` since the export route doesn't need it
  in the response — kept as a bound name (not `_`) for clarity in case of future debugging,
  matching the brief's own code.
- **Discipline**: no new imports beyond exactly what the brief's Step 3 specifies; no
  restructuring elsewhere in the file; didn't touch Task 4's future work.
- **Testing**: tests exercise a real SQLite-backed session, a real DuckDB in-memory
  connection with the `spatial` extension loaded, and real Parquet partitions written via
  geopandas — no mocks. Output is clean at the passing run (no warnings); the RED run's
  captured stderr/stdout noise (an `AppNotOpen` procrastinate traceback from the collection
  registration's best-effort embedding enqueue) is pre-existing and identical to what
  `test_features_aggregate_routes.py` also produces on failure output — unrelated to this
  change, and pytest only captures/prints it for failing tests.

## Issues or concerns

- The one test-assertion fix (403 → 404) described above is a deviation from the literal
  brief/plan text. I'm confident in it (deliberate, documented design decision + existing
  sibling test + the plan's own "reuse verbatim" instruction all agree), but flagging clearly
  since the task description said to follow the brief's Step 1b text precisely — this is the
  one place I did not.
- `features_to_format` is imported but unused by this route (by design — Task 4 will use it
  in the same file). No lint tool (ruff/flake8) is installed in this environment to confirm
  it wouldn't be flagged as an unused import in CI; `lint-imports` (the import-linter layering
  check mentioned in CLAUDE.md) passes, which is the lint gate actually documented for this
  repo.
