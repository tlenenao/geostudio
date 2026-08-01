# Task 2 Report: Shell — pass `bucket` through `itemClient.queryDataSource`

## What Was Implemented

Added support for passing the `bucket` query key through to the core's `/collections/{id}/aggregate` endpoint. This ensures that when a statistics-type DataSource has a `bucket` parameter in its query, it is posted as `body.bucket` rather than leaking into `body.filters`.

## Files Changed

- `shell/src/api/itemClient.ts`: Added "bucket" to STAT_KEYS set (line 40) and added bucket passthrough in buildAggregateBody function (line 55)
- `shell/src/api/itemClient.test.ts`: Added test "queryDataSource sends a bucket query key as body.bucket, not as a filter" (after line 705)

## TDD Evidence

### RED (Failing Test)

Command:
```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "sends a bucket query key"
```

Expected Failure Output:
```
AssertionError: expected undefined to be 'week' // Object.is equality
  expected: "week"
  received: undefined
  
  ❯ src/api/itemClient.test.ts:719:26
```

**Why Expected**: The test was checking that `posted!.bucket` equals "week", but prior to the implementation, the bucket value was not being extracted and passed as a top-level body property. Instead, it remained undefined.

### GREEN (Passing Test)

Command:
```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "sends a bucket query key"
```

Passing Output:
```
 ✓ src/api/itemClient.test.ts (83 tests | 82 skipped) 39ms

 Test Files  1 passed (1)
      Tests  1 passed | 82 skipped (83)
```

## Full Non-Regression Run

Command:
```bash
cd shell && npx vitest run src/api/itemClient.test.ts
```

Result:
```
 ✓ src/api/itemClient.test.ts (83 tests) 480ms

 Test Files  1 passed (1)
      Tests  83 passed (83)
```

All 83 tests pass, confirming no regression in existing functionality.

## Implementation Details

### 1. STAT_KEYS Update (line 40)
Added "bucket" to the Set of reserved statistics configuration keys that are not treated as filters:
```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox", "bucket"]);
```

### 2. buildAggregateBody Update (line 55)
Added bucket passthrough immediately after field handling:
```ts
if (query.bucket) body.bucket = String(query.bucket);
```

This follows the same pattern as the existing field handling and ensures the bucket value is stringified and placed directly on the body object.

## Self-Review

**Completeness**: All requirements from the brief have been implemented:
- Test added and verified to fail before implementation
- Both code changes from the brief applied exactly
- Full test suite passes with no regressions
- Conventional commit message applied

**Quality**: Implementation is minimal and follows existing patterns:
- The bucket passthrough mirrors the field handling pattern
- Addition to STAT_KEYS prevents bucket from being treated as a filter
- No unnecessary code added beyond the brief

**Discipline**: Only the specified changes were made:
- No additional features or refactoring
- Follows the exact code from the brief
- Two files modified only (test + implementation)

**Testing**: TDD workflow executed correctly:
- Test written first and failed as expected
- Implementation added to make test pass
- Full suite run to verify no regressions

## Concerns

None. The implementation is straightforward, follows established patterns in the codebase, and passes all tests including the new test and all existing tests.

## Commit

```
26d925c feat(shell): pass bucket through to /collections/{id}/aggregate
```

## Ready for Next Tasks

This task enables Tasks 3, 4, and 5 which rely on bucketed sparkline/compare queries reaching the core correctly. The passthrough is now in place and tested.
