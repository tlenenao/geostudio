# Task 5 Report: Core — `GET/POST /datasets/{itemId}/arcgis/items|aggregate`

## Status: DONE

## Summary

Implemented two new FastAPI routes that enable live proxying to ArcGIS Feature Services for `arcgis`-sourced datasets. This completes the integration of live data queries through the core platform, translating client requests into ArcGIS REST API calls and reshaping responses for consumption by the shell.

## Implementation

### Files Modified

1. **`core/app/harvest/routes.py`**
   - Added necessary imports: `datetime`, `timezone`, `Query`, `Request`, `httpx`, aggregation models, configs repository, live_query module, egress guarding
   - Added module constant: `_MAX_LIMIT = 1000`
   - Added dependency factory: `get_arcgis_http_client()` for building guarded HTTP clients (overridable in tests)
   - Added helper functions:
     - `_parse_bbox(raw)`: Parses and validates bbox parameter as 4 comma-separated floats
     - `_resolve_arcgis_dataset(session, item_id, user)`: Resolves a dataset item to its ArcGIS layer URL with authorization checks
     - `_groupby_fields(raw)`: Normalizes groupBy parameter to a list
     - `_measure_label(m)`: Derives measure labels
   - Added two routes:
     - `GET /datasets/{item_id}/arcgis/items`: Queries features with filters, bbox, limit, offset
     - `POST /datasets/{item_id}/arcgis/aggregate`: Computes aggregations with optional grouping

2. **`core/tests/test_harvest_dataset_arcgis_routes.py`** (new file)
   - Complete test suite with 10 test cases covering all route behaviors

## Verification Results

### Step 1: Focused Test Run (RED → GREEN)
```bash
cd core && uv run pytest tests/test_harvest_dataset_arcgis_routes.py -v
```

**Before**: Routes did not exist, dependency factory missing
**After**: All 10 tests PASSED in 8.23s

```
============================== 10 passed in 8.23s ==============================
```

Test results:
- ✓ `test_get_items_proxies_to_arcgis_and_reshapes_response`
- ✓ `test_get_items_forwards_filters_and_bbox`
- ✓ `test_get_items_unknown_dataset_item_404s`
- ✓ `test_get_items_egress_blocked_returns_502`
- ✓ `test_post_aggregate_no_groupby_count`
- ✓ `test_post_aggregate_groupby_and_measure`
- ✓ `test_post_aggregate_bucket_rejected`
- ✓ `test_post_aggregate_split_rejected`
- ✓ `test_post_aggregate_bins_rejected`
- ✓ `test_get_items_on_collection_dataset_404s`

### Step 2: Full Core Suite + Lint-Imports
```bash
cd core && uv run pytest && uv run lint-imports
```

**Results**: PASSED
- Full pytest: `844 passed, 106 skipped in 124.35s`
- Import linter: `Contracts: 1 kept, 0 broken.` (layered architecture maintained)
- No new violations introduced

## Self-Review Checklist

✓ **Both routes fully implemented** as specified in the brief

✓ **bucket/split/bins genuinely return 400**: Tests verify HTTP 400 status with correct error message

✓ **Every outbound HTTP call goes through egress guard**: All calls via `get_arcgis_http_client()` dependency which injects guarded client built from `app.harvest.egress.build_guarded_client()`

✓ **Tests are behavioral, not mock-chains**: Use `httpx.MockTransport` for controlled ArcGIS service simulation; real egress-block and error scenarios tested

✓ **No existing httpx import alias conflicts**: File had no prior httpx import

✓ **Authorization enforcement**: `_resolve_arcgis_dataset` checks both dataset item and referenced layer access

✓ **Response shape compliance**: Features include `numberMatched`, `numberReturned`, `timeStamp`, `links`; aggregate includes `categoryKey` and `rows`

## Commit

`53e2cd0` — `feat(core): GET/POST /datasets/{itemId}/arcgis/items|aggregate live proxy (SP-14k)`

Files changed:
- `core/app/harvest/routes.py` (modified)
- `core/tests/test_harvest_dataset_arcgis_routes.py` (new)

## Fix: field-name injection (post-review)

### The finding

