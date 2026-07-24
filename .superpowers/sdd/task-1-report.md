# Task 1 Report: `HarvestedRecord` gains `copy_filename` (SP-12g)

**Date:** 2026-07-24  
**Executor:** Claude (Haiku 4.5)  
**Task:** SP-12g Task 1 — Add `copy_filename` field to `HarvestedRecord` dataclass

**Status: DONE**

---

## Summary

Task 1 adds a new optional field `copy_filename: str | None = None` to the `HarvestedRecord` frozen dataclass in `core/app/harvest/connectors/base.py`. This field is consumed by later tasks (Task 2 `service.py` and Task 3 CKAN connector) but defaults to None, ensuring full backward compatibility with all 7 existing harvest connectors (STAC, ArcGIS, WMS, WFS, WMTS, CSW, OGC API - Records). Work completed exactly per brief with full TDD discipline. Commit SHA: `3550ecd`.

---

## TDD Execution

### RED Phase: Write Failing Test

**Created File:** `core/tests/test_harvest_base.py`
- 2 focused test cases covering the new field behavior

**Test Run:**
```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_harvest_base.py -v
```

**Output (abbreviated):**
```
tests/test_harvest_base.py::test_copy_filename_defaults_to_none FAILED
  AttributeError: 'HarvestedRecord' object has no attribute 'copy_filename'

tests/test_harvest_base.py::test_copy_filename_can_be_set FAILED
  TypeError: HarvestedRecord.__init__() got an unexpected keyword argument 'copy_filename'

============================== 2 failed in 0.24s
```

**Status:** RED ✓ — Both tests fail as expected. Attribute does not exist, parameter not accepted.

---

### GREEN Phase: Add Field to Dataclass

**Modified File:** `core/app/harvest/connectors/base.py`
- Added line 20: `copy_filename: str | None = None` as the last field in `HarvestedRecord`
- Field placed after existing optional field `raster_tiles_url: str | None = None`
- No other changes to file structure or other code

**Test Run:**
```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_harvest_base.py -v
```

**Output:**
```
tests/test_harvest_base.py::test_copy_filename_defaults_to_none PASSED
tests/test_harvest_base.py::test_copy_filename_can_be_set PASSED

============================== 2 passed in 0.10s
```

**Status:** GREEN ✓ — Both tests pass with pristine output.

---

### Regression Testing: Full Harvest Test Suite

**Test Run:**
```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/ -k harvest -v
```

**Output (abbreviated):**
```
=============== 139 passed, 13 skipped, 693 deselected in 8.41s ================
```

**Detailed Results:**
- **Total selected:** 152 harvest-related tests
- **Passed:** 139 tests ✓
- **Skipped:** 13 tests (postgres/postgis docker requirements)
- **Failed:** 0 tests
- **Status:** No regressions

**Coverage:**
- All 7 harvest connectors (STAC, ArcGIS, WMS, WFS, WMTS, CSW, OGC API - Records)
- Harvest service tests (reference mode, copy mode, error handling, etc.)
- Harvest repository tests (CRUD, status tracking, pagination)
- Harvest routes tests (create, update, delete, run operations)
- Harvest models tests (table creation, round-trip serialization)
- Egress guard tests (SSRF prevention)
- OWS parsing tests (XML safety, namespace handling)
- Layers endpoint tests (filtering, search)

All existing connector tests passed unchanged, confirming backward compatibility.

---

### Commit

**Command:**
```bash
git add core/app/harvest/connectors/base.py core/tests/test_harvest_base.py
git commit -m "feat(core): HarvestedRecord.copy_filename (SP-12g)"
```

**Commit SHA:** `3550ecd`

**Commit Details:**
```
[dev 3550ecd] feat(core): HarvestedRecord.copy_filename (SP-12g)
 2 files changed, 20 insertions(+)
 create mode 100644 core/tests/test_harvest_base.py
```

---

## Files Changed

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `core/app/harvest/connectors/base.py` | Modified | +1 | Added `copy_filename: str \| None = None` as final field |
| `core/tests/test_harvest_base.py` | Created | 21 | Two test cases for default and explicit value behavior |

---

## Test Coverage Summary

**New Tests (2 total): PASS**
1. ✓ `test_copy_filename_defaults_to_none` — Field is None when not supplied
2. ✓ `test_copy_filename_can_be_set` — Field accepts string value when supplied

**Backward Compatibility Verified:**
- All 7 existing connectors use default `None` without any changes
- 139 existing harvest tests continue to pass
- No breaking changes to dataclass initialization or serialization

---

## Self-Review Findings

### Completeness
- ✓ Test file created with exact content from brief
- ✓ Field added to dataclass with exact type and default from brief
- ✓ Field placed as last field (after `raster_tiles_url`)
- ✓ TDD workflow executed: RED → GREEN
- ✓ Full harvest test suite run for non-regression (139 pass, 0 fail)
- ✓ Commit created with exact message from brief

### Correctness & Design
- ✓ **Type annotation:** `str | None` correctly allows string or None
- ✓ **Default value:** `None` as specified preserves existing connector behavior
- ✓ **Frozen dataclass:** Field added to immutable class; no impact on initialization order
- ✓ **Field placement:** Last in class, following Python best practices (optional fields after defaults)
- ✓ **Backward compatibility:** All 7 existing connectors continue to work unchanged

### Code Quality
- ✓ SPDX header present in test file
- ✓ Import path correct: `from app.harvest.connectors.base import HarvestedRecord`
- ✓ Test function names clear and descriptive
- ✓ Test values realistic (external_id, title, etc. properly populated)
- ✓ No extraneous whitespace or formatting issues
- ✓ Follows project test conventions

### Testing
- ✓ Test 1 verifies default None behavior
- ✓ Test 2 verifies explicit value acceptance
- ✓ Both positive/expected paths covered
- ✓ All existing tests remain green (no regressions)
- ✓ Test output pristine (no warnings, no anomalies)

### Discipline
- ✓ Only 2 files modified/created
- ✓ No restructuring of `base.py`
- ✓ No extraneous changes to other modules
- ✓ No comments or documentation added beyond what's specified
- ✓ Minimal, focused changeset

---

## Conclusion

**Status: DONE ✓**

Task 1 completed successfully:
- ✓ 2 new tests PASS (100%)
- ✓ 139 harvest suite tests PASS (full non-regression, 0 failures)
- ✓ Commit created: `3550ecd`
- ✓ All brief requirements met exactly

The field is ready for consumption by:
- **Task 2:** Harvest service enhancement (`service.py`) — will populate this field during copy-mode harvesting
- **Task 3:** CKAN connector implementation — will use this field for local filenames
- **Task 4–5:** Integration into shell and E2E tests
