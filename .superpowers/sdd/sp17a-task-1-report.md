# SP-17a Task 1 Report: PrintLayout — schéma cœur + régénération OpenAPI/TS

**Date:** 2026-08-08  
**Status:** DONE  
**Commit:** `2655508` (feat(core): SP-17a — schéma PrintLayout sur BuilderConfig)

---

## Summary

Successfully implemented the `PrintLayout` Pydantic schema in the GeoStudio core and added optional `printLayout` field to `BuilderConfig`. All 5 unit tests pass, full core test suite (1277 tests) passes with no regressions, OpenAPI and TypeScript types regenerated correctly.

---

## Implementation Details

### Step 1: Test-First (RED)

Created `core/tests/test_configs_schemas.py` with 5 unit tests covering:
- Default values validation
- Invalid input rejection (pageSize="letter" → ValidationError)
- Optional field behavior on BuilderConfig
- Field population on map and app kinds

**RED test output (before implementation):**
```
E   ImportError: cannot import name 'PrintLayout' from 'app.configs.schemas'
ERROR tests/test_configs_schemas.py
```

### Step 2: Implementation (GREEN)

**Modified:** `core/app/configs/schemas.py`

1. Added `PrintLayout` class (8 fields, all with defaults, lines 315–323):
   ```python
   class PrintLayout(BaseModel):
       pageSize: Literal["a4", "a3"] = "a4"
       orientation: Literal["portrait", "landscape"] = "portrait"
       title: str | None = None
       showLegend: bool = True
       showScaleBar: bool = True
       showNorthArrow: bool = False
       cartouche: str | None = None
   ```

2. Added `printLayout` field to `BuilderConfig` (line 343):
   ```python
   printLayout: PrintLayout | None = None
   ```

No changes to validation logic; `printLayout` is optional for all `BuilderConfig.kind` values as specified.

**GREEN test output (after implementation):**
```
tests/test_configs_schemas.py::test_print_layout_defaults PASSED         [ 20%]
tests/test_configs_schemas.py::test_print_layout_rejects_invalid_page_size PASSED [ 40%]
tests/test_configs_schemas.py::test_builder_config_print_layout_optional_and_absent_by_default PASSED [ 60%]
tests/test_configs_schemas.py::test_builder_config_accepts_print_layout_on_map_kind PASSED [ 80%]
tests/test_configs_schemas.py::test_builder_config_accepts_print_layout_on_app_kind PASSED [100%]

============================== 5 passed in 0.17s ===============================
```

### Step 3: OpenAPI Regeneration

**Command:**
```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run python scripts/export_openapi.py openapi.json
```

**Result:** Successfully generated `core/openapi.json` with new `PrintLayout` schema definition.

**Diff stats:**
```
core/openapi.json | 71 +++++++++++++++++++++++++++++++++++++++++++++++++++++++
```

**Verification:** 
- New schema `PrintLayout` added to components/schemas section with all 7 properties
- `printLayout` field added to `BuilderConfig` schema with nullable ref to `PrintLayout`

### Step 4: TypeScript Types Regeneration

**Command:**
```bash
cd shell && npm run gen:api-types
```

**Result:** Successfully generated `shell/src/api/generated/core-schema.d.ts`.

**Diff stats:**
```
shell/src/api/generated/core-schema.d.ts | 35 ++++++++++++++++++++++++++++++++
```

**Verification:**
- `printLayout?: components["schemas"]["PrintLayout"] | null;` added to BuilderConfig interface
- Full `PrintLayout` interface generated with all 7 properties (cartouche, orientation, pageSize, showLegend, showNorthArrow, showScaleBar, title)

### Step 5: Full Test Suite Validation

**Command:**
```bash
cd core && uv run pytest -q
```

**Result:**
```
1277 passed, 137 skipped in 86.37s
```

- All existing tests remain green (no regressions)
- 5 new tests for PrintLayout all pass
- 137 skipped tests unchanged (expected postgis/docker-dependent tests)

---

## Files Changed

| File | Status | Changes |
|------|--------|---------|
| `core/app/configs/schemas.py` | Modified | +PrintLayout class, +printLayout field on BuilderConfig |
| `core/tests/test_configs_schemas.py` | Created | 5 unit tests covering defaults, validation, optionality |
| `core/openapi.json` | Regenerated | +71 lines (PrintLayout schema + field reference) |
| `shell/src/api/generated/core-schema.d.ts` | Regenerated | +35 lines (PrintLayout interface + field) |

---

## Self-Review Findings

### Completeness
- All 5 test cases from brief implemented verbatim ✓
- Both Pydantic class and BuilderConfig field added ✓
- OpenAPI/TS regeneration successful with non-empty diffs ✓
- Commit message follows conventional format ✓

### Code Quality
- Schema structure matches existing patterns in file ✓
- Field types and defaults match brief exactly ✓
- No cross-validation needed (printLayout optional for all kinds) ✓
- Literal type constraints enforce valid values (a4|a3, portrait|landscape) ✓

### Discipline
- Only touched 4 files as specified (schemas.py, test file, 2 generated) ✓
- No unintended changes to validation logic or other fields ✓
- No scope creep (e.g., did not implement PrintLayout consumer routes) ✓

### Testing Coverage
- Defaults validated (constructor with no args)
- Invalid input rejection (ValidationError on bad pageSize)
- Optionality on BuilderConfig (map and app kinds)
- Field population and access

---

## Concerns

None. The task was straightforward, well-specified, and executed without issues.

---

## Commit Details

```
Commit: 2655508
Subject: feat(core): SP-17a — schéma PrintLayout sur BuilderConfig
Files: 4 changed, 163 insertions
  - core/app/configs/schemas.py
  - core/tests/test_configs_schemas.py (new)
  - core/openapi.json (regenerated)
  - shell/src/api/generated/core-schema.d.ts (regenerated)
```

---

## Next Steps (SP-17a Task 2+)

This task establishes the schema foundation. Subsequent tasks in the plan will build:
- Worker routes for print export (POST/GET endpoints)
- Shell UI for PrintLayout editing in builder
- Playwright worker implementation for PDF rendering

The schema is ready for all downstream consumers.
