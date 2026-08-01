### Task 2: Shell — pass `bucket` through `itemClient.queryDataSource`

**Files:**
- Modify: `shell/src/api/itemClient.ts:40` (`STAT_KEYS`), `shell/src/api/itemClient.ts:49-71` (`buildAggregateBody`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: nothing new (extends the existing `DataSource.query` vocabulary).
- Produces: a `statistics`-type `DataSource` with `query.bucket` set now posts `body.bucket` to `/collections/{id}/aggregate` instead of leaking into `body.filters`. Task 3/4/5 rely on this to make bucketed sparkline/compare queries reach the core.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/api/itemClient.test.ts`, right after the existing `"queryDataSource sends a bbox query key as body.bbox, not as a filter"` test:

```ts
test("queryDataSource sends a bucket query key as body.bucket, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "annee", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "annee", bucket: "week", agg: "count" },
  });
  expect(posted!.bucket).toBe("week");
  expect(posted!.filters).toBeUndefined();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "sends a bucket query key"`
Expected: FAIL — `posted!.bucket` is `undefined` (it currently lands in `body.filters.bucket` instead).

- [ ] **Step 3: Implement the passthrough**

In `shell/src/api/itemClient.ts:40`:

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox", "bucket"]);
```

In `shell/src/api/itemClient.ts:49-72` (`buildAggregateBody`), add the `bucket` line next to `field`:

```ts
function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (query.bucket) body.bucket = String(query.bucket);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): pass bucket through to /collections/{id}/aggregate"
```

---

