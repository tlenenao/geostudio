# Task 4 Report: `core/app/harvest/live_query.py` — ArcGIS Query Translation Module

## Status

**DONE** — All 15 unit tests pass, full core suite green (834 passed, 106 skipped), no regressions.

## What Was Implemented

Created `core/app/harvest/live_query.py` — a pure translation and caching module that converts generic filter/bbox/groupBy/measures vocabulary into ArcGIS REST Feature Service query parameters. No HTTP routes; consumed by Task 5's FastAPI endpoints.

### Implemented Components

1. **`ArcgisQueryError`** exception — custom error with `.field: str` and `.message: str` attributes
2. **`translate_features_query()`** — filters (__gte, __lte, __in), bbox (esriGeometryEnvelope), pagination → REST params
3. **`translate_aggregate_query()`** — groupBy + measures (count, sum, avg, min, max) → statistics params; validates agg type and field requirements
4. **`fetch_query()`** — HTTP client wrapper with 20-second TTL cache keyed by URL + sorted params
5. **`aggregate_response()`** — reshapes ArcGIS response features into row dictionaries with proper grouping (no grouping / single field / multi-field)

Plus private helpers for WHERE clause building, SQL escaping, bbox params, and cache key generation.

## Test Results

### Focused Test Suite (15 tests)

```bash
cd core && uv run pytest tests/test_harvest_live_query.py -v
```

**Result:** 15/15 PASS ✓

- `test_translate_features_query_builds_where_from_filters` ✓
- `test_translate_features_query_no_filters_is_1_equals_1` ✓
- `test_translate_features_query_bbox_adds_envelope_params` ✓
- `test_translate_features_query_escapes_single_quotes` ✓
- `test_translate_aggregate_query_count_no_groupby` ✓
- `test_translate_aggregate_query_groupby_single_field` ✓
- `test_translate_aggregate_query_groupby_multi_field` ✓
- `test_translate_aggregate_query_unknown_agg_raises` ✓
- `test_translate_aggregate_query_non_count_without_field_raises` ✓
- `test_fetch_query_returns_parsed_json` ✓
- `test_fetch_query_caches_within_ttl` ✓ (monkeypatched time.monotonic)
- `test_aggregate_response_no_groupby_single_row` ✓
- `test_aggregate_response_single_groupby_field` ✓
- `test_aggregate_response_multi_groupby_fields` ✓
- `test_aggregate_response_no_features_empty_rows` ✓

### Full Core Suite

```bash
cd core && uv run pytest
```

**Result:** 834 passed, 106 skipped — NO REGRESSIONS ✓

## TDD Evidence

### RED Phase

```bash
cd core && uv run pytest tests/test_harvest_live_query.py -v
```

**Output:**
```
ERROR collecting tests/test_harvest_live_query.py
ImportError: cannot import name 'live_query' from 'app.harvest'
```

### GREEN Phase

```bash
cd core && uv run pytest tests/test_harvest_live_query.py -v
============================== 15 passed in 0.16s ==============================
```

## Files Changed

| Path | Type | Status |
|------|------|--------|
| `core/app/harvest/live_query.py` | New | Created (171 lines) |
| `core/tests/test_harvest_live_query.py` | New | Created (171 lines) |

## Self-Review Findings

✓ **Completeness:** All 5 interfaces + error class implemented exactly per brief  
✓ **Test coverage:** 15 tests cover all code paths (filters, bbox, aggregations, errors, cache TTL, response shaping)  
✓ **SPDX header:** Present on both files  
✓ **No HTTP routes:** Translation layer only, ready for Task 5 wiring  
✓ **Cache behavior:** TTL validated via monkeypatched `time.monotonic()`; order-independent key (`urlencode(sorted(params))`)  
✓ **Error handling:** `ArcgisQueryError` raised with context (field/message) for validation failures  
✓ **No regressions:** Full suite unchanged from pre-implementation baseline  

## Commit

```
8d7dd3a feat(core): live_query translates filters/bbox/groupBy to ArcGIS REST (SP-14k)
```

## Handoff to Task 5

`live_query` module is complete and ready for FastAPI route wiring. Task 5 will create `/datasets/{itemId}/arcgis/items` and `/datasets/{itemId}/arcgis/aggregate` routes that:
1. Parse query parameters from request
2. Call `translate_features_query()` / `translate_aggregate_query()`
3. Pass injected `httpx.Client` to `fetch_query()`
4. Reshape with `aggregate_response()` if needed
5. Return response to client
