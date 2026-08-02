# Task 3 Report: Core — server-side binned histogram (`bins`)

**Date:** 2026-08-02
**Branch:** `dev`
**Commit:** `4ce6421` (feat(core): server-side binned histogram via bins param on /aggregate (SP-14f))

## Summary

Successfully implemented server-side binned histogram functionality for GeoStudio's analytics `/aggregate` endpoint. Task 3 is the final core task of SP-14f and builds on Tasks 1-2 which had already implemented multi-field groupBy and tidy row structure.

## What Was Implemented

### 1. **Validation Rules** (`_validate_fields`)
Added comprehensive validation for the `bins` parameter:
- Rejects `bins` without a `field` → raises `UnknownAggregateField("bins", "bins requires a field")`
- Rejects `bins` combined with `groupBy` → raises `UnknownAggregateField("bins", "bins cannot combine with groupBy")`
- Rejects `bins` outside the range `1..100` → raises `UnknownAggregateField("bins", "bins must be between 1 and 100")`

### 2. **Binned Histogram Engine** (`_run_binned_histogram`)
New function implementing equal-width histogram binning:
- **Two-query approach for non-constant fields:**
  - First query: `MIN/MAX` to establish the data range [lo, hi]
  - Second query: Uses `LEAST`/`FLOOR` bucket assignment: `LEAST(bins - 1, FLOOR((field - lo) / width))`
  
- **Special handling for constant fields** (lo == hi):
  - Returns a single bucket with `bucketStart == bucketEnd == field_value`
  
- **Null handling:**
  - Filters out NULL values from binning calculations
  - Handles empty result sets gracefully (returns empty list)
  
- **Return format:** List of dictionaries with structure:
  ```json
  {
    "bucketIndex": int,
    "bucketStart": float,
    "bucketEnd": float,
    "count": int
  }
  ```
  - Only non-empty buckets are returned (sparse representation)
  - Rows are ordered by `bucketIndex`
  - The `bucketIndex` is used as the `category_key` in response (enabling proper row id derivation in shell)

### 3. **Request-Response Wiring** (`run_collection_aggregate`)
Integrated binning path into the main aggregate function:
- Checks `request.bins is not None` immediately after building WHERE clause
- Returns early with binned histogram data before multi-field groupBy logic
- Uses `"bucketIndex"` as the fixed category_key (real column, not literal label)

### 4. **Test Coverage**
Added 6 comprehensive test cases covering:
- **test_bins_produces_equal_width_buckets**: Verifies correct equal-width distribution with sparse bins (pop range [1,10], 3 bins → only bins 0 and 2 populated)
- **test_bins_on_a_constant_field_returns_one_bucket**: Handles degenerate case where min == max
- **test_bins_without_field_raises**: Validates error when field is missing
- **test_bins_with_groupby_raises**: Ensures bins and groupBy are mutually exclusive
- **test_bins_out_of_bounds_raises**: Verifies both 0 and 101 are rejected (valid range is 1-100)
- **test_bins_narrowed_by_attribute_filter**: Confirms filters narrow the histogram range correctly

## Test Results

### Step 2: Initial Failure (before implementation)
All 6 bins tests FAILED as expected — the feature was not yet implemented.

### Step 5: Targeted Tests (after implementation)
```
cd core && uv run pytest tests/test_analytics_aggregate.py -k bins -v
```
Result: **6 PASSED** ✓
- test_bins_produces_equal_width_buckets PASSED
- test_bins_on_a_constant_field_returns_one_bucket PASSED
- test_bins_without_field_raises PASSED
- test_bins_with_groupby_raises PASSED
- test_bins_out_of_bounds_raises PASSED
- test_bins_narrowed_by_attribute_filter PASSED

### Step 6: Full Core Suite (non-regression)
```
cd core && uv run pytest -v
```
Result: **807 PASSED, 106 SKIPPED** ✓

This confirms:
- All existing tests (606+ from SP-0 through SP-13) remain green
- New tests (6 from Tasks 1-3 combined) pass
- No regression introduced in any other module

## Files Changed

1. **core/app/analytics/aggregate.py** (+78 lines)
   - `_validate_fields`: Added bins validation block (7 lines)
   - `_run_binned_histogram`: New function (37 lines) implementing the binning logic
   - `run_collection_aggregate`: Added bins handling block (6 lines)

2. **core/tests/test_analytics_aggregate.py** (+60 lines)
   - 6 new test functions (60 lines) covering all validation rules and binning scenarios

## Self-Review Findings

### Code Quality
- ✓ SQL parameter ordering verified: placeholders in `bucket_expr` (`?` × 3) align correctly with `params = [bins, lo, width, *where_params]`
- ✓ Exception types consistent: Uses `UnknownAggregateField` throughout, matching existing pattern
- ✓ Docstring unnecessary: Function is implementation-detail only; tests document the contract
- ✓ Edge cases covered:
  - Empty dataset (returns `[]`)
  - Null values (filtered via `WHERE field IS NOT NULL`)
  - Constant field (single bucket at lo/hi)
  - Filters narrowing range (cascaded through where_sql and where_params)

