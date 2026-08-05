# Task 3 Report: Core — `crossFilterLinks` on `DatasetPayload`

## Summary

Successfully implemented the `crossFilterLinks` field on `DatasetPayload` with discriminated-union schema for cross-filter links between datasets. The field accepts an optional list of attribute-based or spatial link configurations, each with mode-specific validation.

## What Was Implemented

### Interfaces Added

1. **`DatasetCrossFilterLinkAttribute`** — attribute-based cross-filter link:
   - `mode: Literal["attribute"] = "attribute"` (discriminator)
   - `targetDatasetId: str` — dataset to filter
   - `sourceField: str` — column in this dataset
   - `targetField: str` — column in target dataset

2. **`DatasetCrossFilterLinkSpatial`** — spatial cross-filter link:
   - `mode: Literal["spatial"] = "spatial"` (discriminator)
   - `targetDatasetId: str` — dataset to filter
   - `precision: Literal["bbox", "exact"] = "bbox"` — defaults to bbox

3. **`DatasetCrossFilterLink`** — discriminated union type alias:
   - Pydantic `Field(discriminator="mode")` routing on `mode` field
   - Rejects unknown modes at validation time

4. **`DatasetPayload.crossFilterLinks`** — list field:
   - Type: `list[DatasetCrossFilterLink]`
   - Default: `[]` (empty list via `Field(default_factory=list)`)

### Files Modified

- **`core/app/configs/schemas.py`**
  - Line 2: Added `Annotated` to imports
  - Lines 95–111: Inserted three new model classes + type alias
  - Line 122: Added `crossFilterLinks` field to `DatasetPayload`

- **`core/tests/test_dataset_config_schema.py`**
  - Lines 83–125: Appended 5 new tests (84 lines total)

## Testing

### TDD Sequence

#### RED Phase (Failing Tests)

Command:
```
cd core && uv run pytest tests/test_dataset_config_schema.py -k cross_filter -v
```

**Exit:** 1 (FAILED)
**Output:** 5 FAILED (attribute and mode errors):
- `test_dataset_config_cross_filter_links_default_empty`: `AttributeError: 'DatasetPayload' object has no attribute 'crossFilterLinks'`
- `test_dataset_config_attribute_cross_filter_link`: Same AttributeError (field does not exist)
- `test_dataset_config_spatial_cross_filter_link_defaults_to_bbox_precision`: Same AttributeError
- `test_dataset_config_spatial_cross_filter_link_exact_precision`: Same AttributeError
- `test_dataset_config_cross_filter_link_unknown_mode_rejected`: `Failed: DID NOT RAISE ValidationError` (Pydantic silently drops unknown field by default)

**Reason for Failure (Expected):** Schema models did not yet define `crossFilterLinks` field or discriminated union types.

#### GREEN Phase (Passing Tests)

Command:
```
cd core && uv run pytest tests/test_dataset_config_schema.py -v
```

**Exit:** 0 (PASSED)
**Output:** 14 passed (9 existing + 5 new)

```
tests/test_dataset_config_schema.py::test_dataset_config_valide PASSED   [  7%]
tests/test_dataset_config_schema.py::test_dataset_config_sans_payload_rejete PASSED [ 14%]
tests/test_dataset_config_schema.py::test_dataset_config_colonnes_optionnelles PASSED [ 21%]
tests/test_dataset_config_schema.py::test_dataset_config_time_field_and_reacts_to_extent_optional PASSED [ 28%]
tests/test_dataset_config_schema.py::test_dataset_config_time_field_and_reacts_to_extent_default PASSED [ 35%]
tests/test_dataset_config_schema.py::test_dataset_config_arcgis_source_valide PASSED [ 42%]
tests/test_dataset_config_schema.py::test_dataset_config_collection_source_sans_collection_id_rejete PASSED [ 50%]
tests/test_dataset_config_schema.py::test_dataset_config_arcgis_source_sans_arcgis_item_id_rejete PASSED [ 57%]
tests/test_dataset_config_schema.py::test_dataset_config_arcgis_source_avec_collection_id_rejete PASSED [ 64%]
tests/test_dataset_config_schema.py::test_dataset_config_cross_filter_links_default_empty PASSED [ 71%]
tests/test_dataset_config_schema.py::test_dataset_config_attribute_cross_filter_link PASSED [ 78%]
tests/test_dataset_config_schema.py::test_dataset_config_spatial_cross_filter_link_defaults_to_bbox_precision PASSED [ 85%]
tests/test_dataset_config_schema.py::test_dataset_config_spatial_cross_filter_link_exact_precision PASSED [ 92%]
tests/test_dataset_config_schema.py::test_dataset_config_cross_filter_link_unknown_mode_rejected PASSED [100%]

============================== 14 passed in 0.20s ==============================
```

### Full Suite Regression Test

Command:
```
cd core && uv run pytest -q
```

**Exit:** 0 (PASSED)
**Result:** `888 passed, 114 skipped in 130.41s`

Confirms additive change with no regressions — existing payloads without `crossFilterLinks` validate identically, and 5 new tests integrated successfully.

## Test Coverage

All 5 new tests exercise required behavior:

1. **Default empty list** — `crossFilterLinks` omitted defaults to `[]`
2. **Attribute link with all fields** — roundtrip validation of mode-specific fields
3. **Spatial link with default precision** — `precision` omitted defaults to `"bbox"`
4. **Spatial link with explicit precision** — custom `"exact"` precision accepted
5. **Unknown mode rejection** — discriminator rejects invalid `mode` values at validation time

## Self-Review Findings

### Completeness ✓
- All three models defined per brief
- All fields with correct types and defaults
- Discriminated union correctly configured
- Field added to `DatasetPayload` at correct position
- All 5 tests written and passing

### Quality ✓
- Code follows existing conventions (Pydantic, naming style)
- Comments added to discriminated union type alias
- Models reuse `BaseModel` consistently with rest of schema
- Field defaults use `Field(default_factory=list)` pattern matching codebase

### Discipline ✓
- No overbuilding — exactly what brief specifies
- Import statement extended cleanly
- Insertion point (before `DatasetPayload`) matches existing pattern (type definitions → class that uses them)
- TDD strictly followed: RED → implement → GREEN → full suite

### No Issues
- No syntax errors
- No missing imports
- No circular dependencies
- Validation behavior matches test expectations exactly
- Commit message follows conventional format

## Commit

```
d98db7c feat(core): crossFilterLinks on DatasetPayload (SP-14n)
```

Files changed: 2
- `core/app/configs/schemas.py` — +22 lines (imports, 3 models, type alias, field)
- `core/tests/test_dataset_config_schema.py` — +43 lines (5 tests)

Total: 64 insertions, 1 deletion

## Concerns

None. Implementation is complete, tested, and ready for Task 4 (shell types).
