# Task 9 Report: Widen `_SUPPORTED_MODES` to accept `mode="standalone"` (SP-18c)

## Summary
Task 9 of SP-18c implementation successfully completed. The `POST /app-exports` endpoint now accepts `mode="standalone"` as a valid export mode, alongside "static" and "connected".

## What Was Done

### Step 1: Write the Failing Test
Appended a new test `test_post_app_export_accepts_standalone_mode` to `core/tests/test_appexport_routes.py` that verifies the endpoint accepts `mode="standalone"` and returns 202 status with a job ID.

### Step 2: Verified Failure with 422
Ran the new test in isolation to confirm it fails with 422 Unprocessable Entity (expected behavior before applying the fix):
```
test_post_app_export_accepts_standalone_mode FAILED [100%]
assert 422 == 202
```
Confirmed that "standalone" was not in `_SUPPORTED_MODES`.

### Step 3: Applied the One-Line Change
Modified `core/app/appexport/routes.py` line 24:
- **Before:** `_SUPPORTED_MODES = {"static", "connected"}  # "standalone" arrive en SP-18c`
- **After:** `_SUPPORTED_MODES = {"static", "connected", "standalone"}`

### Step 4: Verified All Tests Pass
Ran the full test suite:
```bash
cd core && uv run pytest tests/test_appexport_routes.py -v
```
Result: **9 tests passed** (100%)

All tests passing:
1. test_post_app_export_requires_flag_enabled ✓
2. test_post_app_export_creates_job_and_returns_202 ✓
3. test_post_app_export_denies_user_without_read_access ✓
4. test_post_app_export_rejects_invalid_mode ✓
5. test_get_app_export_job_reports_status ✓
6. test_post_app_export_allowed_in_read_only_demo_mode ✓
7. test_get_app_export_job_done_status_includes_result_url ✓
8. test_post_app_export_accepts_connected_mode ✓
9. test_post_app_export_accepts_standalone_mode ✓ (NEW)

## Test Coverage

The new test `test_post_app_export_accepts_standalone_mode` verifies:
- `POST /app-exports` accepts `mode="standalone"`
- Response status code is 202 (Accepted)
- A task is deferred (1 call recorded)
- Endpoint behavior is consistent with existing mode tests

Test pattern mirrors `test_post_app_export_accepts_connected_mode`, using same fixtures and dependency overrides.

## Self-Review Notes

### Code Quality
- One-line change in routes.py is minimal and focused
- Removed obsolete TODO comment about SP-18c
- No new dependencies or side effects introduced
- Test follows existing naming and structure conventions
- Test uses identical setup pattern as sibling tests

### Process Validation
- TDD discipline: test first, verified failure, applied fix, verified pass
- Only intended files staged (routes.py and test file)
- No unrelated files included in commit
- All 9 tests pass consistently

### Interface Correctness
- Endpoint signature unchanged
- Validation logic properly rejects invalid modes
- HTTP status codes correct (202 success, 422 invalid mode)
- Mode correctly passed through to job creation and audit logging

## Files Modified
- `core/app/appexport/routes.py`: 1 line changed
- `core/tests/test_appexport_routes.py`: 10 lines added (test function)

## No Deviations
Task executed exactly as specified in the brief. No unexpected issues or alternatives encountered.

## Commit Details
- **Hash:** 9bda1c8
- **Message:** "feat(core): POST /app-exports accepts mode=standalone (SP-18c)"
- **Files:** core/app/appexport/routes.py, core/tests/test_appexport_routes.py
- **Staged:** Explicitly (not via git add -A), excluding .superpowers/sdd/ bookkeeping files
