# Task 1 Report: Core — DatasetPayload gains source=arcgis + per-source validator registry

## Summary

Successfully implemented Task 1 of SP-14k following strict TDD workflow. Extended `DatasetPayload` Pydantic model to support `source: "arcgis"` alongside existing `"collection"` source, and converted the dataset-kind config validator registry from a single global validator to a per-source registry keyed by the source type.

## Implementation Details

### What Was Implemented

1. **Extended `DatasetPayload` schema** (`core/app/configs/schemas.py`)
   - Added `source: Literal["collection", "arcgis"]` to replace `source: Literal["collection"]`
   - Made `collectionId: str | None = None` (optional, required only for "collection" source)
   - Added `arcgisItemId: str | None = None` (optional, required only for "arcgis" source)
   - Added `@model_validator(mode="after")` to enforce source-specific field requirements:
     - collection source requires collectionId, must not set arcgisItemId
     - arcgis source requires arcgisItemId, must not set collectionId

2. **Converted validator registry to per-source** (`core/app/configs/dataset_validation.py`)
   - Replaced single `_validator` global with `_validators: dict[str, DatasetValidator]`
   - Changed signature of `register_dataset_validator(source: str, validator)` to accept source key
   - Updated `validate_dataset_payload()` to lookup validator by `payload.source`

3. **Updated collection validator registration** (`core/app/collections/dataset_validation.py`)
   - Changed `register_dataset_validator(_validate_dataset_payload)` to `register_dataset_validator("collection", _validate_dataset_payload)`

4. **Added arcgis validator module** (`core/app/harvest/dataset_validation.py`, new)
   - Implements `_validate_arcgis_dataset_payload()` function
   - Validates that arcgis item exists via `harvest_repo.get_feature_layer_record()`
   - Validates user has read access to the harvested item
   - Uses same "not found" error message for both missing item and access denied (security)
   - Registers with `register_dataset_validator("arcgis", _validate_arcgis_dataset_payload)`

5. **Wired imports** (`core/app/main.py`)
   - Added import of `app.harvest.dataset_validation` module for side effect of validator registration

6. **Pydantic-level tests** (`core/tests/test_dataset_config_schema.py`)
   - Added 4 new tests validating schema constraints:
     - `test_dataset_config_arcgis_source_valide`: arcgis source with arcgisItemId works
     - `test_dataset_config_collection_source_sans_collection_id_rejete`: collection source without collectionId rejected
     - `test_dataset_config_arcgis_source_sans_arcgis_item_id_rejete`: arcgis source without arcgisItemId rejected
     - `test_dataset_config_arcgis_source_avec_collection_id_rejete`: arcgis source with collectionId rejected

7. **HTTP-level tests** (`core/tests/test_create_dataset_arcgis.py`, new)
   - Creates test fixture with 2 harvested items (one readable by alice, one owned by bob)
   - Tests dataset creation with readable arcgis layer succeeds
   - Tests dataset creation with non-existent item returns 422 with "arcgis layer not found"
   - Tests dataset creation with unreadable item returns same 422 message (no info leakage)

## TDD Evidence

### Step 2: RED - Pydantic tests fail as expected

**Command:** `cd core && uv run pytest tests/test_dataset_config_schema.py -v`

**Output before implementation:**
```
FAILED tests/test_dataset_config_schema.py::test_dataset_config_arcgis_source_valide
pydantic_core._pydantic_core.ValidationError: 2 validation errors for BuilderConfig
dataset.source: Input should be 'collection' [type=literal_error, input_value='arcgis']
dataset.collectionId: Field required [type=missing_field]
```

### Step 4: GREEN - All pydantic tests pass

**Command:** `cd core && uv run pytest tests/test_dataset_config_schema.py -v`

