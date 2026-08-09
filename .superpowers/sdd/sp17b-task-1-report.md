# Task 1 Report: `ReportSchedulePayload` Schema + `BuilderConfig` Kind Registration

**Date:** 2026-08-09  
**Status:** DONE

## What Was Implemented

Implemented the 9th `BuilderConfig` kind, `"report"`, adding a new `ReportSchedulePayload` schema to the GeoStudio core. This is the foundational schema work for SP-17b ("ReportSchedule").

### Files Modified

1. **`core/app/configs/schemas.py`**
   - Added `ReportSchedulePayload` class (after `AlertRulePayload`, line 316–328)
   - Extended `BuilderConfig.kind` Literal to include `"report"` (line 343)
   - Added `report: ReportSchedulePayload | None = None` field (line 360)
   - Added validation branch in `_require_kind_payload` for `"report"` kind (line 369–371)

2. **`core/tests/test_report_config_schema.py`** (new file)
   - Test file with 5 tests covering all aspects of the schema

## Test Results

### TDD Evidence

**Step 1 – Write failing test:**  
Test file created at `core/tests/test_report_config_schema.py` with all 5 tests.

**Step 2 – Verify failure (expected ImportError):**
```
ERROR tests/test_report_config_schema.py:5: in <module>
    from app.configs.schemas import BuilderConfig, ReportSchedulePayload
E   ImportError: cannot import name 'ReportSchedulePayload' from 'app.configs.schemas'
```
✓ Failure confirmed — exact expected error.

**Step 3 – Implementation:**
- Added `ReportSchedulePayload` class with three fields: `bookmarkItemId`, `refreshPolicy`, `channels`
- Added validator `_require_at_least_one_channel` to enforce at least one notification channel
- Extended `BuilderConfig.kind` Literal from 8 to 9 kinds
- Added `report` field to `BuilderConfig`
- Added validation in `_require_kind_payload` to enforce `report` payload when `kind == "report"`

**Step 4 – Verify pass (all 5 tests green):**
```
tests/test_report_config_schema.py::test_report_schedule_payload_round_trips PASSED
tests/test_report_config_schema.py::test_report_schedule_payload_requires_at_least_one_channel PASSED
tests/test_report_config_schema.py::test_report_schedule_payload_rejects_invalid_cron PASSED
tests/test_report_config_schema.py::test_builder_config_accepts_kind_report PASSED
tests/test_report_config_schema.py::test_builder_config_kind_report_requires_report_payload PASSED

============================== 5 passed in 0.16s ==============================
```

### Full Test Suite Verification

Core test suite after implementation:
- **1327 tests passed**
- **137 tests skipped** (postgis-dependent, expected)
- **0 tests failed** — no regressions

## Implementation Details

### ReportSchedulePayload Schema

```python
class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    refreshPolicy: PipelineRefreshPolicy  # reused from alerts/pipelines
    channels: list[AlertChannel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self
```

**Design rationale:**
- Reuses `PipelineRefreshPolicy` (cron scheduling, already validated)
- Reuses `AlertChannel` discriminated union (webhook + email, already validated)
- Enforces at least one notification channel (users cannot create a report with no way to receive it)
- Fields match interface contract: `bookmarkItemId`, `refreshPolicy`, `channels`

### BuilderConfig Extension

- **Kind Literal:** Extended from 8 to 9 kinds by appending `"report"`
- **Field:** `report: ReportSchedulePayload | None = None` — parallel to existing `alert`, `pipeline`, `bookmark` fields
- **Validation:** Enforces payload presence when `kind == "report"` in `_require_kind_payload`

## Self-Review Findings

✓ **All brief requirements met:**
- Class definition follows exact interface from Step 3 of brief
- Field names and types match specification
- Validator pattern consistent with `AlertRulePayload` and `BookmarkPayload`
- `BuilderConfig` changes follow exact specifications
- No deviation from brief scope

✓ **Test coverage:**
- Round-trip serialization/deserialization
- Channel validation (empty list rejected)
- Cron validation (invalid cron rejected)
- `BuilderConfig.kind` acceptance of `"report"`
- `BuilderConfig` enforcement of `report` payload presence

✓ **No scope creep:**
- No routes created (out of scope)
- No repository layer (out of scope)
- No jobs/workers (out of scope)
- Only schema + tests, exactly as specified

✓ **Code quality:**
- Follows existing patterns in file (validator decorators, error messages)
- Comments document intent (line 318–319: reuse rationale)
- Test file SPDX header present
- No warnings in test output

## Commits

- **`2c7cd20`** — `feat(core): ReportSchedulePayload schema, 9th BuilderConfig kind (SP-17b)`

## Issues/Concerns

None. Implementation is clean, fully tested, and ready for downstream tasks.
