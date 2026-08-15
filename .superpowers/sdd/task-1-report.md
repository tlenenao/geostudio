# SP-18b Task 1 Report: `check_export_guard` Becomes Mode-Aware

**Status:** DONE

**Commit Hash:** 3dc1e3e

**Test Summary:** 12 passed (all modes tested)

---

## What Was Implemented

The export guard function signature was evolved to support two distinct export modes:
- **mode="static"** (SP-18a): Bundles frozen data locally; restricts to public collections, forbids `statistics` sources, forbids third-party widgets.
- **mode="connected"** (SP-18b): Keeps the bundle calling the live core; only restricts to public collections; allows `statistics` sources and third-party widgets.

## Files Changed

1. **`core/app/appexport/guard.py`** — Updated `check_export_guard()` to accept a required keyword-only parameter `mode: str`:
   - Added `mode: str` as required keyword-only parameter to function signature.
   - Refactored logic for `statistics` sources: rejected in static mode only; allowed in connected mode if collection is public.
   - Refactored widget allowlist check: applied in static mode only; skipped in connected mode.
   - Public collection check: applied uniformly to both `features` and `statistics` sources across both modes.
   - Expanded docstring to explain both modes and justifications.

2. **`core/tests/test_appexport_guard.py`** — Comprehensive test refactor:
   - Renamed 8 existing tests with explicit `_in_static_mode` suffix for clarity.
   - Added `mode="static"` parameter to all 8 existing test calls (no logic changes).
   - Added 4 new connected-mode tests:
     - `test_statistics_source_on_public_collection_is_allowed_in_connected_mode` — statistics allowed if public
     - `test_statistics_source_on_non_public_collection_is_blocked_in_connected_mode` — statistics blocked if private
     - `test_features_source_on_non_public_collection_is_still_blocked_in_connected_mode` — features still restricted
     - `test_third_party_widget_is_allowed_in_connected_mode` — no widget restrictions in connected mode
   - Factored out collection helpers (`_public_collection()`, `_private_collection()`) to reduce duplication and improve test readability.

## TDD Evidence

### RED (Before guard.py update)
All 12 tests failed with:
```
TypeError: check_export_guard() got an unexpected keyword argument 'mode'
```

### GREEN (After guard.py update)
```
============================= 12 passed in 0.60s ==============================
```
- 8 static-mode tests: PASSED
- 4 connected-mode tests: PASSED
- 0 failures, 0 regressions

## Self-Review

### Signature Correctness:
✅ `mode` is a required keyword-only parameter (enforced by `*, ... mode: str`).  
✅ Matches brief specification exactly.

### Logic Verification:
✅ **Static mode behavior** (byte-for-byte unchanged from SP-18a):
- Line 68: `if source.type == "statistics" and mode == "static"` — blocks statistics
- Line 91: `if mode == "static"` — blocks unsupported widgets
- Both modes check `is_public` uniformly

✅ **Connected mode behavior** (new):
- Statistics sources allowed if public (line 68-69 conditional skips rejection)
- Widget allowlist check skipped entirely (line 91 conditional)
- Still enforces `is_public` on all data sources

### Test Coverage:
✅ 8 static-mode tests cover: empty config, static type, features (public/private/missing), statistics (blocked), widgets (unsupported at both page and top levels)  
✅ 4 connected-mode tests cover: statistics (public/private), features (still private-blocked), third-party widgets (now allowed)  
✅ All 12 tests pass without regression

### Code Quality:
✅ Docstring expanded to document both modes and their restrictions.  
✅ Comments clarify conditional logic at key decision points.  
✅ No linting or type issues.

## Concerns

None. Implementation is clean, passes TDD discipline, and matches brief specification exactly.

---

**Completed:** 2026-08-15  
**Next Task:** Task 2 (jobs.py caller update)