**Output after implementation:**
```
9 passed in 0.71s
- test_dataset_config_valide PASSED
- test_dataset_config_sans_payload_rejete PASSED
- test_dataset_config_colonnes_optionnelles PASSED
- test_dataset_config_time_field_and_reacts_to_extent_optional PASSED
- test_dataset_config_time_field_and_reacts_to_extent_default PASSED
- test_dataset_config_arcgis_source_valide PASSED
- test_dataset_config_collection_source_sans_collection_id_rejete PASSED
- test_dataset_config_arcgis_source_sans_arcgis_item_id_rejete PASSED
- test_dataset_config_arcgis_source_avec_collection_id_rejete PASSED
```

### Step 7: GREEN - Existing collection tests still pass

**Command:** `cd core && uv run pytest tests/test_create_dataset.py -v`

**Output:**
```
4 passed in 8.87s
- test_create_dataset_avec_collection_existante PASSED
- test_create_dataset_collection_inexistante_rejete PASSED
- test_update_dataset_collection_inexistante_rejete PASSED
- test_create_dataset_collection_non_lisible_rejete_avec_meme_message PASSED
```

### Step 11: RED (EXPECTED) - Arcgis tests fail with expected error

**Command:** `cd core && uv run pytest tests/test_create_dataset_arcgis.py -v`

**Output:**
```
FAILED tests/test_create_dataset_arcgis.py::test_create_dataset_arcgis_avec_couche_moissonnee_visible
AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'
```

**This failure is expected and by design** - `get_feature_layer_record()` is added in Task 2. Per the brief, this test failure should be committed as-is.

### Final: Full test suite validation

**Command:** `cd core && uv run pytest`

**Output:**
```
============ 3 failed, 812 passed, 106 skipped in 139.54s =============
```

- **3 failed**: The 3 arcgis dataset tests in `test_create_dataset_arcgis.py` (expected, Task 2 will fix)
- **812 passed**: All other tests including all 9 pydantic schema tests
- **106 skipped**: Existing skipped tests (postgis-dependent, no docker)

## Files Changed

```
Modified:
- core/app/configs/schemas.py               (DatasetPayload extended)
- core/app/configs/dataset_validation.py    (registry converted to per-source)
- core/app/collections/dataset_validation.py (registration keyed by "collection")
- core/app/main.py                          (added harvest.dataset_validation import)
- core/tests/test_dataset_config_schema.py  (added 4 pydantic tests)

Created:
- core/app/harvest/dataset_validation.py    (arcgis validator)
- core/tests/test_create_dataset_arcgis.py  (3 HTTP-level arcgis tests)
```

## Self-Review Findings

### Validation

1. **Backward compatibility verified**: All existing collection-based dataset tests pass unchanged
2. **Pydantic validation complete**: Both positive (valid arcgis config) and negative cases (missing required fields, conflicting fields) properly tested and validated
3. **Authorization logic intact**: Permission checks for arcgis layers follow same pattern as collections (same error message for "not found" vs "no access")
4. **Code follows conventions**: 
   - New file has Apache-2.0 license header
   - Conventional commit message with (SP-14k) suffix
   - Validator registration pattern mirrors existing collection registration
   - Comments explain the registry indirection for architectural clarity

### Edge Cases Covered

1. Arcgis source with collectionId set → rejected by validator
2. Collection source with arcgisItemId set → rejected by validator
3. Missing required field for source type → rejected by validator
4. Unreadable harvested layer → 422 with safe error message (no leakage)
5. Non-existent harvested layer → 422 with same safe error message

## Known Red Test

The 3 tests in `core/tests/test_create_dataset_arcgis.py` fail with:
```
AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'
```

This is **expected and by design**. The function `get_feature_layer_record()` is defined and implemented in Task 2, which runs immediately after this task. Per the brief instructions (§Interfaces), this test must remain red until Task 2 lands. Once Task 2 is merged, these tests will turn green without any changes to Task 1's code.

## Commit

```
ed74164 feat(core): DatasetPayload gains source=arcgis, per-source validator registry (SP-14k)
```

7 files changed: 196 insertions(+), 12 deletions(-)
- Created: `core/app/harvest/dataset_validation.py`
- Created: `core/tests/test_create_dataset_arcgis.py`
- Modified: 5 existing files as specified in brief
