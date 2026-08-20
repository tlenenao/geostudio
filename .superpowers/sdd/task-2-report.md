# Task 2 Report — Core `is_copilot_enabled()` + `GET /instance.copilotEnabled`

## What Was Implemented

Added instance-wide capability flag `copilotEnabled` to the core's `GET /instance` endpoint, backed by an `is_copilot_enabled()` function that detects the presence of the `CORE_LLM_PROVIDER` environment variable. The flag defaults to `False` and returns `True` whenever `CORE_LLM_PROVIDER` is set to any non-empty value (mirroring the pattern of `is_read_only_mode()` rather than the `"true"|"false"` pattern used by `is_etl_enabled` et consorts).

## TDD Evidence

### RED (Failing Test)

```
$ cd core && uv run pytest tests/test_copilot_enabled_flag.py -v

============================= test session starts ==============================
...
collected 0 items / 1 error

==================================== ERRORS ====================================
_____________ ERROR collecting tests/test_copilot_enabled_flag.py ______________
ImportError while importing test module '/home/lenen/projets/geostudio/core/tests/test_copilot_enabled_flag.py'.
...
E   ImportError: cannot import name 'is_copilot_enabled' from 'app.auth.dependency'
=========================== short test summary info ============================
ERROR tests/test_copilot_enabled_flag.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection ==============================
```

### GREEN (Passing Tests)

```
$ cd core && uv run pytest tests/test_copilot_enabled_flag.py tests/test_etl_enabled_flag.py tests/test_export_enabled_flag.py tests/test_read_only_mode.py tests/test_tileset3d_enabled_flag.py tests/test_terrain3d_enabled_flag.py -v

============================= test session starts ==============================
...
tests/test_copilot_enabled_flag.py::test_is_copilot_enabled_defaults_to_false PASSED [  2%]
tests/test_copilot_enabled_flag.py::test_is_copilot_enabled_true_for_any_non_empty_provider PASSED [  5%]
tests/test_copilot_enabled_flag.py::test_instance_reports_copilot_disabled_by_default PASSED [  8%]
tests/test_copilot_enabled_flag.py::test_instance_reports_copilot_enabled PASSED [ 11%]
tests/test_etl_enabled_flag.py::test_is_etl_enabled_defaults_to_false PASSED [ 14%]
tests/test_etl_enabled_flag.py::test_is_etl_enabled_reads_env_var PASSED [ 17%]
tests/test_etl_enabled_flag.py::test_instance_reports_etl_disabled_by_default PASSED [ 20%]
tests/test_etl_enabled_flag.py::test_instance_reports_etl_enabled PASSED [ 23%]
tests/test_export_enabled_flag.py::test_is_export_enabled_defaults_to_false PASSED [ 26%]
tests/test_export_enabled_flag.py::test_is_export_enabled_reads_env_var PASSED [ 29%]
tests/test_export_enabled_flag.py::test_instance_reports_export_disabled_by_default PASSED [ 32%]
tests/test_export_enabled_flag.py::test_instance_reports_export_enabled PASSED [ 35%]
tests/test_read_only_mode.py::test_instance_defaults_to_read_write PASSED [ 38%]
tests/test_read_only_mode.py::test_instance_reports_read_only_without_needing_auth PASSED [ 41%]
tests/test_read_only_mode.py::test_read_only_mode_blocks_every_mutation_even_for_admin[POST-/configs] PASSED [ 44%]
... (15 more passed)
tests/test_tileset3d_enabled_flag.py::test_upload_routes_absent_when_disabled PASSED [ 85%]
tests/test_terrain3d_enabled_flag.py::test_is_terrain3d_enabled_defaults_to_false PASSED [ 88%]
tests/test_terrain3d_enabled_flag.py::test_is_terrain3d_enabled_reads_env_var PASSED [ 91%]
tests/test_terrain3d_enabled_flag.py::test_instance_reports_terrain3d_disabled_by_default PASSED [ 94%]
tests/test_terrain3d_enabled_flag.py::test_instance_reports_terrain3d_enabled PASSED [ 97%]
tests/test_terrain3d_enabled_flag.py::test_upload_routes_absent_when_disabled PASSED [100%]

============================== 34 passed in 6.10s ==============================
```

## Files Changed

1. **`core/app/auth/dependency.py`** — Added `is_copilot_enabled()` function after `is_terrain3d_enabled()`. Returns `bool(os.environ.get("CORE_LLM_PROVIDER"))`.

2. **`core/app/instance/routes.py`** — Added import of `is_copilot_enabled` and added `"copilotEnabled": is_copilot_enabled()` key to `GET /instance` response dict.

3. **`core/tests/test_copilot_enabled_flag.py`** — Created new test file with 4 tests:
   - `test_is_copilot_enabled_defaults_to_false` — verifies flag is False without env var
   - `test_is_copilot_enabled_true_for_any_non_empty_provider` — verifies flag is True for any non-empty CORE_LLM_PROVIDER
   - `test_instance_reports_copilot_disabled_by_default` — integration test for GET /instance
   - `test_instance_reports_copilot_enabled` — integration test with flag enabled

4. **`core/tests/test_etl_enabled_flag.py`** — Fixed two exact-dict assertions in `test_instance_reports_etl_disabled_by_default()` and `test_instance_reports_etl_enabled()` by appending `"copilotEnabled": False,` key.

5. **`core/tests/test_export_enabled_flag.py`** — Fixed exact-dict assertion in `test_instance_reports_export_disabled_by_default()` by appending `"copilotEnabled": False,` key.

6. **`core/tests/test_read_only_mode.py`** — Fixed two exact-dict assertions in `test_instance_defaults_to_read_write()` and `test_instance_reports_read_only_without_needing_auth()` by appending `"copilotEnabled": False,` key.

## Self-Review Findings

- Implementation follows the exact pattern specified in the brief
- TDD workflow correctly executed: failing test → implementation → all tests passing
- Brittle dict assertions in existing tests were properly fixed (all three test files updated without errors)
- The function uses the correct semantics: `bool(os.environ.get("CORE_LLM_PROVIDER"))` evaluates to True for any non-empty string value, not just "true"
- Function is placed in the correct location in `dependency.py` (between `is_terrain3d_enabled()` and `admin_subs()` as per brief)
- Import in `routes.py` is in alphabetical order with other dependency imports
- All 34 tests pass (4 new copilot tests + 8 etl + 4 export + 8 read_only + 5 tileset3d + 5 terrain3d)

## Issues or Concerns

None. The implementation is complete and all tests pass.

## Commit

- **SHA**: f572c62
- **Message**: `feat(core): capacité copilotEnabled sur GET /instance (SP-20)`