### Design Decisions
- ✓ `category_key = "bucketIndex"` (not `"bins"` literal): Allows shell to reuse existing `statRowId` single-field derivation logic without histogram-specific case
- ✓ Two-query approach (MIN/MAX then bucket): Necessary for equal-width binning; separate round-trip cost negligible on typical histograms (<50 buckets)
- ✓ `LEAST(bins - 1, ...)` clamping: Correctly handles the max value (which would otherwise fall into a non-existent bin), fixing the edge case where hi equals the upper boundary

### Testing
- ✓ Tests use TDD (RED → GREEN → REFACTOR)
- ✓ All validation paths tested (no field, with groupBy, bounds)
- ✓ Both common cases (variable + constant fields) and narrow case (filters) tested
- ✓ Return shape verified exactly (`bucketIndex`, `bucketStart`, `bucketEnd`, `count`)
- ✓ Empty bins correctly omitted from result set

## Known Constraints (from task brief)

None. Task 3 is final and self-contained.

## Integration Notes

This task completes the three-task SP-14f core track:
- **Task 1**: Declared `bins` field in `AggregateRequestBody`, widened `groupBy` to list, tidy rows
- **Task 2**: Implemented tidy row pivoting for multi-field groupBy
- **Task 3** (this): Added validation and binning engine for histogram requests

Next work in the SP-14f pipeline is shell-side (Task 4 onwards: UI/visualization for bins).

## Fix: Non-numeric values in histogram bucket (review round 1)

**Date:** 2026-08-02  
**Reviewer Finding:** Code review identified a SQL NULL-handling bug in `_run_binned_histogram` (line 223)

### The Bug

The `not_null_clause` on line 223 checked the **raw column** instead of the **cast expression**:
```python
# BUGGY:
not_null_clause = f"{_qi(field)} IS NOT NULL"  # checks raw column, not cast result
field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"  # defined above
```

**Impact:** When a row's raw value is non-null but fails `TRY_CAST(... AS DOUBLE)` (e.g., a non-numeric string like `"abc"` in a loosely-typed column from no-code CSV/GeoJSON ingestion):
- The WHERE clause includes the row (because the raw column is not null)
- The `bucket_expr` evaluates the cast: `TRY_CAST("abc" AS DOUBLE)` = `NULL`
- DuckDB's `LEAST(bins-1, NULL)` silently returns `bins-1` (ignoring NULL arguments)
- The row is **silently miscounted into the last histogram bucket** instead of being excluded

**Verified Reproduction:** With `pop = ["1", "2", "abc", "10"]`, `bins=3`:
- Expected buckets: `{0: count 2, 2: count 1}` (the "abc" row excluded)
- Buggy behavior: `{0: count 2, 2: count 2}` (the "abc" row incorrectly added to bucket 2)

### The Fix

Changed line 223 to check the **cast expression** instead of the raw column:
```python
# FIXED:
not_null_clause = f"{field_expr} IS NOT NULL"
```

Now `TRY_CAST('abc' AS DOUBLE) IS NOT NULL` correctly evaluates to `False`, excluding non-numeric rows while including valid numeric ones (including `0`, which is a valid DOUBLE).

### Regression Test

Added `test_bins_excludes_non_numeric_values_from_top_bucket` to verify:
1. Writes a partition with mixed numeric strings and one non-numeric string ("1", "2", "abc", "10")
2. Calls `run_collection_aggregate` with `AggregateRequestBody(field="pop", bins=3)`
3. Asserts the non-numeric row does NOT appear in any bucket and the top bucket count reflects only numeric values
4. **Verified:** Test FAILS against buggy code (bucket 2 has count 2), PASSES against fixed code (bucket 2 has count 1)

### Test Results

**Targeted bins run:**
```
cd core && uv run pytest tests/test_analytics_aggregate.py -k bins -v
```
Result: **7 PASSED** ✓ (6 existing + 1 new regression test)
- test_bins_produces_equal_width_buckets PASSED
- test_bins_on_a_constant_field_returns_one_bucket PASSED
- test_bins_without_field_raises PASSED
- test_bins_with_groupby_raises PASSED
- test_bins_out_of_bounds_raises PASSED
- test_bins_narrowed_by_attribute_filter PASSED
- test_bins_excludes_non_numeric_values_from_top_bucket PASSED ✓ (NEW)

**Full core suite (non-regression):**
```
cd core && uv run pytest -v
```
Result: **808 PASSED, 106 SKIPPED** ✓
- All 807 existing tests remain green
- 1 new regression test passes
- No regression in any other module

### Commit

```
a992b78 fix(core): exclure les valeurs non numériques du dernier bucket de l'histogramme (SP-14f)
```
