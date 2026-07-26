## Task 5: Wire `ExplorerProvider`/`ExplorerDrawer` into `AppRenderer`

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx:1-15` (imports), `:172-200` (JSX)
- Modify (test fixture + new tests): `shell/src/builder/AppRenderer.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `ExplorerProvider` from `./ExplorerContext`.
- Consumes (from Task 4): `ExplorerDrawer` from `./ExplorerDrawer`.
- Produces: nothing new — this is the final wiring point, `AppRenderer` is the app's root renderer.

- [ ] **Step 1: Write the failing test**

In `shell/src/builder/AppRenderer.test.tsx`, extend the shared `stubClient` fixture (around line 26) so `DataContext`'s dataset/collection-schema resolution has something to call instead of throwing when a `dataSources` entry carries a `datasetId` — replace:

```ts
const stubClient = {
  queryDataSource: vi.fn().mockResolvedValue([]),
  featuresUrl: vi.fn().mockReturnValue(""),
} as unknown as ItemClient;
```

with:

```ts
const stubClient = {
  queryDataSource: vi.fn().mockResolvedValue([]),
  featuresUrl: vi.fn().mockReturnValue(""),
  getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "col1", columns: {} }),
  getCollectionSchema: vi.fn().mockResolvedValue({ collection: "col1", pk: "id", geometry: null, fields: [] }),
} as unknown as ItemClient;
```

Then append this test at the end of the file:

```tsx
test("shows the explorer menu on an eligible widget only when interactions is auto and not edit mode", async () => {
  const autoConfig: AppConfig = {
    ...config,
    interactions: "auto",
    dataSources: [{ id: "src1", type: "features", service: "core", layer: "col1", datasetId: "ds1", query: {} }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "ind1", widget: "indicator", x: 0, y: 0, w: 2, h: 2, props: { dataSourceId: "src1", label: "Total" } },
    ] },
  };
  const { rerender } = render(<AppRenderer config={autoConfig} mode="runtime" />, { wrapper: Wrapper });
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();

  rerender(<AppRenderer config={autoConfig} mode="edit" />);
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();

  rerender(<AppRenderer config={{ ...autoConfig, interactions: "manual" }} mode="runtime" />);
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL on the new test — `Unable to find a label with the text of: Explorer` (the `ExplorerMenu` inside the `indicator` widget never renders because `ExplorerProvider` isn't mounted yet, so `useExplorerEnabled()` defaults to `false`).

- [ ] **Step 3: Write minimal implementation**

In `shell/src/builder/AppRenderer.tsx`, add the two imports after the existing `AnalyticsContextIndicator` import (line 13):

```tsx
import { ExplorerProvider } from "./ExplorerContext";
import { ExplorerDrawer } from "./ExplorerDrawer";
```

Replace the JSX block (lines 172-200):

```tsx
      <div className="min-h-0 flex-1">
        <ActionBusProvider bus={bus}>
          <VariablesProvider variables={config.variables ?? []}>
            <ExplorerProvider enabled={mode !== "edit" && config.interactions === "auto"}>
              <AnalyticsContextProvider
                interactions={config.interactions}
                initialState={initialAnalyticsContext}
                onStateChange={onAnalyticsContextChange}
              >
                {mode !== "edit" && config.interactions === "auto" && <AnalyticsContextIndicator />}
                <ExplorerDrawer />
                <ActionConditionBridge bus={bus} />
                {(config.variables ?? []).map((v) => (
                  <VariableBusBridge key={v.id} variable={v} bus={bus} />
                ))}
                <DataProvider sources={config.dataSources}>
                  <GridCanvas
                    items={activeLayout.items}
                    breakpoint={bp}
                    editable={editable}
                    selectedId={selectedId}
                    onSelect={(id) => onSelect?.(id)}
                    onMoveItem={handleMove}
                    renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} />}
                  />
                </DataProvider>
              </AnalyticsContextProvider>
            </ExplorerProvider>
          </VariablesProvider>
        </ActionBusProvider>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS, including the new test.

Run: `cd shell && npm run test`
Expected: full unit suite green (previous total + 14 new from Tasks 1-5).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): mount ExplorerProvider/ExplorerDrawer in AppRenderer, gated like the context indicator (SP-14d)"
```

---

