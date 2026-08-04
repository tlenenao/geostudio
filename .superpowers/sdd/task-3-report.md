# Task 3 Report: Core — GET /harvest/feature-layers

**Date:** 2026-08-04
**Status:** DONE

## Implementation Summary

Implemented the new `GET /harvest/feature-layers` endpoint in `core/app/harvest/routes.py` that:
- Consumes `repo.list_feature_layer_records()` to query feature layers across all harvested sources
- Applies per-item read authorization using `can(user, "read", item)` 
- Filters by optional `q` search parameter
- Returns only `{id, title}` pairs, deliberately **never** exposing `external_url` to the browser
- Returns response shape: `{"layers": [{"id": str, "title": str}]}`

## Test Evidence

### RED Phase (Failing Test)
```bash
$ cd core && uv run pytest tests/test_harvest_feature_layers_endpoint.py -v
============================= test session starts ==============================
tests/test_harvest_feature_layers_endpoint.py::test_feature_layers_returns_only_feature_records_of_visible_items FAILED [ 50%]
tests/test_harvest_feature_layers_endpoint.py::test_feature_layers_filters_by_q FAILED [100%]

>       assert resp.status_code == 200
E       assert 404 == 200
```
Both tests failed with 404 (route did not exist).

### GREEN Phase (Passing Tests)
```bash
$ cd core && uv run pytest tests/test_harvest_feature_layers_endpoint.py -v
============================= test session starts ==============================
tests/test_harvest_feature_layers_endpoint.py::test_feature_layers_returns_only_feature_records_of_visible_items PASSED [ 50%]
tests/test_harvest_feature_layers_endpoint.py::test_feature_layers_filters_by_q PASSED [100%]

============================== 2 passed in 3.21s ===============================
```
Both tests now pass.

### Full Suite (No Regressions)
```bash
$ cd core && uv run pytest
================= 819 passed, 106 skipped in 112.27s (0:01:52) =================
```
Full core test suite remains fully green. No regressions introduced.

## Files Changed

1. **core/app/harvest/routes.py** — Added new endpoint `list_feature_layers()` after `list_layers()`
2. **core/tests/test_harvest_feature_layers_endpoint.py** — New test file with 2 test cases

## Self-Review Findings

✓ **Complete literal implementation** — Route added exactly as specified in brief
✓ **URL security** — Response contains only `{"id", "title"}`; `external_url`/`externalUrl` is never exposed
✓ **Authorization verification** — Test verifies that items owned by regular user (without read access from admin context) do NOT appear in response
✓ **Query filtering** — Test verifies `?q=zzz-nomatch` returns empty layers list
✓ **Test quality** — Both test cases exercise real authorization logic (not mocks); authorization check via `can()` is active

## Commit

```
de5aa0b feat(core): GET /harvest/feature-layers for the SP-14k dataset picker (SP-14k)
```

---

## Notes

- The new endpoint follows the exact pattern of the existing `list_layers()` endpoint but uses `list_feature_layer_records()` and filters to feature layers only
- The test seed creates three items: one visible feature layer (admin owner), one raster layer (admin owner), one feature layer hidden from the requesting user (regular owner)
- When accessed as admin user, only the visible feature layer appears in the response, confirming authorization is working correctly
- All procrastinate job-queue errors in test output are expected (SQLite in-memory DB doesn't have job queue infrastructure) and do not affect test results
