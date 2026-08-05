## Task 6 Report: Shell — `geomIntersects` in the aggregate request body

### What Was Implemented

Modified `buildAggregateBody()` in `shell/src/api/itemClient.ts` (lines 65-67) to forward `query.geomIntersects` (a GeoJSON geometry object) to the request body as `body.geomIntersects`, which the server's DuckDB aggregate endpoint (Task 1) understands and uses for spatial filtering.

**Implementation Details:**
- Added conditional check: if `query.geomIntersects` exists and is an object, forward it verbatim to the request body
- Placed immediately after the existing `bbox` handling (line 64), before the generic filters loop
- The object type guard (`typeof query.geomIntersects === "object"`) ensures only actual geometry objects are forwarded, excluding null/undefined
- The generic filters loop naturally excludes `geomIntersects` because it only processes string/number/boolean values

### Testing Evidence

#### RED (Failing Test)

**Command:** `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`

**Result:** Test failed with:
```
AssertionError: expected undefined to deeply equal { Object (type, coordinates) }
```

**Why Expected:** `buildAggregateBody` was not yet handling `query.geomIntersects`, so the posted body did not include it.

**Test Added:** Append to `itemClient.test.ts` line 924:
```typescript
test("queryDataSource sends a geomIntersects query key as body.geomIntersects", async () => {
  const geom = { type: "Point", coordinates: [1, 2] };
  let posted: { geomIntersects?: unknown } | undefined;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as { geomIntersects?: unknown };
      return HttpResponse.json({ categoryKey: "group", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "src-1", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", agg: "count", geomIntersects: geom },
  });
  expect(posted!.geomIntersects).toEqual(geom);
});
```

#### GREEN (Passing Test)

**Command:** `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`

**Result:** Test passed:
```
 ✓ src/api/itemClient.test.ts (103 tests | 102 skipped) 68ms
 ✓ queryDataSource sends a geomIntersects query key as body.geomIntersects
```

**Full Test Suite:** `cd shell && npm run test`

**Result:** All tests passed:
```
 Test Files  111 passed (111)
      Tests  868 passed (868)
```

### Files Changed

1. **shell/src/api/itemClient.ts** (lines 65-67)
   - Added `geomIntersects` forwarding in `buildAggregateBody()`

2. **shell/src/api/itemClient.test.ts** (lines 926-940)
   - Added test case for `geomIntersects` parameter forwarding

### Self-Review Findings

**Completeness:** ✓ All steps from the brief completed
- ✓ Test written and failing
- ✓ Implementation added
- ✓ Test passes
- ✓ Full suite passes
- ✓ Commit created

**Quality:** ✓ Clean, idiomatic implementation
- Implementation follows the existing pattern used for `bbox` handling
- Type guard (`typeof ... === "object"`) prevents accidental forwarding of non-geometry values
- Minimal change: only 3 lines added
- No changes to STAT_KEYS or other configuration needed
- Generic filters loop automatically excludes it (object type exclusion)

**Discipline:** ✓ No overbuilding
- Exactly what the brief specified
- No extra features or unnecessary changes
- Consistent with the codebase style

**Testing:** ✓ Real behavior verified
- TDD followed: RED → GREEN
- Test captures the exact scenario: geometry object forwarded to request body
- Integration verified with full suite
- No regressions

### Issues or Concerns

None. The implementation is minimal, correct, and fully tested.

---

**Commit:** `1e9f120` — feat(shell): forward geomIntersects to the aggregate request body (SP-14n)