A task review flagged a Critical: unvalidated filter field *names* (query-param
keys on `GET /datasets/{itemId}/arcgis/items`, JSON-body keys of `body.filters`
on `POST /datasets/{itemId}/arcgis/aggregate`) reached the outbound ArcGIS
`where=` clause unescaped. `live_query._build_where` only escaped filter
*values* via `_sql_lit`; the field *name* was interpolated verbatim into the
SQL-like where string, so a query param key like `1) OR (1=1--` would land
unescaped in the request sent to the remote ArcGIS `FeatureServer/query`
endpoint — a confirmed, exploitable injection into an external-service
request.

### What I changed

1. **`core/app/harvest/live_query.py`**
   - Line 8: added `import re`.
   - Line 16: added `_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")`
     next to `_RANGE_OPS`/`_STAT_TYPES` — a strict ArcGIS/SQL-style identifier
     pattern (letter/underscore then letters/digits/underscores only).
   - In `_build_where` (around line 43-45): after
     `name, suffix = _split_filter_key(raw_name)`, added a check that raises
     `ArcgisQueryError(raw_name, f"invalid filter field name '{name}'")` when
     `name` doesn't match `_FIELD_NAME_RE`, before any clause is built from it.
     This is a scoped identifier-pattern fix (not a column allowlist), per the
     reviewer's own suggestion — the arcgis connector has no local
     schema/column list for the remote layer to allowlist against.
   - `_build_where` is shared by both `translate_features_query` (used by the
     `GET .../items` route) and `translate_aggregate_query` (used by the
     `POST .../aggregate` route), so one check covers both filter-name
     injection paths.

2. **`core/app/harvest/routes.py`**
   - In `get_dataset_arcgis_items` (around line 238-246): wrapped the
     `live_query.translate_features_query(...)` call in a
     `try/except live_query.ArcgisQueryError` that raises `HTTPException(400, …)`
     with the same response shape (`{"errors": [{"field", "code": "invalid_filter", "message"}]}`)
     already used by the aggregate route's equivalent handling. The existing
     `try/except EgressBlockedError/httpx.HTTPError/finally` around
     `fetch_query` was left untouched, as a separate block.
   - `get_dataset_arcgis_aggregate` was **not modified** — see below.

### Was the aggregate route already covered "for free"?

Yes, confirmed by reading the code before assuming it. Lines 276-284 of
`routes.py` (pre-existing, unchanged) already wrap
`live_query.translate_aggregate_query(group_by=group_by, measures=measures, filters=body.filters, bbox=body.bbox)`
in a `try/except live_query.ArcgisQueryError` that raises the same 400 shape
(`code: "invalid_aggregate"`). Since `translate_aggregate_query` calls the
same `_build_where` that now raises on bad field names, `body.filters` keys
are validated through the exact same code path and the existing except clause
catches it — no route-level change was needed for the aggregate route.

### Tests added

**`core/tests/test_harvest_live_query.py`** — added
`test_translate_features_query_rejects_invalid_field_name`, asserting
`live_query.translate_features_query(filters={"1) OR (1=1--": "x"}, ...)`
raises `ArcgisQueryError`. Existing tests use only valid identifiers
(`statut`, `annee`, `type`, `nom`, `commune`, with `__gte`/`__lte`/`__in`
suffixes), confirmed unaffected.

**`core/tests/test_harvest_dataset_arcgis_routes.py`** — added:
- `test_get_items_invalid_filter_field_name_rejected`: `GET
  /datasets/{item_id}/arcgis/items` with query param key
  `1) OR (1=1--` returns 400.
- `test_post_aggregate_invalid_filter_field_name_rejected`: `POST
  /datasets/{item_id}/arcgis/aggregate` with `filters: {"1) OR (1=1--": "x"}`
  in the JSON body returns 400 (mirrors the existing
  `test_post_aggregate_bucket_rejected`-style tests in that file).

### Verification commands and results

```
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_harvest_live_query.py tests/test_harvest_dataset_arcgis_routes.py tests/test_create_dataset_arcgis.py -q
```
Result: `31 passed in 6.77s`

```
uv run pytest -q
```
Result: `847 passed, 106 skipped in 113.86s` — fully green (up from the
606+87 baseline noted in CLAUDE.md, reflecting cumulative SP-14k test growth
across tasks 1-5).

```
uv run lint-imports
```
Result: `Contracts: 1 kept, 0 broken.` — unaffected, as expected (no new
cross-module imports introduced).

### Scope discipline

No schema-fetch/column-allowlist system was added. `groupByFieldsForStatistics`
/ `group_by` field validation was left untouched (out of scope for this
finding — the review explicitly excluded it). No unrelated refactoring.
