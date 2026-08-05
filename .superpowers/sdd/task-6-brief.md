## Task 6: Shell — `geomIntersects` in the aggregate request body

**Files:**
- Modify: `shell/src/api/itemClient.ts:49-75` (`buildAggregateBody`)
- Test: `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Consumes: `DataSource.query.geomIntersects` (an object, set by Task 5's `derivePatch` for a spatial/exact link).
- Produces: `buildAggregateBody` forwards `query.geomIntersects` verbatim into `body.geomIntersects`, consumed server-side by Task 1's `AggregateRequestBody.geomIntersects`. `bbox` needs no change here — it already flows through `parseBboxQueryValue`, and Task 5's spatial/bbox patch reuses that same `bbox` key.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/api/itemClient.test.ts`, right after the existing `"queryDataSource sends a bbox query key as body.bbox, not as a filter"` test:

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

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`
Expected: FAIL — `buildAggregateBody` never reads `query.geomIntersects`, so `posted!.geomIntersects` is `undefined`.

- [ ] **Step 3: Implement**

In `shell/src/api/itemClient.ts`, extend `buildAggregateBody` (right after the existing `bbox` block):

```typescript
function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (Array.isArray(query.groupBy)) body.groupBy = query.groupBy.map(String);
  else if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (query.bucket) body.bucket = String(query.bucket);
  if (query.bins) body.bins = Number(query.bins);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
  if (query.geomIntersects && typeof query.geomIntersects === "object") {
    body.geomIntersects = query.geomIntersects;
  }
  const filters: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      filters[k] = String(v);
    }
  }
  if (Object.keys(filters).length) body.filters = filters;
  return body;
}
```

(the generic `filters` loop already skips `geomIntersects` implicitly — its value is an object, and the loop's `typeof v === "string" || "number" || "boolean"` guard excludes it, exactly like `measures`/`bbox` today. No change to `STAT_KEYS` is needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t geomIntersects`
Expected: PASS.

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): forward geomIntersects to the aggregate request body (SP-14n)"
```

---

