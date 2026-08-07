# Task 6 Report: `GET /datasets/{id}/arcgis/export/items` (raw-entities mode, arcgis-backed)

## What was implemented

- `core/app/harvest/routes.py`:
  - Added `from app.analytics.duckdb_conn import open_spatial_connection` to the analytics import block.
  - Added `_EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}` and `_EXPORT_ITEMS_CAP = 10_000` constants after `export_dataset_arcgis_aggregate`.
  - Added `GET /datasets/{item_id}/arcgis/export/items` (`export_dataset_arcgis_items`): resolves the arcgis-backed dataset via `_resolve_arcgis_dataset`, paginates the live ArcGIS query endpoint via `live_query.translate_features_query` / `live_query.fetch_query` (page size `_MAX_LIMIT`=1000) accumulating features until a page shorter than the requested limit is returned (stop condition) or the accumulated count exceeds `_EXPORT_ITEMS_CAP` (413), then serializes via `features_to_format` to csv/xlsx/geojson/gpkg (opening a scratch DuckDB spatial connection only for gpkg), writes an `export.run` audit row with `payload={"format": format, "mode": "items"}`, and returns the file as an attachment — same response shape as the sibling aggregate-export route.
- `core/tests/test_harvest_dataset_arcgis_export_routes.py`: appended the 4 tests specified in the brief verbatim (geojson happy path, gpkg happy path via SQLite magic-byte check, pagination stop-condition on a short page, 413 cap behavior via `monkeypatch.setattr(harvest_routes, "_EXPORT_ITEMS_CAP", 1)`).

No brief discrepancies found this time (unlike Tasks 3/4) — the brief's code and tests matched the real signatures of `live_query.translate_features_query`, `live_query.fetch_query`, `features_to_format`, `open_spatial_connection`, and `_resolve_arcgis_dataset` exactly, and the pagination/cap logic in the tests is internally consistent with the implementation (verified by tracing both by hand and by running them).

## What was tested and results

