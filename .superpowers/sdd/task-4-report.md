# Task 4 report — GET /collections/{id}/export/items (raw-entities mode)

## What was implemented

- `core/app/features/routes.py`: added `EXPORT_FORMATS_ITEMS`, `EXPORT_ITEMS_CAP = 10_000`,
  and the route `GET /collections/{collection_id}/export/items?format=csv|xlsx|geojson|gpkg`,
  exactly as specified in the brief. It paginates through `repo.select_features` (page size
  `MAX_LIMIT` = 1000) under RLS scope, accumulates features, raises `413` if the accumulated
  count exceeds `EXPORT_ITEMS_CAP`, then serializes via `features_to_format` (gpkg needs a
  DuckDB spatial connection from the newly-imported `open_spatial_connection`), sets an
  audit log row (`action="export.run"`, `payload={"format":..., "mode":"items"}`), and returns
  a `Response` with the correct media type + `Content-Disposition` attachment header.
- Added `from app.analytics.duckdb_conn import open_spatial_connection` to the imports.
- `core/tests/test_features_export_routes.py`: appended the 5 tests from the brief (geojson,
  csv, gpkg, unsupported-format, cap-at-10000-via-monkeypatch).

## Bugs found in the brief's literal test text (fixed, not worked around)

Two real bugs, both in the *test* code the brief specified verbatim (not in the route
implementation, which was correct as given):

1. **Missing `"type": "Feature"` in the `POST /collections/{id}/items` payloads.**
   `validate_feature()` (`app/features/validation.py`) rejects any payload whose
   `feature.get("type") != "Feature"` with a structured 400 *before* even looking at
   `properties`/`geometry`. Every other test file in this codebase that posts a feature
   includes `"type": "Feature"` (e.g. `VALID` in `test_features_routes_write.py`,
   `demo_incidents` roundtrip in `test_features_integration.py`); the brief's 5 new item-export
   tests omitted it, so every `POST .../items` in the new tests failed 400, and the
   `_seed`-only fixture had nothing real to export. Fixed by adding `"type": "Feature"` to all
   five POST payloads.
2. **Missing required `"pop"` field in the cap test's two POST payloads.** `INFO` declares
   `pop` (`ColumnInfo(name="pop", type="integer", required=True)`); posting only `{"region": ...}`
   trips `missing_required` and the feature is never created — with 0 features created,
   `EXPORT_ITEMS_CAP=1` would never be exceeded and the 413 assertion would never be reachable.
   Fixed by adding `"pop": 1` / `"pop": 2` to those two payloads.

## A structural gap in the shared fixture (fixed — this one was necessary, not optional)

The existing `env` fixture (built for Task 1–3, aggregate-mode-only) never exercised the live
SQL-table path: `get_ddl_applier` is a no-op (no real "villes" table exists in the sqlite test
DB), and `get_features_repo`/`get_rls_scope` were left un-overridden, defaulting to the real
`app.features.repository`/`app.features.rls.rls_scope`. The real `rls_scope` issues
`SET LOCAL ... set_config(...)`, a PostGIS-only GUC function that SQLite doesn't have
(`sqlite3.OperationalError: no such function: set_config`) — confirmed by grepping the
codebase: every other test file that exercises `POST/GET .../items` against the sqlite fixture
(`test_features_routes_read.py`, `test_features_routes_write.py`) overrides both
`get_features_repo` (with an in-memory fake) and `get_rls_scope` (with `null_rls_scope`); only
`test_features_integration.py`'s real end-to-end roundtrip runs against real PostGIS
(`@pytest.mark.postgis`), where `set_config` genuinely exists.

Since the brief's new tests need a real write-then-read roundtrip (`POST /items` then
`GET /export/items`) through the *SQLite* `env` fixture, and no such support existed, I added:
- `make_fake_items_repo()` — an in-memory `SimpleNamespace(insert_feature, select_features,
  get_feature, state)`, same shape/pattern as `make_fake_repo()` in
  `test_features_routes_read.py`, but backed by real mutable state so a `POST` is visible to a
  later `GET`.
- In the `env` fixture: `app.dependency_overrides[features_routes.get_features_repo] = lambda:
  fake_items_repo` (single shared instance, not re-created per request) and
  `app.dependency_overrides[features_routes.get_rls_scope] = lambda:
  features_routes.null_rls_scope`.

This only affects tests that call `/items` (the 5 new ones); Task 3's aggregate/export tests
never touch `get_features_repo`/`get_rls_scope` (they go through the DuckDB CDC path only), so
this change is additive and safe.

## Testing

### RED (before implementing the route, after fixing the test-payload bugs)

