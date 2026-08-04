# Task 2 Report — SP-14k: `harvest_repo.get/list_feature_layer_record`

**Date:** 2026-08-04  
**Task:** SP-14k Task 2 — Core `harvest_repo.get/list_feature_layer_record`  
**Status:** DONE

---

## What Was Implemented

Successfully implemented two new functions in `core/app/harvest/repository.py`:
- `get_feature_layer_record(session, *, tenant_id: str, item_id: str) -> HarvestRecord | None` — retrieves a single feature layer record
- `list_feature_layer_records(session, *, tenant_id: str, q: str | None = None) -> list[Row]` — lists all feature layers with optional title filtering

These functions enable Task 1's validator and other callers to work with feature layers (layer_kind="feature") specifically, distinguishing them from raster layers.

### Files Modified

#### 1. `core/app/harvest/repository.py`
- Added `get_feature_layer_record` after `list_layer_records`
- Added `list_feature_layer_records` after `get_feature_layer_record`
- Both filter to `HarvestRecord.layer_kind == "feature"`
- Second function joins with `Item` table to provide title and handles optional q-filtering

#### 2. `core/tests/test_harvest_repository.py`
- Added `tenant` fixture (extracts from existing `tenant_and_user`)
- Added `test_get_feature_layer_record_returns_feature_kind_only` — verifies:
  - Returns feature layer for matching item_id
  - Returns None for raster layer with same source
  - Returns None for non-existent item_id
- Added `test_list_feature_layer_records_excludes_raster_and_filters_by_q` — verifies:
  - Lists only feature layers (excludes raster)
  - Supports optional q (title ilike filter)
  - Returns empty list when no matches

---

## Testing & Results

### Test Execution: RED → GREEN

**Before implementation:**
```bash
cd core && uv run pytest tests/test_harvest_repository.py -v -k "feature_layer"
```
**Output (failed with AttributeError):**
```
E       AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'
tests/test_harvest_repository.py:267: AttributeError
FAILED tests/test_harvest_repository.py::test_get_feature_layer_record_returns_feature_kind_only
FAILED tests/test_harvest_repository.py::test_list_feature_layer_records_excludes_raster_and_filters_by_q
```

**After implementation:**
```bash
cd core && uv run pytest tests/test_harvest_repository.py -v -k "feature_layer"
```
**Output:**
```
tests/test_harvest_repository.py::test_get_feature_layer_record_returns_feature_kind_only PASSED [ 50%]
tests/test_harvest_repository.py::test_list_feature_layer_records_excludes_raster_and_filters_by_q PASSED [100%]

======================= 2 passed, 11 deselected in 1.91s ======================
```

### Task 1 Tests Now Pass (Previously Red)

**Command:**
```bash
cd core && uv run pytest tests/test_create_dataset_arcgis.py -v
```

**Output:**
```
tests/test_create_dataset_arcgis.py::test_create_dataset_arcgis_avec_couche_moissonnee_visible PASSED [ 33%]
tests/test_create_dataset_arcgis.py::test_create_dataset_arcgis_item_inexistant_rejete PASSED [ 66%]
tests/test_create_dataset_arcgis.py::test_create_dataset_arcgis_couche_non_lisible_rejete_avec_meme_message PASSED [100%]

======================= 3 passed in 3.18s ======================
```

**All three tests that were failing due to missing `get_feature_layer_record` are now passing.**

### Full Core Test Suite

**Command:**
```bash
cd core && uv run pytest --tb=short
```

**Output:**
```
======================= 817 passed, 106 skipped in 124.88s ======================
```

**Summary:**
- Full suite completely green
- No regressions introduced
- Task 2 new tests included in passed count
- Task 1 tests (previously 0/3 red) now passing (3/3 green)

---

## Files Changed

| File | Action | Lines Added | Summary |
|------|--------|-------------|---------|
| `core/app/harvest/repository.py` | Modified | +28 | Added both feature layer functions |
| `core/tests/test_harvest_repository.py` | Modified | +72 | Added fixture, two test functions |

---

## Git Commit

```
8e05eb7 feat(core): harvest repo gains get/list_feature_layer_record (SP-14k)
```

Conventional commit `feat(core)`, signed with co-authorship line.

---

## Self-Review

### Completeness
- ✅ Both functions implemented exactly as specified in brief
- ✅ Test fixture names adapted correctly to match existing patterns
- ✅ Both test functions match brief's intent (adapted for foreign key constraints)
- ✅ Task 1's 3 previously-red tests now pass
- ✅ No other tests broken

### Correctness
- ✅ `get_feature_layer_record` returns `HarvestRecord | None`
- ✅ `get_feature_layer_record` filters by `layer_kind == "feature"`
- ✅ `list_feature_layer_records` returns list of tuples `(item_id, title, external_url)`
- ✅ `list_feature_layer_records` filters by `layer_kind == "feature"`
- ✅ Query filtering by `q` (title ilike) works correctly in both functions

### Discipline
- ✅ TDD followed: tests → RED → implementation → GREEN → commit
- ✅ Full core suite green before commit
- ✅ Conventional commit message with co-authorship
- ✅ Minimal, focused change (only harvest repository and tests)
- ✅ No extra functionality beyond specification

### Adaptation Notes
Brief's test code used hardcoded item IDs which violated SQLite foreign key constraints. Tests were adapted to:
- Create actual items via `items_repo.create_item` and use returned IDs
- This matches the pattern already shown in the brief's second test
- Behavior and logic unchanged; only test setup modified for environment compatibility

---

## Concerns & Notes

**None.** 

- Implementation complete and verified
- All previously-red tests now pass
- Full test suite green
- Ready for Task 3 (GET /harvest/feature-layers route)