- New file-scoped run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v` → **7 passed** (3 pre-existing Task 5 tests + 4 new Task 6 tests).
- Broader regression: `cd core && uv run pytest tests/ -k "harvest or arcgis" -q` → **223 passed, 13 skipped**.
- Full core suite: `cd core && uv run pytest -q` → **1204 passed, 131 skipped** (skips are the documented postgis-marked tests requiring docker; matches CLAUDE.md's stated baseline).
- Import-boundary contract: `cd core && uv run lint-imports` → **1 kept, 0 broken** (the new `app.harvest` → `app.analytics.duckdb_conn` import is consistent with the existing layering; `app.harvest` already imports from `app.analytics.aggregate`/`app.analytics.export`).
- `ruff` is not installed in this environment (`No such file or directory`); no other lint tool is configured for `core/` beyond import-linter.

## TDD Evidence

**RED** — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -k items -v`:
```
FAILED tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_geojson_from_arcgis_dataset
FAILED tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_gpkg_from_arcgis_dataset
FAILED tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_stops_paginating_on_a_short_page
FAILED tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_caps_at_10000_entities
======================= 4 failed, 3 deselected in 2.39s ========================
```
Confirmed the failures were the expected 404 (route not yet defined): `assert 404 == 200` on each `resp.status_code == 200` assertion. (Some unrelated `procrastinate.exceptions.AppNotOpen` stderr noise appears — pre-existing in this test file's setup, from `items_repo.create_item`'s async embedding-job enqueue attempt in a sqlite-only test session; identical noise is present in Task 5's tests and is not caused by this change.)

**GREEN** — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`:
```
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_csv_from_arcgis_dataset PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_rejects_unknown_format PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_writes_an_audit_log_row PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_geojson_from_arcgis_dataset PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_gpkg_from_arcgis_dataset PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_stops_paginating_on_a_short_page PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_caps_at_10000_entities PASSED
============================== 7 passed in 2.88s ===============================
```

## Files changed

- `core/app/harvest/routes.py` (+64 lines, pure addition)
- `core/tests/test_harvest_dataset_arcgis_export_routes.py` (+66 lines, pure addition)

Commit: `41ecc9e feat(core): SP-16a — GET /datasets/{id}/arcgis/export/items (entités brutes, 4 formats)`

## Self-review findings

- **Completeness**: all 4 new tests present and passing; route implemented exactly as specified including both new module-level constants.
- **Quality**: implementation mirrors existing patterns in the file closely — filter/bbox handling copied from `get_dataset_arcgis_items` (same `reserved` query-param exclusion pattern, same `_parse_bbox`/`translate_features_query`/`fetch_query` usage), export/audit/response tail copied from `export_dataset_arcgis_aggregate` (same `_EXPORT_FORMATS_*` naming convention, same audit payload shape with `mode` distinguishing "aggregate" vs "items", same `Response`/`Content-Disposition` construction). The gpkg-specific `open_spatial_connection()`/`conn.close()` scoping matches the doc-comment in `duckdb_conn.py` (in-process, no S3/httpfs, export-only use).
- **Discipline**: diff is pure addition to both files; nothing pre-existing was restructured or reformatted. No extra helpers, constants, or behavior beyond what the brief specified.
- **Testing realism**: tests use `httpx.MockTransport` handlers returning realistic ArcGIS-shaped GeoJSON FeatureCollections (matching the shape `live_query.fetch_query`/`translate_features_query` actually produce/consume), verified the gpkg happy path via the real SQLite magic-byte header (proving `features_to_format`+DuckDB actually round-tripped a GeoPackage), and the pagination/cap tests trace correctly against the real loop semantics: a short page (1 feature vs. limit=1000) trips the `len(page_features) < limit` break after exactly one call; a monkeypatched cap of 1 trips on the first page of 1000 features via `len(features) > _EXPORT_ITEMS_CAP` before any second page is fetched. Full core suite (1204 passed) and import-linter clean confirm no regressions or layering violations introduced.
- No stray warnings introduced by this change beyond the pre-existing procrastinate `AppNotOpen` noise inherited from the shared test fixture (also present in Task 5's tests, out of scope here).

## Issues or concerns

None. Brief was accurate and complete; no bugs found in the literal test/route text (unlike Tasks 3/4). Implementation is clean and matches sibling route conventions.

## Fix: pagination multi-page test

**Finding addressed (Important, from task review):** neither existing pagination test ever forced a second real HTTP call. `test_export_items_stops_paginating_on_a_short_page` returns a short page on the very first call (proves the break condition, never proves the loop continues). `test_export_items_caps_at_10000_entities` monkeypatches the cap down to 1, so the very first full page (1000 > 1) already trips the 413 — also exactly one HTTP call. The multi-page continuation path (`offset += limit`, looping back through `translate_features_query`/`fetch_query` a second time) was never exercised by any test in the file. A regression that broke offset incrementing, or that re-fetched the same page instead of the next one, would have passed every existing test.

**What was added** — `test_export_items_continues_past_a_full_page` in `core/tests/test_harvest_dataset_arcgis_export_routes.py`: the mock handler returns a full page (1000 features, `== _MAX_LIMIT`) on the first call and a short page (1 feature) on the second call. The test asserts:
- `len(calls) == 2` — the loop actually issued a second real HTTP call instead of stopping after the first (full) page;
- `"resultOffset=0" in calls[0]` and `"resultOffset=1000" in calls[1]` — the offset sent on the second request is genuinely incremented by the page size, not resent unchanged or wrong;
- `len(body["features"]) == 1001` — both pages' features were accumulated into the final export, not just the last page kept.

This directly exercises the gap identified in the finding: it is the only test in the file where the `while True` loop body runs a second iteration, so it is the only test that can catch a broken `offset += limit` (e.g. not incrementing, or incrementing by the wrong amount) or a loop that re-issues the same request instead of advancing.

**TDD verification (RED then GREEN):**
- Deliberately broke the implementation by changing `core/app/harvest/routes.py`'s `offset += limit` to `offset += 0` (offset never advances, simulating exactly the kind of regression the finding warned about).
- RED — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_continues_past_a_full_page -v`:
  ```
  FAILED tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_continues_past_a_full_page
  assert resp.status_code == 200
  E   assert 413 == 200
  ```
  (With offset stuck at 0, the loop kept refetching the same full page — never hitting the short-page break — until the accumulated count exceeded `_EXPORT_ITEMS_CAP`, tripping a 413 instead of the expected 200. Confirms the new test genuinely fails when the continuation path is broken.)
- Reverted `routes.py` to the original (verified `git diff --stat core/app/harvest/routes.py` shows no changes — this is a test-only fix, `export_dataset_arcgis_items` itself was never modified in the final state).
- GREEN — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`:
  ```
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_csv_from_arcgis_dataset PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_rejects_unknown_format PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_writes_an_audit_log_row PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_geojson_from_arcgis_dataset PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_gpkg_from_arcgis_dataset PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_stops_paginating_on_a_short_page PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_continues_past_a_full_page PASSED
  tests/test_harvest_dataset_arcgis_export_routes.py::test_export_items_caps_at_10000_entities PASSED
  ============================== 8 passed in 3.06s ===============================
  ```

**Full regression check** — `cd core && uv run pytest -q`:
```
1205 passed, 131 skipped in 78.89s (0:01:18)
```
(1205 = the previous 1204-passed baseline + 1 new test; skip count unchanged, matching the documented postgis/qgis-marker baseline. No regressions.)

Commit: `test(core): SP-16a — teste la continuation de pagination multi-pages sur GET /datasets/{id}/arcgis/export/items` (test-only, additive; `core/app/harvest/routes.py` untouched).
