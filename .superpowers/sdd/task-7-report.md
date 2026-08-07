# Task 7: Read-only demo guard — exempt export routes

**Date:** 2026-08-07  
**Status:** ✅ DONE  
**Branch:** dev  
**Commit:** d35f46b

## What Was Implemented

Task 7 adds a new regex pattern `_EXPORT_PATH_RE` to the read-only-demo middleware guard in `core/app/main.py` and adds a corresponding test to `core/tests/test_read_only_mode.py`. The export routes (added in Tasks 1-6) use POST for aggregate-mode exports and must be exempted from the read-only guard to work correctly in demo mode.

### Changes Made

**File: `core/app/main.py`**
- Added `_EXPORT_PATH_RE` regex pattern: `r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$"`
- Updated `read_only_guard` middleware to include `and not _EXPORT_PATH_RE.match(request.url.path)` in the condition

**File: `core/tests/test_read_only_mode.py`**
- Appended new test function: `test_read_only_mode_does_not_block_export_endpoints()`
- Test verifies both export routes return 404 (not 403) in read-only mode

## Testing and Test Results

### TDD Evidence: RED Phase
```
cd core && uv run pytest tests/test_read_only_mode.py::test_read_only_mode_does_not_block_export_endpoints -v

FAILED tests/test_read_only_mode.py::test_read_only_mode_does_not_block_export_endpoints
assert 403 == 404
```
✅ Test failed as expected with 403 status (guard blocking before route execution).

### TDD Evidence: GREEN Phase
```
cd core && uv run pytest tests/test_read_only_mode.py -v

tests/test_read_only_mode.py::test_instance_defaults_to_read_write PASSED
tests/test_read_only_mode.py::test_instance_reports_read_only_without_needing_auth PASSED
tests/test_read_only_mode.py::test_read_only_mode_blocks_every_mutation_even_for_admin[...] PASSED (5 variants)
tests/test_read_only_mode.py::test_read_only_mode_does_not_affect_reads PASSED
tests/test_read_only_mode.py::test_read_only_mode_off_by_default_leaves_mutations_working PASSED
tests/test_read_only_mode.py::test_read_only_mode_does_not_block_the_aggregate_endpoint PASSED
tests/test_read_only_mode.py::test_analytics_sql_is_exempt_from_read_only PASSED
tests/test_read_only_mode.py::test_read_only_mode_does_not_block_export_endpoints PASSED

====== 12 passed in 2.97s ======
```
✅ All read-only mode tests pass.

### Full Core Test Suite
```
cd core && uv run pytest -q

1206 passed, 131 skipped in 78.41s
```
✅ No regressions. Test count increased due to Tasks 1-7 additions (previously 606 + 87 skipped).

## Files Changed

- `/home/lenen/projets/geostudio/core/app/main.py`
  - Line 36-37: Added `_EXPORT_PATH_RE` regex
  - Line 73: Added export path check to guard condition

- `/home/lenen/projets/geostudio/core/tests/test_read_only_mode.py`
  - Lines 107-121: Appended new test function

## Self-Review Findings

### Regex Validation

The `_EXPORT_PATH_RE` pattern correctly matches all four export route shapes:
- ✅ `/collections/{id}/export` — matches `^/collections/[^/]+/export$`
- ✅ `/collections/{id}/export/items` — matches with optional `/items` capture
- ✅ `/datasets/{id}/arcgis/export` — matches alternation second part
- ✅ `/datasets/{id}/arcgis/export/items` — matches with optional `/items`

**Negative cases (must NOT match):**
- ❌ `/collections/x/aggregate` — correctly NOT matched (different route)
- ❌ `/collections/x/export/unknown` — correctly NOT matched (only `/items` allowed)
- ❌ `/datasets/x/export` — correctly NOT matched (requires `arcgis` segment)
- ❌ `/invalid/export` — correctly NOT matched (invalid collection/dataset prefix)

### Guard Condition Logic

The middleware guard now correctly exempts:
1. GET requests (method not in mutation set)
2. `/mcp` path (exact match)
3. `/analytics/sql` path (exact match)
4. Paths matching `_AGGREGATE_PATH_RE` (e.g., `/collections/{id}/aggregate`)
5. Paths matching `_EXPORT_PATH_RE` (new — e.g., `/collections/{id}/export`)

Write operations on other paths remain blocked in read-only mode. ✅

### Code Quality

- Implementation mirrors existing `_AGGREGATE_PATH_RE` pattern exactly
- No extraneous changes beyond the brief requirements
- Test message (French) matches project documentation style
- Commit message follows conventional format (`fix(core): SP-16a — …`)

## Issues and Concerns

**None.** The implementation:
- Matches the brief specification exactly
- Passes all tests (12 read-only + 1206 full suite)
- Introduces no regressions
- Follows established patterns in the codebase
