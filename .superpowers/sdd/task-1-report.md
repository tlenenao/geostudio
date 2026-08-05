# Task 1 Report: Core — `BookmarkPayload` schema (Pydantic)

## Summary

Implemented the complete bookmark configuration schema in Pydantic, adding three new model classes and extending `BuilderConfig` to support the `"bookmark"` kind. All specifications from the task brief were implemented exactly as specified.

## What Was Implemented

### 1. Three new Pydantic model classes (in `core/app/configs/schemas.py`):

- **`BookmarkCrossFilterEntry`**: Represents a single cross-filter entry with field, value(s), and origin source ID
- **`BookmarkTimeRange`**: Represents a time range with `from_` and `to` fields (using Pydantic `alias` to map JSON `"from"` to Python `from_`)
- **`BookmarkPayload`**: Main bookmark payload with appId, pageId, optional timeRange, extent, and crossFilter dict

### 2. Extended `BuilderConfig`:

- Added `"bookmark"` to the `kind` Literal type
- Added `bookmark: BookmarkPayload | None = None` field
- Extended `_require_kind_payload` validator to validate that when `kind == "bookmark"`, the `bookmark` payload is present

## Test Results

### TDD Red → Green

**RED (before implementation):**
```bash
$ cd core && uv run pytest tests/test_bookmark_config_schema.py -v
FAILED tests/test_bookmark_config_schema.py::test_bookmark_config_valide
FAILED tests/test_bookmark_config_schema.py::test_bookmark_config_time_range_extent_cross_filter_optionnels
FAILED tests/test_bookmark_config_schema.py::test_bookmark_config_round_trips_through_dump_and_validate
PASSED tests/test_bookmark_config_schema.py::test_bookmark_config_sans_payload_rejete
PASSED tests/test_bookmark_config_schema.py::test_bookmark_config_page_id_vide_rejete
PASSED tests/test_bookmark_config_schema.py::test_bookmark_config_page_id_blanc_rejete
3 failed, 3 passed
```

Root cause: `kind` literal did not accept `"bookmark"`.

**GREEN (after implementation):**
```bash
$ cd core && uv run pytest tests/test_bookmark_config_schema.py -v
tests/test_bookmark_config_schema.py::test_bookmark_config_valide PASSED
tests/test_bookmark_config_schema.py::test_bookmark_config_sans_payload_rejete PASSED
tests/test_bookmark_config_schema.py::test_bookmark_config_time_range_extent_cross_filter_optionnels PASSED
tests/test_bookmark_config_schema.py::test_bookmark_config_page_id_vide_rejete PASSED
tests/test_bookmark_config_schema.py::test_bookmark_config_page_id_blanc_rejete PASSED
tests/test_bookmark_config_schema.py::test_bookmark_config_round_trips_through_dump_and_validate PASSED
6 passed in 0.10s
```

### Full Test Suite

Before: 861 passed, 112 skipped
After: 867 passed, 112 skipped (+6 tests)

No regressions detected. The 6-test increase corresponds exactly to the 6 new tests added.

## Files Changed

1. **`core/app/configs/schemas.py`** (modified)
   - Added 3 new Pydantic model classes (29 lines)
   - Updated `BuilderConfig` (added `"bookmark"` to kind literal, added bookmark field, extended validator)
   - Total: +47 insertions in this file

2. **`core/tests/test_bookmark_config_schema.py`** (new file)
   - Complete test suite with 6 tests
   - Tests: valid bookmark config, missing payload rejection, optional fields, empty/whitespace pageId validation, round-trip serialization
   - Total: 55 lines

## Test Coverage

The test suite comprehensively validates:

1. **Valid bookmark config**: Full payload with all fields populated
2. **Required payload validation**: Rejects `kind: "bookmark"` without `bookmark` payload
3. **Optional fields**: timeRange, extent, and crossFilter are truly optional (default to None and {})
4. **Page ID validation**: Empty string and whitespace-only strings are rejected via custom validator
5. **Serialization round-trip**: Full dump → reload cycle with Pydantic aliases works correctly

## Self-Review Findings

✅ **Completeness**: All requirements from the brief implemented exactly as specified
✅ **Code Quality**: Follows existing patterns in the codebase (identical style to `DatasetPayload`)
✅ **Discipline**: No overbuilding; only added what was requested
✅ **Testing**: TDD followed; tests written before implementation; comprehensive coverage of happy path and edge cases
✅ **No Regressions**: Full test suite passes without issues

## Commit

```
commit a461604
Author: Tanguy
Date: 2026-08-05

feat(core): bookmark config schema (SP-14m)

- Added BookmarkCrossFilterEntry, BookmarkTimeRange, BookmarkPayload models
- Extended BuilderConfig to support "bookmark" kind
- Added comprehensive test suite (6 tests)
- All tests passing, no regressions

Files:
  core/app/configs/schemas.py (modified, +47 lines)
  core/tests/test_bookmark_config_schema.py (new, 55 lines)
```

## Status

✅ **DONE** — All requirements met, tests passing, no concerns.
