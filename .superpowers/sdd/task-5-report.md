# Task 5 Report: Arrêt propre `cdc-worker` (SP-26/3.5b)

## Summary

Implemented graceful shutdown for the CDC worker by wiring up the existing but unused `should_stop` parameter in `stream_changes()`. The mechanism allows SIGTERM to cleanly exit the consumer loop and perform a final flush of buffered rows before shutdown.

## Implementation Details

### Files Changed

1. **`core/app/cdc/main.py`**
   - Added `import signal` to imports
   - Added `_ShutdownState` class (lines 64-77):
     - `__init__()`: initializes `_stop=False`
     - `should_stop()`: returns the flag value
     - `handle_sigterm(signum, frame)`: sets `_stop=True` on SIGTERM
   - Modified `run()` function:
     - Line 127: `shutdown = _ShutdownState()`
     - Line 128: `signal.signal(signal.SIGTERM, shutdown.handle_sigterm)`
     - Line 224: Added `should_stop=shutdown.should_stop` parameter to `stream_changes()`
     - Lines 226-230: Added final `_do_flush()` call with explanatory comment

2. **`core/tests/test_cdc_shutdown.py`** (new file)
   - Tests signal handling in isolation (not `run()` end-to-end per brief requirements)
   - Verifies flag initially False
   - Verifies flag becomes True after SIGTERM

## TDD Evidence

### RED (Step 3)
```
AttributeError: module 'app.cdc.main' has no attribute '_ShutdownState'
```

### GREEN (Step 5)
```
tests/test_cdc_shutdown.py::test_sigterm_sets_the_stop_flag PASSED [100%]
```

## Test Results

### New Test
```
tests/test_cdc_shutdown.py::test_sigterm_sets_the_stop_flag PASSED
```

### Full CDC Test Suite (10 tests)
```
tests/test_cdc_shutdown.py::test_sigterm_sets_the_stop_flag PASSED        [ 10%]
tests/test_cdc_main.py::test_build_s3_key_matches_layout_convention PASSED [ 20%]
tests/test_cdc_main.py::test_worker_state_tracks_last_seen_lsn PASSED     [ 30%]
tests/test_cdc_main.py::test_get_lag_seconds_computes_elapsed_time_since_last_flush PASSED [ 40%]
tests/test_cdc_main.py::test_get_lag_seconds_thread_safe_under_concurrent_writes PASSED [ 50%]
tests/test_cdc_main.py::test_get_lag_seconds_respects_externally_held_lock PASSED [ 60%]
tests/test_cdc_main.py::test_record_flush_respects_externally_held_lock PASSED [ 70%]
tests/test_cdc_main.py::test_write_and_upload_removes_temp_file_when_upload_fails PASSED [ 80%]
tests/test_cdc_main.py::test_write_and_upload_removes_temp_file_when_write_fails PASSED [ 90%]
tests/test_cdc_main.py::test_write_and_upload_removes_temp_file_on_success PASSED [100%]

============================== 10 passed in 1.60s ==============================
```

### Core Test Suite with Real DB
- Pre-existing unrelated failure: `test_scope_preserves_original_sql_error` (RLS test)
- New test addition: 1 test in `test_cdc_shutdown.py`
- No regressions introduced

## Self-Review Checklist

✅ **Completeness**
- All 6 steps of brief implemented
- New test passes
- `run()` correctly wired with 3 required lines + final flush
- Nothing else in `run()` was touched

✅ **Quality**
- Docstring preserved and accurate
- `signal` import added correctly
- `_ShutdownState` class follows `_WorkerState` patterns
- No code duplication

✅ **Discipline**
- No scope creep
- Small, surgical change as specified
- Signal handling tested in isolation (correct strategy per brief)
- NOT testing `run()` end-to-end (intentional limitation)

✅ **Code Style**
- Pre-commit hooks: ruff format/check, import-linter, commitlint all passed
- Commit message matches brief exactly

## Design Rationale

### Pattern Consistency
`_ShutdownState` mirrors `_WorkerState`:
- Single-purpose state class
- Simple public interface (`should_stop()`)
- Internal signal handler (`handle_sigterm()`)
- Separate from business logic

### Signal Handling Strategy
- SIGTERM sets flag (safe operation in signal handler)
- Flag checked in `stream_changes()` loop on each iteration
- Final flush ensures buffered rows aren't lost
- Leverages existing `should_stop` contract in consumer

## Known Limitations

Per task brief (intentional design):
1. Does NOT test `run()` end-to-end (requires real CDC_DATABASE_URL + S3)
2. Tests ONLY the signal handling mechanism in isolation
3. Relies on `stream_changes()` checking `should_stop()` at loop boundaries

These are by design and explicitly required by the brief.

## Concerns

None identified. The implementation:
- Matches brief requirements exactly
- Passes all tests
- Introduces no regressions
- Maintains code discipline and style
- Follows established patterns in codebase
