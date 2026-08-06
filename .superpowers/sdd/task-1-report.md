# Task 1 Report: Op Catalog Entries for Reader Connectors

## Summary

Successfully implemented Task 1 of SP-15f: added two new Pipeline reader operation types (`reader.connector.rest` and `reader.connector.postgres`) to the op catalog module `core/app/pipelines/ops/schemas.py`.

## Implementation Details

### What Was Implemented

**Two new Pydantic models added to `core/app/pipelines/ops/schemas.py`:**

1. **`ReaderConnectorRestParams`**
   - Validates REST API endpoints with required `baseUrl` field (enforced http/https via regex pattern)
   - Optional fields: `path` (default ""), `method` (GET/POST, default GET), `query`, `headers`, `recordsPath`, `paginator`, `paginatorConfig`, `secretName`
   - Paginator types validated via Literal: "none", "page_number", "cursor", "offset"
   - References optional authentication secret (SP-15e) for api_key, bearer_token, basic_auth, or oauth2_client_credentials

2. **`ReaderConnectorPostgresParams`**
   - Validates remote PostgreSQL queries with required `secretName` and `query` fields
   - `secretName` references a postgres_dsn secret (SP-15e)
   - `query` not validated for SELECT-only at schema level (validation deferred to runtime)

**Updated catalogs:**
- `OP_KINDS`: added entries for both ops as "reader" kind
- `OP_PARAMS`: registered both model classes with their respective op keys

### Test-Driven Development Evidence

**RED phase (tests failing before implementation):**
```bash
cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v
# Result: 7 tests failing
# - test_all_seventeen_ops_are_registered (KeyError/AssertionError)
# - test_reader_connector_ops_are_kind_reader (KeyError)
# - test_reader_connector_rest_minimal_params (ValueError: unknown op)
# - test_reader_connector_rest_rejects_non_http_base_url (ValueError: unknown op)
# - test_reader_connector_rest_full_params (ValueError: unknown op)
# - test_reader_connector_rest_rejects_unknown_paginator (ValueError: unknown op)
# - test_reader_connector_postgres_requires_secret_name_and_query (ValueError: unknown op)
# - test_reader_connector_ops_appear_in_catalog (ValueError: unknown op)
```

**GREEN phase (all tests passing after implementation):**
```bash
cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v
# Result: 49 passed in 0.14s
```

**Regression test suite (full pipelines):**
```bash
cd core && uv run pytest tests/test_pipeline_*.py tests/test_mcp_tools_pipeline.py -v
# Result: 143 passed, 10 skipped in 6.77s
# (Also updated test_pipeline_routes.py::test_get_pipelines_ops_returns_all_seventeen to reflect new op count)
```

## Files Changed

1. **`core/app/pipelines/ops/schemas.py`**
   - Added `ReaderConnectorRestParams` class (40 lines)
   - Added `ReaderConnectorPostgresParams` class (7 lines)
   - Extended `OP_KINDS` dict with 2 new entries
   - Extended `OP_PARAMS` dict with 2 new entries

2. **`core/tests/test_pipeline_ops_schemas.py`**
   - Renamed test: `test_all_fifteen_ops_are_registered` → `test_all_seventeen_ops_are_registered`
   - Updated expected ops set to include both new connector reader ops
   - Added 7 new test functions covering:
     - Op kind registration
     - Minimal parameter defaults
     - URL validation (http/https only)
     - Full parameter configuration
     - Paginator type validation
     - PostgreSQL required fields validation
     - Catalog exposure

3. **`core/tests/test_pipeline_routes.py`**
   - Renamed test: `test_get_pipelines_ops_returns_all_fifteen` → `test_get_pipelines_ops_returns_all_seventeen`
   - Updated expected ops count (15→17) and set to include new connector readers

## Self-Review Findings

✅ **Implementation matches brief exactly:**
- Pydantic field definitions match verbatim from brief
- `OP_KINDS` and `OP_PARAMS` dicts contain all 17 ops in specified order
- Docstrings in French match brief specifications

✅ **TDD properly executed:**
- Tests written first (failing)
- Implementation added (passing)
- Regression tests run and passing
- Test names and descriptions accurate

✅ **Code organization maintained:**
- No file restructuring
- Models added after `TransformQgisParams` as specified
- Dicts remain in consistent alphabetical/category order
- No unrelated changes

✅ **All test assertions pass:**
- URL pattern validation (http/https)
- Required field validation
- Literal type validation for paginator
- Catalog JSON schema generation
- Kind classification ("reader")

✅ **No warnings or errors:**
- Clean pytest output
- No deprecation warnings
- No linting issues

## Concerns

None. Implementation is clean, follows the exact specification, and all tests pass including the broader regression suite. The two new ops are now discoverable through:
- `parse_op_params()` function
- `ops_catalog()` function
- Direct dictionary access via `OP_PARAMS` and `OP_KINDS`

## Commit Information

- **Commit SHA:** 7f3e7e2
- **Branch:** dev
- **Message:** feat(core): pipelines — reader.connector.rest/postgres op catalog entries
- **Files changed:** 3 (schemas.py, test_pipeline_ops_schemas.py, test_pipeline_routes.py)
- **Lines added/modified:** 106 insertions, 3 deletions