```
$ git stash push -- app/features/routes.py   # temporarily remove the new route
$ uv run pytest tests/test_features_export_routes.py -k items -v
...
FAILED tests/test_features_export_routes.py::test_export_items_geojson_returns_a_feature_collection
FAILED tests/test_features_export_routes.py::test_export_items_csv_flattens_properties
FAILED tests/test_features_export_routes.py::test_export_items_gpkg_returns_a_sqlite_container
FAILED tests/test_features_export_routes.py::test_export_items_rejects_unknown_format
FAILED tests/test_features_export_routes.py::test_export_items_caps_at_10000_entities
======================= 5 failed, 6 deselected in 4.25s ========================
$ git stash pop
```
(4 failed with 404 route-not-found; the cap test failed with `AttributeError:
<module 'app.features.routes'> has no attribute 'EXPORT_ITEMS_CAP'` since the constant
didn't exist yet either — also an expected RED signal.)

### GREEN (after implementing the route)

```
$ uv run pytest tests/test_features_export_routes.py -v
tests/test_features_export_routes.py::test_export_aggregate_csv_returns_a_csv_attachment PASSED
tests/test_features_export_routes.py::test_export_aggregate_xlsx_returns_an_xlsx_attachment PASSED
tests/test_features_export_routes.py::test_export_aggregate_rejects_unknown_format PASSED
tests/test_features_export_routes.py::test_export_aggregate_requires_authentication PASSED
tests/test_features_export_routes.py::test_export_aggregate_denies_a_user_without_read_access PASSED
tests/test_features_export_routes.py::test_export_aggregate_writes_an_audit_log_row PASSED
tests/test_features_export_routes.py::test_export_items_geojson_returns_a_feature_collection PASSED
tests/test_features_export_routes.py::test_export_items_csv_flattens_properties PASSED
tests/test_features_export_routes.py::test_export_items_gpkg_returns_a_sqlite_container PASSED
tests/test_features_export_routes.py::test_export_items_rejects_unknown_format PASSED
tests/test_features_export_routes.py::test_export_items_caps_at_10000_entities PASSED
============================== 11 passed in 3.46s ==============================
```

### Regression check

```
$ uv run pytest -q
1197 passed, 131 skipped in 77.38s (0:01:17)
```
No regressions; skip count matches the documented baseline (postgis-marked tests, no docker
in this environment).

Output is clean under a normal run (`pytest -v`, no `-W error`); a pre-existing
`ResourceWarning: unclosed database in <sqlite3.Connection ...>` only surfaces under
`-W error::pytest.PytestUnraisableExceptionWarning` and reproduces identically on the
*original* Task-3-only tests (`-k aggregate`) with none of my changes in the loop — confirmed
pre-existing and unrelated to this task, not introduced by it.

## Files changed

- `core/app/features/routes.py` — new route + two constants + one import.
- `core/tests/test_features_export_routes.py` — 5 new tests (with the two payload fixes above),
  `make_fake_items_repo()` helper, two new fixture overrides, two new imports
  (`SimpleNamespace`, `FeaturePage`).

## Self-review

- **Completeness**: all 5 tests from the brief present and passing; route implemented verbatim
  per brief (format allowlist, pagination loop, cap check, gpkg-needs-conn branch, audit log,
  Content-Disposition header).
- **Quality**: route matches the existing sibling routes' style in this file (`list_features`,
  `export_collection_aggregate`) — same helpers (`_parse_bbox`, `_parse_geom_intersects`,
  `_collect_filters`, `_validation_error`), same RLS/introspection/repo injection pattern.
- **Discipline**: nothing added beyond the brief's route and tests, except the two necessary
  fixes above (test payload bugs) and the fixture gap fix (both required to make the brief's
  own tests exercise real behaviour rather than fail for reasons unrelated to the feature under
  test).
- **Testing**: tests exercise real behaviour (real in-memory write-then-read roundtrip, real
  cap-triggered 413, real format rejection) rather than being vacuously true; RED/GREEN evidence
  captured via `git stash` isolation of the route change; full suite green; no stray warnings
  in a normal test run.

## Issues / concerns

- The fixture change (fake repo + null RLS scope override) is a bit more invasive than a pure
  "append tests" instruction implies — but it was the only way to make the brief's tests
  exercise the real code path rather than 500/404 for unrelated reasons. Flagging this clearly
  since it wasn't in the brief's literal text; happy to discuss an alternative shape if the
  reviewer prefers a different fixture design (e.g. a real sqlite-backed "villes" table via a
  real DDL applier instead of a fake in-memory repo).
- Everything else matches the brief exactly (route code, constant names, commit message).
