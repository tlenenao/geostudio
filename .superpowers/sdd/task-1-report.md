# SP-18c Task 1 Report: `check_export_guard` gains `mode="standalone"`

**Status:** DONE

**Commit Hash:** f4c5508

**Test Summary:** 17 passed (all modes tested: static + connected + standalone)

---

## What Was Implemented

Extended the export guard to support a third "standalone" (autoporté) export mode that combines:
- **is_public leniency** from "connected" mode: statistics sources allowed on public collections
- **widget allowlist strictness** from "static" mode: builtin-widget-only allowlist enforced

The three modes now work as follows:
- **mode="static"** (SP-18a): Public collections only, no statistics, builtin widgets only
- **mode="connected"** (SP-18b): Public collections only, statistics allowed, any widgets allowed
- **mode="standalone"** (SP-18c): Public collections only, statistics allowed, builtin widgets only

## Files Changed

1. **`core/app/appexport/guard.py`** — Updated to support "standalone" mode:
   - Updated docstring from "(SP-18a/b)" to "(SP-18a/b/c)" with full explanation of autoporté mode
   - Added `_STRICT_WIDGET_MODES = frozenset({"static", "standalone"})` constant
   - Updated widget allowlist comment: "Pertinent pour mode="static" ET mode="standalone""
   - Refactored widget check from `if mode == "static":` to `if mode in _STRICT_WIDGET_MODES:`
   - Updated error message to be generic: "ce mode d'export" instead of "l'export statique"
   - Updated is_public guard comment to clarify all three modes' handling of "statistics" sources

2. **`core/tests/test_appexport_guard.py`** — Added comprehensive standalone mode tests:
   - `test_statistics_source_on_public_collection_is_allowed_in_standalone_mode`
   - `test_statistics_source_on_non_public_collection_is_blocked_in_standalone_mode`
   - `test_features_source_on_non_public_collection_is_still_blocked_in_standalone_mode`
   - `test_unsupported_widget_type_is_blocked_in_standalone_mode`
   - `test_builtin_widgets_only_is_allowed_in_standalone_mode`

## TDD Evidence

### Step 1: Tests written and verified to fail
Initial test run showed 1 failure as expected:
- `test_unsupported_widget_type_is_blocked_in_standalone_mode` — FAILED (widget allowlist not yet enforced)
- Other standalone tests mostly passed (they only test is_public guard which was already lenient for "connected")

### Step 2: Implementation applied
Guard updated with `_STRICT_WIDGET_MODES` constant and conditional logic refactor.

### Step 3: All tests pass
```
============================== 17 passed in 0.61s ==============================
```
- 12 original tests (8 static-mode + 4 connected-mode): PASSED
- 5 new standalone-mode tests: PASSED
- 0 failures, 0 regressions

## Self-Review

### Mode Behavior Correctness:
✅ **Static mode** — unchanged from prior implementation:
  - Line 73-76: Blocks `statistics` sources
  - Line 97-100: Enforces widget allowlist
  - Line 88-89: Enforces is_public for all sources

✅ **Connected mode** — unchanged from prior implementation:
  - Line 73-76: Allows `statistics` if public (conditional skips rejection)
  - Line 97-100: No widget allowlist check
  - Line 88-89: Enforces is_public for all sources

✅ **Standalone mode** (new):
  - Allows `statistics` if public (same as connected)
  - Enforces widget allowlist (same as static)
  - Enforces is_public for all sources (same as both)

### Implementation Quality:
✅ Minimal, focused change: only 24 lines modified/added in guard.py
✅ Uses `_STRICT_WIDGET_MODES` set to clearly express mode grouping
✅ No changes to function signature or public interfaces
✅ Backward compatible with "static" and "connected" mode callers
✅ Error messages updated to be mode-agnostic

### Test Coverage:
✅ 5 new standalone tests cover all key scenarios:
  - Statistics on public collections (allowed)
  - Statistics on private collections (blocked)
  - Features on private collections (still blocked)
  - Third-party widgets (blocked)
  - Builtin widgets (allowed)
✅ All test assertions verify correct behavior
✅ Test names clearly document the expected behavior

### Code Quality:
✅ Docstring expanded with clear explanation of autoporté mode behavior
✅ Comments updated to document all three modes' handling of statistics
✅ Widget allowlist comment correctly states applicability to both "static" and "standalone"
✅ No type errors, no linting issues

## Key Design Decisions

1. **`_STRICT_WIDGET_MODES` constant** — Groups "static" and "standalone" modes for readability and future extensibility. Single source of truth for which modes enforce widget allowlist.

2. **Generic error message** — Changed from "l'export statique" to "ce mode d'export" to support multiple modes without code duplication.

3. **is_public leniency** — Both "connected" and "standalone" allow statistics sources on public collections. This reflects the architecture decision that:
   - Connected mode calls `/aggregate` at runtime (already anonymously capable)
   - Standalone mode freezes aggregates in the snapshot and serves them from the mini-server (also anonymously callable)
   - Neither requires figuring out the aggregate at export time itself

4. **Widget allowlist strictness** — Both "static" and "standalone" reject third-party widgets because:
   - Static bundles everything; third-party widgets can't be bundled
   - Standalone also bundles; same constraint applies
   - Connected mode loads widgets from external URLs, so no bundling needed

## Concerns

None. Implementation follows TDD discipline, passes all tests, and matches brief specification exactly.

---

**Completed:** 2026-08-15  
**Next Task:** Task 2 (update jobs.py to handle mode parameter)
