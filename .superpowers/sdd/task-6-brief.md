### Task 6: Shell — types + `itemClient.ts` (dataset source branching)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `DatasetConfig` becomes a discriminated union (`source: "collection" | "arcgis"`). `CreateDatasetInput` new discriminated union type. `ItemClient.createDatasetItem(input: CreateDatasetInput)`, `ItemClient.listFeatureLayers(params?: {q?: string}): Promise<FeatureLayerSource[]>` (new), `featuresUrl`/`queryDataSource` transparently route arcgis-backed sources to `/datasets/{arcgisItemId}/arcgis/items|aggregate`. Consumed by Task 7 (hooks/NewItemButton) and Task 8 (DataContext).

- [ ] **Step 1: Write the failing shell tests**

Open `shell/src/api/itemClient.test.ts`, find `makeClient()` at the top (reuse it as-is), and add these tests near the existing `featuresUrl`/`queryDataSource` dataset tests (around line 412-446):

```ts
test("featuresUrl routes an arcgis-sourced dataset to /datasets/{arcgisItemId}/arcgis/items", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-1", () =>
      HttpResponse.json({
        id: "cfg-arc1", itemId: "ds-arcgis-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-9", columns: {} } },
      }),
    ),
  );
  const client = makeClient();
  await client.getDatasetConfig("ds-arcgis-1"); // warms the cache
  expect(
    client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-arcgis-1", query: {} }),
  ).toBe("https://core.test/datasets/layer-9/arcgis/items");
});

test("queryDataSource fetches features from the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-2", () =>
      HttpResponse.json({
        id: "cfg-arc2", itemId: "ds-arcgis-2", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-10", columns: {} } },
      }),
    ),
    http.get("https://core.test/datasets/layer-10/arcgis/items", () =>
      HttpResponse.json({ type: "FeatureCollection", features: [{ id: 1, properties: { nom: "Bât" } }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-arcgis-2", query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Bât" }, geometry: undefined }]);
});

test("queryDataSource posts aggregate queries to the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-3", () =>
      HttpResponse.json({
        id: "cfg-arc3", itemId: "ds-arcgis-3", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-11", columns: {} } },
      }),
    ),
    http.post("https://core.test/datasets/layer-11/arcgis/aggregate", () =>
      HttpResponse.json({ categoryKey: "group", rows: [{ group: "Total", value: 4 }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "statistics", service: "core", layer: "", datasetId: "ds-arcgis-3", query: { agg: "count" },
  });
  expect(records).toEqual([{ id: "Total", properties: { group: "Total", value: 4 } }]);
});

test("getDatasetConfig returns an arcgis-shaped DatasetConfig for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-4", () =>
      HttpResponse.json({
        id: "cfg-arc4", itemId: "ds-arcgis-4", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-12", columns: {} } },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-arcgis-4");
  expect(config).toMatchObject({ source: "arcgis", arcgisItemId: "layer-12" });
});

test("createDatasetItem with source=arcgis posts an arcgis dataset payload", async () => {
  let postBody: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      postBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "cfg-9", kind: "dataset", itemId: "ds-9" });
    }),
  );
  const item = await makeClient().createDatasetItem({
    title: "Bâtiments (live)", owner: "alice", source: "arcgis", arcgisItemId: "layer-13",
  });
  expect(item.pk).toBe("ds-9");
  const config = postBody!.config as Record<string, unknown>;
  expect(config.dataset).toEqual({ source: "arcgis", arcgisItemId: "layer-13", columns: {} });
});

test("listFeatureLayers fetches /harvest/feature-layers", async () => {
  server.use(
    http.get("https://core.test/harvest/feature-layers", () =>
      HttpResponse.json({ layers: [{ id: "layer-1", title: "Bâtiments" }] }),
    ),
  );
  const layers = await makeClient().listFeatureLayers();
  expect(layers).toEqual([{ id: "layer-1", title: "Bâtiments" }]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `DatasetConfig`/`createDatasetItem` don't accept `source: "arcgis"` yet, `listFeatureLayers` doesn't exist, `featuresUrl`/`queryDataSource` don't branch.

- [ ] **Step 3: Update `shell/src/api/types.ts`**

Replace:

```ts
export type DatasetConfig = {
  source: "collection";
  collectionId: string;
  columns: Record<string, DatasetColumnMeta>;
  timeField?: string | null;
  reactsToExtent?: boolean;
};
```

with:

```ts
export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
    };

export type FeatureLayerSource = { id: string; title: string };

export type CreateDatasetInput =
  | { title: string; owner: string; source: "collection"; collectionId: string }
  | { title: string; owner: string; source: "arcgis"; arcgisItemId: string };
```

In the `ItemClient` interface, replace:

```ts
  createDatasetItem(input: { title: string; owner: string; collectionId: string }): Promise<Item>;
```

with:

```ts
  createDatasetItem(input: CreateDatasetInput): Promise<Item>;
  listFeatureLayers(params?: { q?: string }): Promise<FeatureLayerSource[]>;
```

- [ ] **Step 4: Update `shell/src/api/itemClient.ts`**

Replace the `ResolvedDataset` type and `resolveDataset` function:

```ts
  type ResolvedDataset = {
    source: "collection"; collectionId: string; columns: Record<string, DatasetColumnMeta>;
    timeField: string | null; reactsToExtent: boolean;
  };
```

with:

```ts
  type ResolvedDataset = {
    source: "collection" | "arcgis";
    collectionId: string | null;
    arcgisItemId: string | null;
    columns: Record<string, DatasetColumnMeta>;
    timeField: string | null;
    reactsToExtent: boolean;
  };
