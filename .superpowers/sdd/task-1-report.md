# Task 1 Report: Core — `bucket` param on `/collections/{id}/aggregate`

## Summary

Implemented the optional `bucket` parameter on the `/collections/{id}/aggregate` endpoint to support time-bucketed aggregates. When set to `"day"`, `"week"`, or `"month"`, the grouping expression switches from raw column values to `DATE_TRUNC` results, enabling sparklines and period comparisons in downstream shell work.

## Implementation Details

### Code Changes

#### 1. `core/app/analytics/aggregate.py`

**Import added (line 15):**
```python
from typing import Literal
```

**Field added to AggregateRequestBody (line 33):**
```python
bucket: Literal["day", "week", "month"] | None = None
```

**Guard added to _validate_fields (lines 76-77):**
```python
if request.bucket is not None and not request.groupBy:
    raise UnknownAggregateField("bucket", "bucket requires groupBy")
```

**cat_expr logic updated in run_collection_aggregate (lines 213-216):**
```python
if request.bucket:
    cat_expr = f"DATE_TRUNC({_sql_lit(request.bucket)}, TRY_CAST({_qi(request.groupBy)} AS TIMESTAMP))"
else:
    cat_expr = _qi(request.groupBy) if request.groupBy else "'Total'"
```

#### 2. `core/tests/test_analytics_aggregate.py`

Added 4 test cases:
- `test_bucket_groups_rows_by_day` — verifies day-level bucketing groups 2026-01-05 records together
- `test_bucket_groups_rows_by_month` — verifies month-level bucketing groups January and February separately with correct aggregation
- `test_bucket_without_group_by_raises` — verifies that bucket without groupBy raises `UnknownAggregateField` with field="bucket"
- `test_bucket_on_non_castable_field_groups_under_a_null_bucket` — verifies graceful handling of non-castable dates (NULL truncation)

## TDD Evidence

### GREEN Phase (All Tests Pass)

**Bucket tests execution:**
```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -k bucket -v
```

Result:
```
tests/test_analytics_aggregate.py::test_bucket_groups_rows_by_day PASSED [ 25%]
tests/test_analytics_aggregate.py::test_bucket_groups_rows_by_month PASSED [ 50%]
tests/test_analytics_aggregate.py::test_bucket_without_group_by_raises PASSED [ 75%]
tests/test_analytics_aggregate.py::test_bucket_on_non_castable_field_groups_under_a_null_bucket PASSED [100%]

============================== 4 passed in 2.08s =======================
```

## Non-Regression Suite

**Command:**
```bash
cd core && uv run pytest tests/test_analytics_aggregate.py tests/test_features_aggregate_routes.py -v
```

**Result:**
```
============================== 21 passed in 5.07s =======================
```

All pre-existing tests remain unaffected:
- 13 pre-existing aggregation tests: PASS
- 4 route integration tests: PASS
- 4 new bucket tests: PASS

The `bucket=None` default ensures backward compatibility.

## Files Changed

- `/home/lenen/projets/geostudio/core/app/analytics/aggregate.py` (+18 lines)
- `/home/lenen/projets/geostudio/core/tests/test_analytics_aggregate.py` (+57 lines)

## Commit Information

**Commit SHA:** 1338041
**Subject:** `feat(core): add optional bucket param to /collections/{id}/aggregate`

## Self-Review Findings

### Completeness ✓
- [x] Added `bucket` field to `AggregateRequestBody` with correct type
- [x] Added validation guard for bucket requiring groupBy
- [x] Updated `cat_expr` logic to use `DATE_TRUNC` when bucket is set
- [x] Appended all 4 test cases with correct assertions
- [x] All changes match brief specifications exactly

### Quality ✓
- **Naming:** Field and parameter names follow existing convention (e.g., `groupBy`, `split`)
- **Clarity:** Validation error message is explicit ("bucket requires groupBy")
- **Type Safety:** Used `Literal["day", "week", "month"]` for type checking
- **SQL Safety:** Used helper functions `_sql_lit()` and `_qi()` for proper SQL escaping

### Discipline ✓
- No extra validation added beyond the brief requirement
- No additional bucket modes added (only "day", "week", "month")
- No changes to existing function signatures or behavior
- Implementation is minimal and focused

### Testing ✓
- 4 tests exercise core bucket behavior:
  - Day-level aggregation
  - Month-level aggregation with numeric field aggregation
  - Error case (bucket without groupBy)
  - Edge case (non-castable dates fall through to NULL bucket)
- Tests use existing fixtures and helpers (`_row`, `_write_partition`, `TABLE_INFO`)
- Tests verify both the category_key and row values

### Concerns

None identified. The implementation is straightforward, well-tested, and maintains backward compatibility.
