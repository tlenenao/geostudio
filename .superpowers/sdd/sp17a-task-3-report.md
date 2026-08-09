# SP-17a Task 3 Report: `export_jobs` Table + Repository

## Summary

Implemented the `export_jobs` SQLAlchemy table and CRUD repository for GeoStudio's export worker infrastructure. Task completed TDD: RED (test failed due to missing module) → GREEN (all 4 tests pass) → commit.

## What Was Implemented

### Files Created

1. **`core/app/export/__init__.py`** (empty, following `core/app/alerts/__init__.py` pattern)
2. **`core/app/export/models.py`** (SQLAlchemy model `ExportJob`)
   - Table: `export_jobs`
   - Columns: `id` (PK, uuid4.hex), `tenant_id`, `item_id`, `user_id`, `format`, `status` (default "pending"), `error`, `result_key`, `started_at`, `finished_at`, `created_at`
   - Foreign keys to `tenants.id`, `items.id`, `users.id`

3. **`core/app/export/repository.py`** (CRUD functions)
   - `create_job()` — creates a job with status "pending", assigns uuid4.hex as id, flushes & refreshes
   - `get_job()` — retrieves by job_id + tenant_id (tenant-scoped query)
   - `mark_running()` — updates status to "running", sets started_at
   - `mark_done()` — updates status to "done", sets result_key & finished_at
   - `mark_error()` — updates status to "error", sets error message & finished_at

4. **`core/tests/test_export_repository.py`** (4 unit tests)
   - `test_create_job_starts_pending` — verifies job starts with status "pending", error/result_key are None, can be fetched by get_job
   - `test_mark_running_then_done` — verifies transitions through running→done, sets started_at & finished_at
   - `test_mark_error_never_leaves_status_running` — verifies mark_error changes status to "error", never leaves it "running"
   - `test_get_job_scoped_to_tenant` — verifies get_job returns None when queried with different tenant_id (tenant isolation)

### File Modified

**`core/app/db.py`** — added import of `app.export.models` in `core_table_names()` function (line 51). This ensures SQLAlchemy's `Base.metadata` discovers the `ExportJob` model before `create_all()` is called. This is required for the SQLite in-memory test setup to work correctly.

## TDD Evidence

### RED State (Step 2)
```
ModuleNotFoundError: No module named 'app.export'
```
✓ Expected error confirmed when test file ran before implementation.

### GREEN State (Step 4)
```
tests/test_export_repository.py::test_create_job_starts_pending PASSED   [ 25%]
tests/test_export_repository.py::test_mark_running_then_done PASSED      [ 50%]
tests/test_export_repository.py::test_mark_error_never_leaves_status_running PASSED [ 75%]
tests/test_export_repository.py::test_get_job_scoped_to_tenant PASSED    [100%]

============================== 4 passed in 0.47s ===============================
```
✓ All 4 tests pass.

## Self-Review Findings

### Test Coverage
1. ✓ `test_create_job_starts_pending` — verifies initial state and persistence
2. ✓ `test_mark_running_then_done` — verifies state transitions and timestamp updates
3. ✓ `test_mark_error_never_leaves_status_running` — verifies mark_error changes status to "error" (no stuck "running" state)
4. ✓ `test_get_job_scoped_to_tenant` — genuinely proves tenant isolation: queries the same job_id with a different tenant_id and expects None (not just checking None is returned by accident)

### Implementation Quality
- Model follows SQLAlchemy 2.0 patterns (Mapped types, ForeignKey constraints)
- Foreign key constraints on all related entities (tenant, item, user)
- All nullable fields properly typed with `| None`
- Repository functions use `session.flush()` not `session.commit()` (follows project pattern)
- `mark_*` functions use `session.get()` for efficient direct lookup, guard against None
- Tenant scoping enforced in `get_job()` via WHERE clause filtering

### Database Registration
- Added import in `core/app/db.py` to ensure model is registered on `Base.metadata` before SQLite tests create tables
- Pattern mirrors existing modules (`app.alerts`, `app.items`, etc.)
- No regression: alphabetical order in imports maintained

### Full Test Suite
```
1285 passed, 137 skipped in 85.86s
```
✓ No regressions. Export job tests + all existing core tests pass.

## Commit

**SHA:** `a101546`
**Message:** `feat(core): SP-17a — table export_jobs + repository`

## Concerns

None. All requirements met:
- TDD workflow complete (RED → GREEN)
- All 4 tests pass with genuine tenant isolation verification
- mark_error correctly sets status to "error" (never stuck in "running")
- Full core suite green
- Minimal change to existing code (only `core/app/db.py`, which was necessary for model registration)

## Files Changed

```
core/app/export/__init__.py (new, empty)
core/app/export/models.py (new, 28 lines)
core/app/export/repository.py (new, 56 lines)
core/tests/test_export_repository.py (new, 73 lines)
core/app/db.py (modified, 1 line added for export model import)
```
