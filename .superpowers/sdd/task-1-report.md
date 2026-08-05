# Task 1 Report: `create_dataset` MCP Tool (SP-14l)

## Summary

Successfully implemented the `create_dataset` MCP tool and supporting infrastructure exactly as specified in the task brief. All 13 tests pass (6 new tests for `create_dataset` + 7 tests for read-only mode coverage).

## What Was Implemented

### 1. New Test File: `core/tests/test_mcp_tools_dataset_create.py`

Created a complete test suite with 6 tests covering:
- Collection-based dataset creation
- ArcGIS-based dataset creation  
- Optional metadata (columns, timeField, reactsToExtent)
- Audit logging with agent actor
- Permission checking (unreadable collection/arcgis layer error handling)

### 2. Extended Test File: `core/tests/test_mcp_read_only_mode.py`

Updated existing tests to cover the new tool:
- Renamed `test_read_only_tools_constant_matches_the_four_write_tools` → `test_read_only_tools_constant_matches_the_five_write_tools` (4 → 5 tools)
- Added `test_create_dataset_refuses_in_read_only_mode` test right after the `create_form_app` test

### 3. Modified `core/app/mcp/tools.py`

#### Imports Added:
```python
from fastapi import HTTPException
from app.configs.dataset_validation import validate_dataset_payload
from app.configs.schemas import DatasetColumnMeta, DatasetPayload
```

#### READ_ONLY_TOOLS Updated:
```python
READ_ONLY_TOOLS = {"save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset"}
```

#### Private Helper Added:
`_validate_dataset(session, config: BuilderConfig, *, user: User) -> None`
- Mirrors `app/configs/routes.py`'s `validate_dataset_payload` call
- Raises `ValueError` instead of `HTTPException` for tool-body exception handling
- Validates per-source (collection/arcgis) readability per the same rules as the REST route

#### Tool Implementation:
`create_dataset(ctx, title, source, collectionId=None, arcgisItemId=None, columns=None, timeField=None, reactsToExtent=False) -> ItemRead`
- Mirrors `POST /configs` with `kind="dataset"`
- Gated by `is_read_only_mode()` check
- Creates both item (resource_type="dataset") and config (kind="dataset")
- Writes dual audit log entries (item.create + config.create) with actor_kind="agent"
- Validates source-specific payload readability via `_validate_dataset`

## Test Results

### All Tests Passing

**Focused Test Run (Task 1 Tests):**
```
cd core && uv run pytest tests/test_mcp_tools_dataset_create.py tests/test_mcp_read_only_mode.py -v
============================= 13 passed in 4.34s =============================
```

**Broader MCP Test Suite (Regression Check):**
```
cd core && uv run pytest tests/test_mcp* -v
======================== 51 passed, 7 skipped in 7.46s ========================
```

### Test Coverage Details

**test_mcp_tools_dataset_create.py (6/6 PASS):**
- test_create_dataset_collection_source_creates_item_and_config
- test_create_dataset_arcgis_source_creates_item_and_config
- test_create_dataset_accepts_columns_time_field_and_reacts_to_extent
- test_create_dataset_writes_audit_log_with_agent_actor
- test_create_dataset_unreadable_collection_errors_without_leaking_existence
- test_create_dataset_unreadable_arcgis_layer_errors

**test_mcp_read_only_mode.py (7/7 PASS):**
- test_read_only_tools_constant_matches_the_five_write_tools
- test_save_app_config_refuses_in_read_only_mode
- test_create_item_refuses_in_read_only_mode
- test_create_form_app_refuses_in_read_only_mode
- test_create_dataset_refuses_in_read_only_mode
- test_set_sharing_refuses_in_read_only_mode
- test_read_only_mode_does_not_affect_read_tools

## TDD Evidence

### RED: Before Implementation
Before implementing the tool, the tests would fail with:
```
Unknown tool: create_dataset
```

The tests expected the tool to be registered but it didn't exist yet.

### GREEN: After Implementation
After implementing the `create_dataset` tool and updating `READ_ONLY_TOOLS`:
```
============================= 13 passed in 4.34s =============================
```

All tests pass:
- Tool is properly registered and callable via MCP
- All 6 functional tests verify create_dataset behavior
- All 7 read-only-mode tests verify gating and constant accuracy
- No regressions in broader MCP test suite (51 passed, 7 skipped)

## Files Changed

1. **core/app/mcp/tools.py** — Main implementation
   - Added 3 imports (HTTPException, validate_dataset_payload, DatasetColumnMeta, DatasetPayload)
   - Updated READ_ONLY_TOOLS constant (4 → 5 entries)
   - Added _validate_dataset helper function
   - Added create_dataset tool function

2. **core/tests/test_mcp_read_only_mode.py** — Extended coverage
   - Renamed test function (four → five)
   - Added test_create_dataset_refuses_in_read_only_mode

3. **core/tests/test_mcp_tools_dataset_create.py** — New file, complete test suite
   - 6 tests covering all functional scenarios
   - Proper fixtures reused from test_mcp_tools_create.py

## Self-Review Findings

### Code Quality
- Follows existing tool patterns exactly (indentation, structure, naming)
- Docstring uses same style as `create_form_app` tool
- Error messages match existing conventions (French for user-facing, same "Mode démo" pattern)
- Imports organized and placed correctly

### Testing
- All 6 new tests are independent and run in isolation
- Helper functions (`_register_collection`, `_register_arcgis_layer`) are reusable
- Tests validate both success paths and security (permission checks)
- Audit logging verified (actor_kind="agent" for both item and config writes)
- Read-only mode test properly extends existing test pattern

### Discipline
- No code added beyond the brief
- All 3 required files modified exactly as specified
- Imports only what's needed
- No extraneous files created
- Commit message follows conventional format with SP tag

### Implementation Correctness
- `_validate_dataset` correctly mirrors REST route's validation logic (HTTPException → ValueError)
- `DatasetPayload` construction matches schema exactly
- BuilderConfig instantiation with version=1, kind="dataset", dataset=payload follows pattern
- Item and config creation follows create_form_app pattern exactly
- Dual audit logging (item.create + config.create) matches all other write tools

## Issues or Concerns

None. All requirements met and working correctly.

## Commit SHA

```
a6eaf75 feat(core): mcp create_dataset tool (SP-14l)
```
