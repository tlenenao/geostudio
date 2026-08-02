### Task 4: Shell — `itemClient` passes `groupBy` arrays and `bins` through, builds composite ids

**Files:**
- Modify: `shell/src/api/itemClient.ts:40` (`STAT_KEYS`), `shell/src/api/itemClient.ts:49-73` (`buildAggregateBody`), `shell/src/api/itemClient.ts:619-630` (`queryDataSource`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `buildAggregateBody` forwards `query.groupBy` as a `string[]` when it's an array (unchanged `string` otherwise), and forwards `query.bins` as a `number`. New helper `statRowId(row: Record<string, unknown>, categoryKey: string | string[]): string` — joins multi-field values with `"|"` for a stable per-row id; unchanged single-field behavior otherwise.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("queryDataSource sends an array groupBy as-is in the aggregate request body", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: ["region", "annee"], rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "count" },
  });
  expect(posted!.groupBy).toEqual(["region", "annee"]);
});

test("queryDataSource builds a composite id when categoryKey is a multi-field array", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: ["region", "annee"],
        rows: [{ region: "Nord", annee: "2025", value: 10 }],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord|2025", properties: { region: "Nord", annee: "2025", value: 10 } },
  ]);
});

test("queryDataSource sends a bins query key as body.bins, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "bucketIndex", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { field: "pop", bins: 5 },
  });
  expect(posted!.bins).toBe(5);
  expect(posted!.filters).toBeUndefined();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "groupBy|composite id|bins query"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `shell/src/api/itemClient.ts`, replace line 40:

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox", "bucket", "bins"]);
```

Replace `buildAggregateBody` (lines 49-73):

```ts
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

// Multi-field groupBy responses carry no single categorical key — this joins
// the group columns' values into a stable per-row id (single-field case
// unchanged: same as `String(row[categoryKey])` today).
function statRowId(row: Record<string, unknown>, categoryKey: string | string[]): string {
  if (Array.isArray(categoryKey)) return categoryKey.map((k) => String(row[k] ?? "")).join("|");
  return String(row[categoryKey] ?? "");
}
```

In `queryDataSource` (lines 626-630), replace:

```ts
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${resolved.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
      }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS — new tests plus full existing file green.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient forwards multi-field groupBy and bins to /aggregate (SP-14f)"
```

---