```

Replace the body of `resolveDataset`:

```ts
  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: {
        dataset?: {
          source: "collection" | "arcgis";
          collectionId?: string | null; arcgisItemId?: string | null;
          columns?: Record<string, DatasetColumnMeta>;
          timeField?: string | null; reactsToExtent?: boolean;
        } | null;
      };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      source: dataset.source,
      collectionId: dataset.collectionId ?? null,
      arcgisItemId: dataset.arcgisItemId ?? null,
      columns: dataset.columns ?? {}, timeField: dataset.timeField ?? null,
      reactsToExtent: dataset.reactsToExtent ?? false,
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

Replace `buildFeaturesUrl` (module-level, above `createItemClient`) with a shared query-string helper plus two URL builders:

```ts
function _queryParams(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query).sort(([a], [b]) => a.localeCompare(b))) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      params.set(k, String(v));
    }
  }
  return params.toString();
}

function buildFeaturesUrl(coreUrl: string, source: DataSource): string {
  const base = `${coreUrl}/collections/${source.layer}/items`;
  const qs = _queryParams(source.query);
  return qs ? `${base}?${qs}` : base;
}

function buildArcgisItemsUrl(coreUrl: string, arcgisItemId: string, query: Record<string, unknown>): string {
  const base = `${coreUrl}/datasets/${arcgisItemId}/arcgis/items`;
  const qs = _queryParams(query);
  return qs ? `${base}?${qs}` : base;
}
```

Inside `createItemClient`, add a shared feature-fetch helper next to `resolveDataset` (needs `getToken` from the enclosing closure):

```ts
  async function _fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    const token = getToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error(`Request failed: ${res.status} features`);
    const data = (await res.json()) as {
      features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
    };
    return (data.features ?? []).map((f, i) => ({ id: f.id ?? i, properties: f.properties ?? {}, geometry: f.geometry }));
  }
```

Replace `featuresUrl` in the returned object:

```ts
    featuresUrl(source: DataSource): string {
      if (source.datasetId) {
        const cached = datasetCache.get(source.datasetId);
        if (cached?.source === "arcgis" && cached.arcgisItemId) {
          return buildArcgisItemsUrl(coreUrl, cached.arcgisItemId, source.query);
        }
        return buildFeaturesUrl(coreUrl, { ...source, layer: cached?.collectionId ?? source.layer });
      }
      return buildFeaturesUrl(coreUrl, source);
    },
```

Replace `queryDataSource`:

```ts
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      if (cachedDataset?.source === "arcgis" && cachedDataset.arcgisItemId) {
        if (source.type === "statistics") {
          const body = buildAggregateBody(source.query);
          const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
            "POST", `/datasets/${cachedDataset.arcgisItemId}/arcgis/aggregate`, body,
          );
          return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
        }
        return _fetchGeoJsonFeatures(buildArcgisItemsUrl(coreUrl, cachedDataset.arcgisItemId, source.query));
      }
      const resolved = source.datasetId
        ? { ...source, layer: cachedDataset?.collectionId ?? source.layer }
        : source;
      if (resolved.type === "static") {
        return (resolved.query.records as DataRecord[] | undefined) ?? [];
      }
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${resolved.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
      }
      return _fetchGeoJsonFeatures(buildFeaturesUrl(coreUrl, resolved));
    },
```

Replace `createDatasetItem`:

```ts
    async createDatasetItem(input: CreateDatasetInput): Promise<Item> {
      const dataset: DatasetConfig =
        input.source === "arcgis"
          ? { source: "arcgis", arcgisItemId: input.arcgisItemId, columns: {} }
          : { source: "collection", collectionId: input.collectionId, columns: {} };
      const config = { version: 1, kind: "dataset", dataset };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createDatasetItem: core returned no itemId");
      datasetCache.set(String(data.itemId), {
        source: dataset.source,
        collectionId: dataset.source === "collection" ? dataset.collectionId : null,
        arcgisItemId: dataset.source === "arcgis" ? dataset.arcgisItemId : null,
        columns: {}, timeField: null, reactsToExtent: false,
      });
      return {
        pk: String(data.itemId), resourceType: "dataset", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },
```

Replace `getDatasetConfig`/`saveDatasetConfig`:

```ts
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      if (resolved.source === "arcgis" && resolved.arcgisItemId) {
        return {
          source: "arcgis", arcgisItemId: resolved.arcgisItemId, columns: resolved.columns,
          timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
        };
      }
      return {
        source: "collection", collectionId: resolved.collectionId ?? "", columns: resolved.columns,
        timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
      };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns, timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
      });
    },
```

Add `listFeatureLayers` near `listLayerSources`/`fetchExternalRasterSources`:

```ts
    async listFeatureLayers(params: { q?: string } = {}): Promise<FeatureLayerSource[]> {
      const token = getToken();
      const query = params.q ? `?q=${encodeURIComponent(params.q)}` : "";
      const res = await fetch(`${coreUrl}/harvest/feature-layers${query}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /harvest/feature-layers`);
      const data = (await res.json()) as { layers?: FeatureLayerSource[] };
      return data.layers ?? [];
    },
```

Update the import line at the top of the file to add `CreateDatasetInput` and `FeatureLayerSource` to the destructured type import from `"./types"`.

- [ ] **Step 5: Run to verify tests pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: all tests PASS, including the pre-existing collection-dataset ones (unaffected — same behavior, just routed through the now-shared `_queryParams`/`_fetchGeoJsonFeatures` helpers).

- [ ] **Step 6: Typecheck and run the full unit suite**

Run: `cd shell && npm run build && npx vitest run`
Expected: `tsc --noEmit` clean, full Vitest suite green (398+ tests, some new).

- [ ] **Step 7: Commit**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient routes arcgis-sourced datasets to the live proxy (SP-14k)"
```

---

