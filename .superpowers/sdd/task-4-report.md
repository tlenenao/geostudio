# Task 4: Widen `_SUPPORTED_MODES` on the Routes — Report

## What Was Implemented

Per SP-18b Task 4, the `POST /app-exports` route now accepts `mode: "connected"` in addition to the existing `mode: "static"`.

- Updated the route-level allowlist `_SUPPORTED_MODES` from `{"static"}` to `{"static", "connected"}` in `core/app/appexport/routes.py`
- Updated test expectations: replaced the invalid-mode test to reject `"bogus"` (instead of `"connected"`), added new test to verify `"connected"` is now accepted

## TDD Evidence

### RED Phase
```
tests/test_appexport_routes.py::test_post_app_export_rejects_invalid_mode PASSED [ 50%]
tests/test_appexport_routes.py::test_post_app_export_accepts_connected_mode FAILED [100%]

def test_post_app_export_accepts_connected_mode(env):
    ...
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "connected"})
>       assert response.status_code == 202
E       assert 422 == 202
```

Initial test run with updated tests but unchanged routes.py: 7 passed, 1 failed (new test received 422 Unprocessable Entity instead of 202).

### GREEN Phase
```
tests/test_appexport_routes.py::test_post_app_export_requires_flag_enabled PASSED [ 12%]
tests/test_appexport_routes.py::test_post_app_export_creates_job_and_returns_202 PASSED [ 25%]
tests/test_appexport_routes.py::test_post_app_export_denies_user_without_read_access PASSED [ 37%]
tests/test_appexport_routes.py::test_post_app_export_rejects_invalid_mode PASSED [ 50%]
tests/test_appexport_routes.py::test_get_app_export_job_reports_status PASSED [ 62%]
tests/test_appexport_routes.py::test_post_app_export_allowed_in_read_only_demo_mode PASSED [ 75%]
tests/test_appexport_routes.py::test_get_app_export_job_done_status_includes_result_url PASSED [ 87%]
tests/test_appexport_routes.py::test_post_app_export_accepts_connected_mode PASSED [100%]

============================== 8 passed in 3.12s ===============================
```

After widening `_SUPPORTED_MODES` in routes.py: all 8 tests pass.

## Files Changed

1. **`core/app/appexport/routes.py`** (1 line change)
   - Line 24: `_SUPPORTED_MODES = {"static"}` → `_SUPPORTED_MODES = {"static", "connected"}`
   - Updated comment: `"connected"/"standalone" arrivent en SP-18b/c` → `"standalone" arrive en SP-18c`

2. **`core/tests/test_appexport_routes.py`** (12 lines changed)
   - Replaced `test_post_app_export_rejects_invalid_mode`: now tests rejection of `"bogus"` instead of `"connected"` (lines 105-111)
   - Added new `test_post_app_export_accepts_connected_mode` (lines 161-167)
     - Verifies `mode: "connected"` returns 202 Accepted
     - Verifies the task deferrer was called exactly once (same assertion pattern as existing acceptance test)

## Self-Review Findings

✅ **Tests correctly distinguish valid from invalid modes:**
- Invalid mode `"bogus"` correctly rejected with 422 (pre-existing allowlist validation)
- Valid mode `"connected"` correctly accepted with 202 (after routes.py change)
- Mode `"static"` continues to work (7 other tests still passing)

✅ **Comment accuracy:**
- Old comment: `"connected"/"standalone" arrivent en SP-18b/c` (implied both were future)
- New comment: `"standalone" arrive en SP-18c` (correctly reflects that `connected` is now implemented)

✅ **No regressions:**
- All pre-existing 7 tests continue to pass
- Behavior for static mode unchanged
- No architectural changes, only allowlist expansion

✅ **Commit message adheres to conventions:**
- Format: `feat(core): <subject> (SP-18b)`
- Correctly identifies this as a feature to the core
- References the task's SP

## Concerns

None. The task is straightforward: widen the allowlist to accept a mode that was already implemented by Tasks 1–3. The route layer is the final gate before the job is created, and once the gate is widened, the guard/bundler/job layers (already mode-aware from Tasks 1–3) handle `"connected"` correctly.

## Commit

- **SHA:** `726ce98`
- **Message:** `feat(core): POST /app-exports accepts mode=connected (SP-18b)`
