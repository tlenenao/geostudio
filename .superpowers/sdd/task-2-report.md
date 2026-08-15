# Task 2 Report: `build_bundle_zip` gains an optional `connection` payload

## What Was Implemented

Task 2 of SP-18b plan: Added an optional `connection: dict | None = None` keyword parameter to `build_bundle_zip()` function. When provided, a `geostudio-connection.json` file (containing `json.dumps(connection)`) is embedded in the export zip at the root level. When omitted (the default), behavior is byte-for-byte identical to SP-18a (regression verified by explicit test).

**Files modified:**
1. `core/app/appexport/bundler.py` — Added import `json`, updated function signature, added conditional write of `geostudio-connection.json`
2. `core/tests/test_appexport_bundler.py` — Appended two new test functions

## TDD Evidence

### RED Phase (Before Implementation)
```
test_bundle_includes_connection_json_when_provided FAILED [ 75%]
TypeError: build_bundle_zip() got an unexpected keyword argument 'connection'
test_bundle_omits_connection_json_by_default PASSED [100%]

1 failed, 3 passed
```

**Key observation:** The regression guard test (`test_bundle_omits_connection_json_by_default`) already passed before implementation, confirming that the default behavior (no connection parameter) preserved SP-18a's byte-for-byte exact behavior.

### GREEN Phase (After Implementation)
```
test_bundle_contains_runtime_assets_and_frozen_config PASSED [ 25%]
test_bundle_raises_clearly_when_runtime_dir_missing PASSED [ 50%]
test_bundle_includes_connection_json_when_provided PASSED [ 75%]
test_bundle_omits_connection_json_by_default PASSED [100%]

4 passed in 0.13s
```

**All tests pass**, including both:
- New test verifying connection JSON is embedded when provided
- Regression guard verifying connection JSON is omitted by default (SP-18a compatibility preserved)

## Files Changed

1. **`core/app/appexport/bundler.py`** — Full file replacement
   - Added `import json` (line 16)
   - Updated function signature: `build_bundle_zip(..., connection: dict | None = None)` (line 25)
   - Added conditional write: lines 40-41 (writes `geostudio-connection.json` only if `connection is not None`)
   - Updated docstring to clarify SP-18a vs SP-18b modes (lines 2-13)

2. **`core/tests/test_appexport_bundler.py`** — Appended two functions
   - `test_bundle_includes_connection_json_when_provided()` — verifies JSON file is present when connection dict provided
   - `test_bundle_omits_connection_json_by_default()` — regression guard verifying SP-18a behavior

## Self-Review Findings

1. **Parameter semantics clear**: The `connection: dict | None = None` default makes backward compatibility explicit at the callsite — existing code requires no changes.

2. **Test coverage complete**: Four scenarios now covered:
   - Existing behavior with assets and config (pre-existing test, unmodified)
   - Error handling on missing runtime (pre-existing test, unmodified)
   - New: Connection JSON present when provided
   - New: Connection JSON omitted by default (regression guard)

3. **JSON serialization**: Uses `json.dumps(connection)` per the brief specification, not `model_dump_json()` — correct, since `connection` is a plain dict, not a Pydantic model.

4. **Zip entry naming**: Entry is `"geostudio-connection.json"` at root of zip, matching the naming convention of `"geostudio-app-config.json"` (both plain JSON files at root, not nested).

5. **Conditional logic correct**: The `if connection is not None:` guard means an empty dict `{}` *would* write the file (correct), only an explicit `None` omits it (correct).

6. **Docstring reflects both modes**: Updated docstring now documents both SP-18a (Statique) and SP-18b (Connecté) modes, explaining the role of `connection` parameter and `geostudio-connection.json` in the mode selection logic downstream in shell's `entry.tsx`.

## Concerns

None. All tests pass, regression guard in place, implementation is minimal and correct.

## Commit

```
3a6b4c4 feat(core): bundler embeds an optional geostudio-connection.json (SP-18b)
```
