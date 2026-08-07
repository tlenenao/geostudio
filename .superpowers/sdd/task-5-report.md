# Task 5 Report: `POST /datasets/{id}/arcgis/export` (aggregate mode, arcgis-backed)

## What I implemented

Added a new route `POST /datasets/{item_id}/arcgis/export?format=csv|xlsx` to
`core/app/harvest/routes.py`, mirroring the existing
`GET /datasets/{item_id}/arcgis/aggregate` (`get_dataset_arcgis_aggregate`) route
but serializing the aggregated rows to CSV/XLSX via `rows_to_format` instead of
returning JSON — the arcgis-backed sibling of the collection-backed
`POST /collections/{collection_id}/export` route added in an earlier task
(`core/app/features/routes.py`).

Changes to `core/app/harvest/routes.py`:
- Added `Response` to the `fastapi` import.
- Added `from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format, rows_to_format`
  (imported verbatim as specified in the brief; `features_to_format` is unused
  by this route — it is needed by Task 6's `GET /datasets/{id}/arcgis/export/items`,
  which lands in the same file and is expected to reuse this same import line,
  per `progress.md`'s task list).
- Added `_EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}` and the
  `export_dataset_arcgis_aggregate` route function, placed directly after
  `get_dataset_arcgis_aggregate`, exactly as specified in the brief.

The route:
1. Validates `format` against `_EXPORT_FORMATS_AGGREGATE`, 400 on unknown format.
2. Rejects `bucket`/`split`/`bins` (unsupported for arcgis-sourced datasets),
   matching the same rule already enforced by the JSON aggregate route.
3. Resolves the arcgis dataset via `_resolve_arcgis_dataset` (auth + kind checks).
4. Builds groupBy/measures and translates to an ArcGIS query via
   `live_query.translate_aggregate_query`, with the same `ArcgisQueryError` →
   400 and `EgressBlockedError`/`httpx.HTTPError` → 502 handling as the
   existing aggregate route.
5. Aggregates the raw ArcGIS response via `live_query.aggregate_response`.
6. Serializes rows to bytes via `rows_to_format(rows, format=format)`.
7. Looks up the item title (falls back to `item_id` if missing) to build the
   download filename via `export_filename`.
8. Writes an audit log row (`action="export.run"`, `object_type="item"`,
   `object_id=item_id`, `payload={"format": format, "mode": "aggregate"}`).
9. Returns a `Response` with the serialized bytes, the correct
   `EXPORT_MEDIA_TYPES[format]` media type, and a `Content-Disposition:
   attachment` header.

## What I tested and test results

Created `core/tests/test_harvest_dataset_arcgis_export_routes.py` (new), with
the 3 tests from the brief, fixture mirrored verbatim from
`core/tests/test_harvest_dataset_arcgis_routes.py`:

1. `test_export_aggregate_csv_from_arcgis_dataset` — mocks the ArcGIS HTTP
   client to return one grouped row, posts to the export route with
   `format=csv`, asserts 200, `content-type: text/csv; charset=utf-8`, and
   that the CSV body contains `"Nord"`.
2. `test_export_aggregate_rejects_unknown_format` — posts with
   `format=pdf`, asserts 400 (no ArcGIS call is mocked, since the format
   check happens before the external call).
3. `test_export_aggregate_writes_an_audit_log_row` — posts a csv export,
   then queries the `AuditLog` table directly and asserts exactly one
   `export.run` row with `payload == {"format": "csv", "mode": "aggregate"}`.

All 3 tests use a realistic mocked ArcGIS HTTP response shape
(`{"features": [{"attributes": {...}}]}`), consistent with the real ArcGIS
`query` endpoint's aggregate response shape already exercised by the sibling
JSON aggregate route's tests — not vacuous/empty mocks.

### TDD Evidence

**RED** — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`

```
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_csv_from_arcgis_dataset FAILED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_rejects_unknown_format FAILED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_writes_an_audit_log_row FAILED
...
INFO httpx:_client.py:1025 HTTP Request: POST http://testserver/datasets/.../arcgis/export?format=csv "HTTP/1.1 404 Not Found"
============================== 3 failed in 2.28s ===============================
```
All three failed with 404 (route not yet defined), exactly as expected. (The
captured `procrastinate.exceptions.AppNotOpen` traceback in the log output is
pre-existing noise from item-creation embedding enqueue in the test fixture —
verified it also appears if you force a failure/`-s` in the pre-existing,
already-passing `test_harvest_dataset_arcgis_routes.py`; unrelated to this task.)

**GREEN** — `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`

```
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_csv_from_arcgis_dataset PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_rejects_unknown_format PASSED
tests/test_harvest_dataset_arcgis_export_routes.py::test_export_aggregate_writes_an_audit_log_row PASSED
============================== 3 passed in 2.24s ===============================
```

Also ran:
- `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py tests/test_harvest_dataset_arcgis_routes.py -q` → `16 passed`.
- Full core suite: `cd core && uv run pytest -q` → `1200 passed, 131 skipped` (no regressions).
- `cd core && uv run lint-imports` → `layered architecture KEPT — Contracts: 1 kept, 0 broken.` (the new
  `app.analytics.export` import from `app.harvest` doesn't violate the
  import-linter layering contract).
- `-q` run of the new file alone is pristine: `3 passed in 2.14s`, no warnings.

## Files changed

- `core/app/harvest/routes.py` (modified: new import + new route)
- `core/tests/test_harvest_dataset_arcgis_export_routes.py` (new)

## Self-review findings

- **Completeness**: all 3 tests from the brief implemented verbatim; route
  matches the brief's exact code (format validation, bucket/split/bins
  rejection, `_resolve_arcgis_dataset`, translate/fetch/aggregate pipeline,
  `rows_to_format`, filename, audit log, `Response`).
- **Quality**: route placement and structure closely mirror
  `get_dataset_arcgis_aggregate` immediately above it in the same file, and
  the collection-backed `export_collection_aggregate` in
  `core/app/features/routes.py` (same error-handling shape, same audit
  payload shape).
- **Discipline**: nothing added beyond the brief. One flagged but
  intentional-per-plan wrinkle: `features_to_format` is imported but unused
  by this route alone — it's consumed by Task 6's items-mode export route
  landing in the same file next, and importing both together in one line
  matches the pattern already used in `features/routes.py` where one import
  line serves two sibling export routes. I did not silently drop it or add
  an unrelated `# noqa`; there is no linter configured in this repo that
  flags unused imports (no `ruff`, only `import-linter` for module
  boundaries), so it does not break CI.
- **Testing**: mocked ArcGIS responses use realistic
  `{"features": [{"attributes": {...}}]}` shape, not empty/vacuous mocks;
  assertions check status code, content-type header, body content, and
  audit log row shape/payload — not just "it returns 200".

## Issues or concerns

None. Implementation matches the brief exactly, tests pass, no regressions,
import-linter contract holds, output is clean.
