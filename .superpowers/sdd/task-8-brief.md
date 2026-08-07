### Task 8: Shell — `ItemClient.exportDataSource()`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Consumes: `DataSource`, `resolveDataset` (internal to `itemClient.ts`), `_queryParams`, `buildAggregateBody` (all already present).
- Produces: `ItemClient.exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }>` — used by Task 10 (`ExplorerMenu`) and Task 12 (`DatasetEditPage`).

- [ ] **Step 1: Add the type declarations**

Edit `shell/src/api/types.ts`. In the `ItemClient` interface, right after the existing line:

```ts
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
```

add:

```ts
  exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }>;
```

And in `DataSourceState`, add two optional fields:

```ts
export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
  datasetId?: string;
  pkColumn?: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
};
```

- [ ] **Step 2: Write the failing test**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("exportDataSource posts the aggregate body and extracts the filename for a statistics source", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/collections/parcs/export", async ({ request }) => {
      posted = await request.json();
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("csv");
      return new HttpResponse("region,count\nNord,3\n", {
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="parcs-20260807-120000.csv"',
        },
      });
    }),
  );
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: { groupBy: "region", agg: "count" } };
  const { blob, filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("parcs-20260807-120000.csv");
  expect(await blob.text()).toBe("region,count\nNord,3\n");
  expect(posted).toEqual({ groupBy: "region", agg: "count" });
});

test("exportDataSource GETs the items-export route for a non-statistics source", async () => {
  server.use(
    http.get("https://core.test/collections/parcs/export/items", ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("geojson");
      return new HttpResponse('{"type":"FeatureCollection","features":[]}', {
        headers: { "Content-Type": "application/geo+json", "Content-Disposition": 'attachment; filename="parcs.geojson"' },
      });
    }),
  );
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("parcs.geojson");
});

test("exportDataSource dispatches to the arcgis export route for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds1", () =>
      HttpResponse.json({ config: { dataset: { source: "arcgis", arcgisItemId: "ext1", columns: {} } } }),
    ),
    http.post("https://core.test/datasets/ds1/arcgis/export", () =>
      new HttpResponse("a,b\n1,2\n", {
        headers: { "Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="x.csv"' },
      }),
    ),
  );
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "", datasetId: "ds1", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("x.csv");
});

test("exportDataSource falls back to a generic filename when Content-Disposition is missing", async () => {
  server.use(
    http.get("https://core.test/collections/parcs/export/items", () =>
      new HttpResponse("[]", { headers: { "Content-Type": "application/geo+json" } }),
    ),
  );
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("export");
});
```

Check the top of `shell/src/api/itemClient.test.ts` imports `HttpResponse`/`http` from `msw` and `server` from `../test/msw/server` (same as Step 1's existing tests) — add `import type { DataSource } from "./types";` if not already imported.

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `TypeError: makeClient(...).exportDataSource is not a function`

- [ ] **Step 4: Implement**

Edit `shell/src/api/itemClient.ts`. Add a module-level helper right after `requestFeatureWrite` (or near `request`):

```ts
async function requestBlob(
  coreUrl: string, getToken: () => string | undefined, method: string, path: string, body?: unknown,
): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${coreUrl}${path}`, {
    method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status} ${method} ${path}`);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match ? match[1] : "export";
  const blob = await res.blob();
  return { blob, filename };
}
```

Then, inside `createItemClient(...)`, add the method right after `queryDataSource` (which ends around line 820, before `getCollectionSchema`):

```ts
    async exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      const isArcgis = cachedDataset?.source === "arcgis" && Boolean(source.datasetId);
      if (source.type === "statistics") {
        const body = buildAggregateBody(source.query);
        const path = isArcgis
          ? `/datasets/${source.datasetId}/arcgis/export?format=${format}`
          : `/collections/${cachedDataset?.collectionId ?? source.layer}/export?format=${format}`;
        return requestBlob(coreUrl, getToken, "POST", path, body);
      }
      const resolved = source.datasetId ? { ...source, layer: cachedDataset?.collectionId ?? source.layer } : source;
      const qs = _queryParams(resolved.query);
      const suffix = qs ? `&${qs}` : "";
      const path = isArcgis
        ? `/datasets/${source.datasetId}/arcgis/export/items?format=${format}${suffix}`
        : `/collections/${resolved.layer}/export/items?format=${format}${suffix}`;
      return requestBlob(coreUrl, getToken, "GET", path);
    },
```

Check `_queryParams` is accessible at this point in the file (it's a module-level function used by `buildFeaturesUrl` at line ~166) — confirm with `grep -n "_queryParams" shell/src/api/itemClient.ts` and use its exact name.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Run the shell type check**

Run: `cd shell && npm run build`
Expected: no TypeScript errors (this exercises every other file implementing `ItemClient` — search for other implementations with `grep -rn "ItemClient {" shell/src --include=*.ts` and add a stub `exportDataSource` there too if any test double implements the full interface structurally rather than via `as unknown as ItemClient`)

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): SP-16a — ItemClient.exportDataSource() (dispatch collection/arcgis, agrégé/items)"
```

---

