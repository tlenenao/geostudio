## Task 4: Shell — types (`CrossFilterLink`, `CrossFilterEntry.geometry`, `useSetCrossFilter`)

**Files:**
- Modify: `shell/src/api/types.ts:223-237` (`DatasetConfig`)
- Modify: `shell/src/builder/AnalyticsContext.tsx:4-5,19,62-72` (`CrossFilterEntry`, `SetCrossFilter`, `setCrossFilter`)
- Modify: `shell/src/api/itemClient.ts:197-231,584-599,632-655` (`ResolvedDataset`, `resolveDataset`, `createDatasetItem`, `getDatasetConfig`, `saveDatasetConfig`)
- Test: `shell/src/builder/AnalyticsContext.test.tsx` (append), `shell/src/api/itemClient.test.ts` (append)

**Interfaces:**
- Produces: `CrossFilterLink` (discriminated union, mirrors the core's `DatasetCrossFilterLink` field-for-field), `DatasetConfig.crossFilterLinks?: CrossFilterLink[]`, `CrossFilterEntry.geometry?: unknown`, `useSetCrossFilter()` returning a 5-arg setter `(datasetId, field, value, originSourceId, geometry?) => void`. Task 5 (`derivePatch`) and Task 6 (widget capture) both consume these exact names.

- [ ] **Step 1: Write the failing AnalyticsContext test**

Append to `shell/src/builder/AnalyticsContext.test.tsx`. First add a button to `Probe` that passes a geometry:

```typescript
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1", { type: "Point", coordinates: [1, 2] })}>set-cf-geom</button>
```

(insert it right after the existing `set-cf-range` button, inside the same `<div>`).

Then add the test, after `test("setCrossFilter accepts a {from,to} range value", ...)`:

```typescript
test("setCrossFilter stores an optional geometry alongside the entry", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf-geom"));
  expect(screen.getByText(/"geometry":\{"type":"Point","coordinates":\[1,2\]\}/)).toBeInTheDocument();
});

test("setCrossFilter without a geometry omits the field entirely (unchanged shape)", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.queryByText(/"geometry"/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: FAIL — `setCrossFilter` only accepts 4 arguments (TypeScript compile error) and never stores a `geometry` field.

- [ ] **Step 3: Implement in `AnalyticsContext.tsx`**

Change `CrossFilterEntry` (line 5):

```typescript
export type CrossFilterEntry = { field: string; value: CrossFilterValue; originSourceId: string; geometry?: unknown };
```

Change `SetCrossFilter` (line 19):

```typescript
type SetCrossFilter = (datasetId: string, field: string, value: CrossFilterValue, originSourceId: string, geometry?: unknown) => void;
```

Change `setCrossFilter` (currently at line 62-72):

```typescript
  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId, geometry) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId, geometry };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);
```

- [ ] **Step 4: Run the AnalyticsContext test to verify it passes**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: PASS (all tests in the file, including the 2 new ones — `JSON.stringify` naturally omits an `undefined` `geometry`, so the existing toggle/range tests are unaffected).

- [ ] **Step 5: Add `CrossFilterLink` to `types.ts`**

In `shell/src/api/types.ts`, extend `DatasetConfig` (currently lines 223-237):

```typescript
export type CrossFilterLink =
  | { targetDatasetId: string; mode: "attribute"; sourceField: string; targetField: string }
  | { targetDatasetId: string; mode: "spatial"; precision: "bbox" | "exact" };

export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
    };
```

- [ ] **Step 6: Write the failing itemClient round-trip test**

Append to `shell/src/api/itemClient.test.ts`, right after the existing `getDatasetConfig`/`saveDatasetConfig` tests (search the file for `"createDatasetItem"` or `"getDatasetConfig"` to find the neighboring tests and match their exact `server.use(...)`/`makeClient()` style):

```typescript
test("getDatasetConfig includes crossFilterLinks from the wire response", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds-1", kind: "dataset",
        config: {
          version: 1, kind: "dataset",
          dataset: {
            source: "collection", collectionId: "parcs", columns: {},
            crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "attribute", sourceField: "commune", targetField: "nom" }],
          },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "commune", targetField: "nom" },
  ]);
});

test("getDatasetConfig defaults crossFilterLinks to an empty array when absent from the wire", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds-1", kind: "dataset",
        config: { version: 1, kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([]);
});

test("saveDatasetConfig sends crossFilterLinks as-is and caches it for later reads", async () => {
  let posted: unknown;
  server.use(
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json(undefined, { status: 204 });
    }),
  );
  await makeClient().saveDatasetConfig("ds-1", {
    source: "collection", collectionId: "parcs", columns: {},
    crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" }],
  });
  expect((posted as { dataset: { crossFilterLinks: unknown } }).dataset.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" },
  ]);
});
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `getDatasetConfig` never reads/returns `crossFilterLinks` (TypeScript will also flag the `crossFilterLinks` property as unknown on the object literals used to call `saveDatasetConfig` once the type is defined, until Step 8 lands).

- [ ] **Step 8: Implement in `itemClient.ts`**

Extend `ResolvedDataset` (currently lines 197-204):

```typescript
  type ResolvedDataset = {
    source: "collection" | "arcgis";
    collectionId: string | null;
    arcgisItemId: string | null;
    columns: Record<string, DatasetColumnMeta>;
    timeField: string | null;
    reactsToExtent: boolean;
    crossFilterLinks: CrossFilterLink[];
  };
```

Extend `resolveDataset` (currently lines 207-231):

```typescript
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
          crossFilterLinks?: CrossFilterLink[];
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
      crossFilterLinks: dataset.crossFilterLinks ?? [],
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

Extend `createDatasetItem`'s `datasetCache.set(...)` call (currently lines 594-599):

```typescript
      datasetCache.set(String(data.itemId), {
        source: dataset.source,
        collectionId: dataset.source === "collection" ? dataset.collectionId : null,
        arcgisItemId: dataset.source === "arcgis" ? dataset.arcgisItemId : null,
        columns: {}, timeField: null, reactsToExtent: false, crossFilterLinks: [],
      });
```

Extend `getDatasetConfig` (currently lines 632-644):

```typescript
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      if (resolved.source === "arcgis" && resolved.arcgisItemId) {
        return {
          source: "arcgis", arcgisItemId: resolved.arcgisItemId, columns: resolved.columns,
          timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
          crossFilterLinks: resolved.crossFilterLinks,
        };
      }
      return {
        source: "collection", collectionId: resolved.collectionId ?? "", columns: resolved.columns,
        timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
        crossFilterLinks: resolved.crossFilterLinks,
      };
    },
```

Extend `saveDatasetConfig` (currently lines 646-655):

```typescript
    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns, timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
        crossFilterLinks: config.crossFilterLinks ?? [],
      });
    },
```

Add `CrossFilterLink` to the type import at the top of `itemClient.ts` (wherever `DatasetConfig`/`DatasetColumnMeta` are already imported from `./types`).

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests, including the 3 new ones).

- [ ] **Step 10: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions — every change is additive (new optional field, new optional callback parameter with a default of `undefined`).

- [ ] **Step 11: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/AnalyticsContext.tsx shell/src/api/itemClient.ts shell/src/builder/AnalyticsContext.test.tsx shell/src/api/itemClient.test.ts
git commit -m "feat(shell): CrossFilterLink type, cross-filter geometry, dataset round-trip (SP-14n)"
```

---

