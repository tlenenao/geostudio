# Task 3 Report: `build_app_export_task` branches on `mode`

## What Was Implemented

Task 3 is the integration point for SP-18b where the `build_app_export_task` procrastinate job now properly handles two distinct modes:

1. **Static mode** (default, unchanged from SP-18a): Calls `freeze_config()` to materialize all data sources, then passes `connection=None` to the bundler.
2. **Connected mode** (new): Skips `freeze_config()`, keeps the config live, and passes `connection={"coreUrl": ...}` constructed from the `CORE_BASE_URL` environment variable (default `http://localhost:8200`).

The fix integrates Task 1's `check_export_guard(..., mode=...)` requirement and Task 2's `build_bundle_zip(..., connection=...)` parameter.

### Implementation Details

1. **Added `BuilderConfig` import** to the jobs module.
2. **Created `_prepare_bundle_inputs()` helper function** that branches on mode:
   - For `"connected"`: returns original config + `{"coreUrl": core_url}` dict
   - For `"static"`: returns frozen config + `None`
3. **Updated `build_app_export_task()`** to:
   - Read `mode` from the persisted job (line 67: `mode = job.mode`)
   - Pass `mode=mode` to `check_export_guard()` call (line 74)
   - Call `_prepare_bundle_inputs()` to branch on mode (lines 75–78)
   - Pass the resulting `connection` dict to `build_bundle_zip()` (line 81)

## TDD Evidence

### RED Phase (Before Implementation)

```
tests/test_appexport_jobs.py::test_job_succeeds_and_marks_done FAILED
tests/test_appexport_jobs.py::test_job_guard_rejection_marks_error FAILED
tests/test_appexport_jobs.py::test_connected_job_skips_freezing_and_embeds_core_base_url FAILED
tests/test_appexport_jobs.py::test_connected_job_with_private_source_marks_error FAILED

Error: TypeError: check_export_guard() missing 1 required keyword-only argument: 'mode'
```

The job's call to `check_export_guard(session, tenant_id=tenant_id, config=config_read.config)` was missing the `mode=` kwarg entirely, causing all tests to fail. The exception handler caught this and marked jobs as "error" status.

### GREEN Phase (After Implementation)

```
tests/test_appexport_jobs.py::test_job_disabled_flag_marks_error PASSED  [ 20%]
tests/test_appexport_jobs.py::test_job_succeeds_and_marks_done PASSED    [ 40%]
tests/test_appexport_jobs.py::test_job_guard_rejection_marks_error PASSED [ 60%]
tests/test_appexport_jobs.py::test_connected_job_skips_freezing_and_embeds_core_base_url PASSED [ 80%]
tests/test_appexport_jobs.py::test_connected_job_with_private_source_marks_error PASSED [100%]

============================== 5 passed in 0.69s ===============================
```

All 5 tests pass consistently.

## Files Changed

- **`core/app/appexport/jobs.py`** (94 lines → 96 lines)
  - Updated docstring: "SP-18a" → "SP-18a/b"
  - Added `BuilderConfig` import
  - Added `_prepare_bundle_inputs()` helper function (7 lines)
  - Modified `build_app_export_task()` to read `mode` from job and call helper function
  - Updated call to `check_export_guard()` to pass `mode=mode` kwarg
  - Updated `build_bundle_zip()` call to pass `connection` parameter

- **`core/tests/test_appexport_jobs.py`** (100 → 146 lines)
  - Modified `_setup()` function signature: added `mode="static"` parameter
  - Modified `_setup()` function body: changed `create_job()` to pass `mode=mode` instead of hardcoded `"static"`
  - Added `test_connected_job_skips_freezing_and_embeds_core_base_url()` test
  - Added `test_connected_job_with_private_source_marks_error()` test

## Commit

```
commit 17608be: feat(core): app export job branches on mode — connected skips freezing (SP-18b)
```

## Self-Review Findings

### Correctness

- ✅ The implementation exactly matches the plan text and satisfies all three test assertions
- ✅ `check_export_guard()` now receives the required `mode=` kwarg
- ✅ `freeze_config()` is properly skipped for connected mode
- ✅ The `connection` dict is correctly constructed from `CORE_BASE_URL` env var with proper default
- ✅ The mode is read from `job.mode` (field set at job creation time, not modified here)
- ✅ All three pre-existing tests continue to pass with the default `mode="static"`
- ✅ Both new tests verify the branching behavior correctly:
  - One asserts that `connection` is properly embedded for connected mode
  - One asserts that connected mode still respects the guard (rejects private sources)

### Code Quality

- ✅ `_prepare_bundle_inputs()` is a clean, testable abstraction that encapsulates the mode branching logic
- ✅ No breaking changes to public signatures
- ✅ The exception handling remains unchanged (broad catch-all still marks job as "error")
- ✅ Docstring updated to reflect the new dual-mode behavior
- ✅ Import of `BuilderConfig` is necessary and correct

### Testing

- ✅ Tests demonstrate both modes work correctly (static freezes, connected embeds URL)
- ✅ Tests confirm the guard still rejects private sources in both modes
- ✅ Spy pattern on `build_bundle_zip()` in new test correctly captures the `connection` argument
- ✅ No test fixtures were broken
- ✅ Test isolation is clean (each test gets its own database session)

### Environment

- ✅ Default `CORE_BASE_URL` value matches the pattern used elsewhere in the codebase (`http://localhost:8200`)
- ✅ New env var read is optional with proper fallback

## Concerns

None. The implementation is complete, correct, and well-tested. All requirements from the plan are satisfied.

---

**Status**: DONE  
**Execution Time**: ~3 minutes (all 5 tests pass in 0.69s)
