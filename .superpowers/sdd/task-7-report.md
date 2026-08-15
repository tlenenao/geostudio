# Task 7: `build_standalone_bundle_zip` — Report

## Summary

Task 7 has been completed successfully. Added `build_standalone_bundle_zip` function to `core/app/appexport/bundler.py` with comprehensive test coverage. Implementation zips app config, snapshot directory contents, and generated docker-compose.yml/README.md into a self-contained bundle for Autoporté export mode (SP-18c).

**Commit:** `c38f3c8` (dev branch)

## What Was Done

### Step 1: Write Failing Tests (TDD)
Added three new test functions to `core/tests/test_appexport_bundler.py`:
- `_write_snapshot_fixture(tmp_path)` — helper creating nested parquet directory structure with manifest.json
- `test_standalone_bundle_contains_data_manifest_and_compose(tmp_path)` — validates bundle contains all required paths and content
- `test_standalone_bundle_with_empty_snapshot_dir(tmp_path)` — validates bundle handles empty snapshot directory

Updated import to include `build_standalone_bundle_zip` from bundler module.

### Step 2: Verified Tests Failed
Ran: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Result: `ImportError: cannot import name 'build_standalone_bundle_zip'` — expected failure.

### Step 3: Implemented `build_standalone_bundle_zip`
Added to `core/app/appexport/bundler.py`:
- Module constant `_STANDALONE_COMPOSE` — docker-compose.yml content (services/app with ghcr.io/tlenenao/geostudio-appexport-standalone:latest, port 8090, read-only data volume)
- Module constant `_STANDALONE_README` — French README.md with startup instructions, content description, and read-only guarantee
- Function `build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes` — zips:
  - `data/geostudio-app-config.json` (config serialized with model_dump_json)
  - All files from snapshot_dir tree as `data/{relative_path}`
  - `docker-compose.yml` at zip root
  - `README.md` at zip root

Implementation uses os.walk to traverse snapshot directory, preserving nested structure (e.g., snapshot/tenant_id=*/collection_id=*/dt=snapshot/*.parquet).

### Step 4: Verified Tests Pass
Ran: `cd core && uv run pytest tests/test_appexport_bundler.py -v`

Result: **6 tests PASSED** (0.17s)
- test_bundle_contains_runtime_assets_and_frozen_config PASSED
- test_bundle_raises_clearly_when_runtime_dir_missing PASSED
- test_bundle_includes_connection_json_when_provided PASSED
- test_bundle_omits_connection_json_by_default PASSED
- test_standalone_bundle_contains_data_manifest_and_compose PASSED
- test_standalone_bundle_with_empty_snapshot_dir PASSED

## Code Changes

### `core/app/appexport/bundler.py`
- Added two module-level string constants for standalone compose and README templates
- Added function signature: `def build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes`
- Implementation: creates BytesIO buffer → ZipFile with DEFLATE compression → writes config + snapshot tree + compose/readme → returns bytes
- Reuses existing imports (io, os, zipfile, BuilderConfig)

### `core/tests/test_appexport_bundler.py`
- Updated import from `build_bundle_zip` to `build_bundle_zip, build_standalone_bundle_zip`
- Added `_write_snapshot_fixture` helper to create realistic snapshot directory structure
- Added `test_standalone_bundle_contains_data_manifest_and_compose` to validate:
  - All expected file paths present in zip
  - Config and compose content contain required strings
- Added `test_standalone_bundle_with_empty_snapshot_dir` to validate graceful handling of minimal snapshot

## Deviations from Brief

None. Implementation matches brief exactly:
- Verbatim code copied from Step 3 specification
- Import statement updated as specified
- Test code added as specified
- All file paths and content correct
- Commit message matches specification

## Self-Review Notes

**Strengths:**
1. Pure, additive change — existing `build_bundle_zip` function untouched, backward compatible
2. Clear, idiomatic Python (os.walk, zipfile context manager, straightforward logic)
3. Comprehensive test coverage — two test cases covering normal and edge case (empty snapshot)
4. Reuses existing patterns from `build_bundle_zip` (BytesIO buffer, writestr for strings, model_dump_json)
5. No external dependencies added
6. Proper path handling with os.path.relpath maintaining directory structure

**Test Quality:**
- Tests are isolated and use pytest tmp_path fixture for safety
- Fixtures create realistic nested directory structures
- Both file presence and content assertions included
- Edge case (empty snapshot) explicitly tested
- Helper function removes duplication

**Code Style:**
- Consistent with existing bundler.py (imports, naming, minimal comments)
- Matches Python 3.12+ style (f-strings, type hints, context managers)
- README and compose are domain-specific strings (French docs, Dockerfile registry)

**Risk Assessment:**
- No security issues (input is config object and local directory)
- No database access, pure file I/O
- No regression risk (isolated, additive feature)
- Performance acceptable (os.walk, zipfile DEFLATE suitable for snapshot volumes)

## Files Modified

- `core/app/appexport/bundler.py` (implementation)
- `core/tests/test_appexport_bundler.py` (tests)

No other files changed.

## What Comes Next

Task 8 will consume this function: job handler that calls `build_standalone_bundle_zip(config, snapshot_dir=...)` to produce the artifact downloaded by authors in Autoporté mode.

## Fix Report (Task 7 Review Finding)

### Review Finding
`build_standalone_bundle_zip` had a critical silent failure mode: calling `os.walk(snapshot_dir)` when `snapshot_dir` doesn't exist yields zero results, producing an incomplete zip with no error signal. The function would "succeed" with a bundle missing all snapshot data.

### Fix Applied
Added guard at function entry (mirrors existing pattern in `build_bundle_zip`):
```python
if not os.path.isdir(snapshot_dir):
    raise FileNotFoundError(f"snapshot directory not found at {snapshot_dir}")
```
Placed before the `os.walk` loop. Preserves the valid case: an existing directory with just `manifest.json` and no parquet data (legitimate for apps with no DataSources).

### Test Added
New test `test_standalone_bundle_raises_clearly_when_snapshot_dir_missing` in `core/tests/test_appexport_bundler.py` (lines 114–118):
```python
def test_standalone_bundle_raises_clearly_when_snapshot_dir_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        build_standalone_bundle_zip(_config(), snapshot_dir=str(tmp_path / "does-not-exist"))
```

### Test Results
All 7 tests (6 original + 1 new) pass:
```
tests/test_appexport_bundler.py::test_bundle_contains_runtime_assets_and_frozen_config PASSED [ 14%]
tests/test_appexport_bundler.py::test_bundle_raises_clearly_when_runtime_dir_missing PASSED [ 28%]
tests/test_appexport_bundler.py::test_bundle_includes_connection_json_when_provided PASSED [ 42%]
tests/test_appexport_bundler.py::test_bundle_omits_connection_json_by_default PASSED [ 57%]
tests/test_appexport_bundler.py::test_standalone_bundle_contains_data_manifest_and_compose PASSED [ 71%]
tests/test_appexport_bundler.py::test_standalone_bundle_with_empty_snapshot_dir PASSED [ 85%]
tests/test_appexport_bundler.py::test_standalone_bundle_raises_clearly_when_snapshot_dir_missing PASSED [100%]

============================== 7 passed in 0.15s =======================================
```

### Verification
Guard confirmed in place (line 78–79 of `core/app/appexport/bundler.py`):
- ✅ Raises `FileNotFoundError` when `snapshot_dir` is a non-existent path
- ✅ Existing behavior preserved for empty-but-existing directories
- ✅ Error message clear: `"snapshot directory not found at {path}"`

**Commit:** `150ca28` (dev branch)
