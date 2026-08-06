# Task 3 Report: `compiler.py` — SRID tracking for `transform.qgis`

## What Was Implemented

Modified `core/app/pipelines/compiler.py` to add SRID tracking for the new `transform.qgis` pipeline operation:

1. **Import Addition**: Added `TransformQgisParams` to the imports from `app.pipelines.ops.schemas`.

2. **`transform_output_srid` Branch**: Added a new conditional branch before the final `return input_srid`:
   - When `op == "transform.qgis"`, validates the `params` dict against `TransformQgisParams` schema
   - If `outputSrid` is explicitly set (e.g., for reprojecting algorithms like `gdal:warpreproject`), extracts the SRID number from the "EPSG:XXXX" format and returns it as an int
   - Otherwise, returns `input_srid` unchanged (same-CRS assumption for ~49 non-reprojecting algorithms in the allowlist)

## TDD Evidence

### RED Phase (Asymmetric Failure)

Ran new tests before implementation:

```
tests/test_pipeline_compiler.py::test_transform_output_srid_qgis_passes_through_by_default PASSED [ 50%]
tests/test_pipeline_compiler.py::test_transform_output_srid_qgis_uses_explicit_output_srid FAILED [100%]
```

**Asymmetry confirmed**: 
- First test passed by accident (existing fallthrough `return input_srid` returns 4326, matching the default expectation)
- Second test failed (current code ignores `outputSrid`, returns 4326 instead of expected 2154)

### GREEN Phase (Both Tests Pass)

After implementation, both targeted tests pass:

```
test_transform_output_srid_qgis_passes_through_by_default PASSED
test_transform_output_srid_qgis_uses_explicit_output_srid PASSED
```

Full test suite run confirms no regressions:

```
============================== 29 passed in 0.81s ===============================
```

All 27 existing tests still pass + 2 new tests.

## Files Changed

- `core/app/pipelines/compiler.py`
  - Added `TransformQgisParams` to import block
  - Added new `if op == "transform.qgis"` branch in `transform_output_srid()` (lines 190-191)

- `core/tests/test_pipeline_compiler.py`
  - Added `test_transform_output_srid_qgis_passes_through_by_default()` (lines 296-302)
  - Added `test_transform_output_srid_qgis_uses_explicit_output_srid()` (lines 305-318)

## Self-Review Findings

✓ **Completeness**: All task steps completed.
  
✓ **Quality**: Implementation matches brief exactly:
  - Uses `.model_validate()` for schema validation
  - Correctly parses "EPSG:XXXX" format via `rsplit(":", 1)[1]`
  - Converts to int for return value
  - Preserves `input_srid` when `outputSrid is None`

✓ **Discipline**:
  - No changes to other ops' SRID logic
  - No files added outside the task scope
  - No modification to unrelated code paths

✓ **Testing**:
  - Both new tests pass (passing and failing cases covered)
  - All existing tests pass (no regressions)
  - Test comments match real `gdal:warpreproject` schema from Task 1

✓ **Verification**:
  - Ran full test file to confirm no side effects
  - Import added in correct alphabetical order
  - Logic is testable, pure (no I/O), and correct

## Issues or Concerns

None. Implementation is complete and verified.

## Commit

```
[dev 0149e19] feat(core): transform.qgis SRID tracking via explicit outputSrid
 2 files changed, 31 insertions(+), 2 deletions(-)
```
