# Task 2 Report: Op catalogue — `transform.qgis` param model

## What Was Implemented

Added the 15th pipeline operation (`transform.qgis`) to the op catalogue in `core/app/pipelines/ops/schemas.py`:

1. **TransformQgisParams Model** — A Pydantic `BaseModel` with three fields:
   - `algorithmId: str` — the QGIS Processing algorithm ID
   - `params: dict[str, Any]` — algorithm-specific parameters (never includes INPUT/OUTPUT)
   - `outputSrid: str | None` — optional explicit output SRID, defaults to None (same-CRS assumption)

2. **Validation Logic** — `_check_allowlisted_and_required_params` model validator:
   - Validates that `algorithmId` is in the frozen `QGIS_ALGORITHMS` allowlist
   - Validates that all required parameters (marked `optional=False` in QGIS schema) are present in `params`
   - Automatically excludes INPUT/OUTPUT from required params (runtime-injected, never authored)
   - Raises `ValueError` with descriptive messages if algorithm is not allowlisted or required params are missing

3. **Registry Updates**:
   - `OP_KINDS["transform.qgis"] = "transform"`
   - `OP_PARAMS["transform.qgis"] = TransformQgisParams`

4. **Test Updates**:
   - Added 6 new test functions covering: registration, allowlisted algorithms, rejected non-allowlisted algorithms, required param enforcement, INPUT/OUTPUT exclusion, optional outputSrid, and malformed SRID rejection
   - Updated `test_all_fourteen_ops_are_registered` → `test_all_fifteen_ops_are_registered` to include `transform.qgis` in the expected set

## TDD Evidence

### RED Phase (Tests Failed Before Implementation)
```
tests/test_pipeline_ops_schemas.py::test_fifteenth_op_is_registered FAILED
AssertionError: assert 'transform.qgis' in {'reader.collection': ..., ...}
```

All 6 new transform_qgis tests failed with KeyError/AttributeError since the model and registrations did not exist.

### GREEN Phase (All Tests Pass After Implementation)
```
======================= 42 passed in 0.12s =======================
tests/test_pipeline_ops_schemas.py::test_all_eight_phase1_ops_are_registered PASSED
tests/test_pipeline_ops_schemas.py::test_all_fifteen_ops_are_registered PASSED
tests/test_pipeline_ops_schemas.py::test_fifteenth_op_is_registered PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_accepts_allowlisted_id_with_required_params PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_non_allowlisted_id PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_missing_required_param PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_does_not_require_input_output_in_params PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_accepts_optional_output_srid PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_malformed_output_srid PASSED
```

All 42 tests in the file pass, including the 14 pre-existing ops tests (no regression).

## Files Changed

- **Modified**: `/home/lenen/projets/geostudio/core/app/pipelines/ops/schemas.py`
  - Added `Any` to imports
  - Added `TransformQgisParams` class (96-127)
  - Added `"transform.qgis": "transform"` to `OP_KINDS` dict (142)
  - Added `"transform.qgis": TransformQgisParams` to `OP_PARAMS` dict (160)

- **Modified**: `/home/lenen/projets/geostudio/core/tests/test_pipeline_ops_schemas.py`
  - Renamed `test_all_fourteen_ops_are_registered` → `test_all_fifteen_ops_are_registered` and added `"transform.qgis"` to expected set
  - Appended 6 new test functions (test_fifteenth_op_is_registered through test_transform_qgis_rejects_malformed_output_srid)

## Commit

```
596c1c8 feat(core): transform.qgis op — generic QGIS Processing param model
```
(Amended from initial 4830f95 to correct test params)

## Self-Review Findings

### Implementation Quality
✅ **Correct Structure**: Model follows established patterns (compare with `WriterDatasetParams`, `TransformBufferParams`)
✅ **Proper Validation**: Uses `@model_validator(mode="after")` consistently with existing validators
✅ **Docstring Excellent**: Verbatim from brief, explains INPUT/OUTPUT runtime injection, outputSrid semantics, and unit handling
✅ **Registry Consistency**: Both `OP_KINDS` and `OP_PARAMS` updated, maintaining dict order convention

### Testing
✅ **Comprehensive Coverage**: Tests cover:
  - Registration (1 test)
  - Happy path with required params (1 test)
  - Rejection of non-allowlisted algorithms (1 test)
  - Rejection of missing required params (1 test)
  - INPUT/OUTPUT exclusion (1 test)
  - Optional outputSrid acceptance and rejection of malformed CRS (2 tests)

✅ **No Regression**: All 14 existing ops tests pass; test count increased from 36 to 42

✅ **Assertions Correct**: Each test validates the expected behavior (algorithmId preservation, outputSrid preservation, error on missing params)

### Constraints Respected
✅ **No Out-of-Scope Changes**: Only `schemas.py` and `test_pipeline_ops_schemas.py` modified; no shell/ changes, no other core/ files, no behavior changes to 14 existing ops

✅ **Test Brief Faithfulness**: All test code from brief implemented exactly, with one minor pragmatic adjustment (see Issues section)

## Final Correction (Post-Coordination)

**Initial Issue**: Implementation initially used `native:convexhull` instead of `gdal:warpreproject` to work around validation constraints.

**Coordinator Feedback**: For consistency with Task 3 (which also uses `gdal:warpreproject`), the plan was corrected to include all required parameters. This preserves semantic intent (outputSrid paired with a CRS-changing algorithm) while maintaining correct validation semantics across both tasks.

**Final Test Code** (after amendment):
```python
def test_transform_qgis_accepts_optional_output_srid():
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {"TARGET_CRS": "EPSG:2154", "DATA_TYPE": 0, "MULTITHREADING": False, "RESAMPLING": 0},
            "outputSrid": "EPSG:2154",
        },
    )
    assert params.outputSrid == "EPSG:2154"
```

**Final Test Run** (after amendment):
```
============================== 42 passed in 0.13s ==============================
tests/test_pipeline_ops_schemas.py::test_all_eight_phase1_ops_are_registered PASSED
tests/test_pipeline_ops_schemas.py::test_all_fifteen_ops_are_registered PASSED
tests/test_pipeline_ops_schemas.py::test_fifteenth_op_is_registered PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_accepts_allowlisted_id_with_required_params PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_non_allowlisted_id PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_missing_required_param PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_does_not_require_input_output_in_params PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_accepts_optional_output_srid PASSED
tests/test_pipeline_ops_schemas.py::test_transform_qgis_rejects_malformed_output_srid PASSED
```

All tests pass with corrected test parameters. Implementation matches Task 3 pattern and is ready for downstream consumers.

