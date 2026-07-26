## Task 3: Wire `ExplorerMenu` into the 5 eligible widgets

**Files:**
- Modify: `shell/src/builder/widgets/chart.tsx:1-6` (imports), `:112-116` (return)
- Modify: `shell/src/builder/widgets/data.tsx:1-9` (imports), `:60-72` (`list` return), `:190-233` (`table` return)
- Modify: `shell/src/builder/widgets/mapWidget.tsx:1-11` (imports), `:57-74` (return)
- Modify: `shell/src/builder/widgets/indicator.tsx:1-3` (imports), `:42-47` (return)
- Modify (tests): `shell/src/builder/widgets/chart.test.tsx`, `shell/src/builder/widgets/data.test.tsx`, `shell/src/builder/widgets/mapWidget.test.tsx`, `shell/src/builder/widgets/indicator.test.tsx`

**Interfaces:**
- Consumes (from Task 2): `ExplorerMenu` component, props `{ datasetId: string | undefined; dataSourceId: string }`.
- Consumes (from Task 1, in tests only): `ExplorerProvider` to enable the menu in the new assertions.
- Produces: nothing new consumed by later tasks — this task only wires an existing component into existing widgets.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/chart.test.tsx` (add the import alongside the existing ones, then the test at the end of the file):

```tsx
import { ExplorerProvider } from "../ExplorerContext";
```

```tsx
test("shows an explorer menu when the widget is bound to a dataset and interactions are auto", async () => {
  const Chart = getWidget("chart")!.Component;
  render(
    <ExplorerProvider enabled>
      <Chart
        props={{ chartType: "bar", categoryField: "region", dataSourceId: "src1" }}
        ctx={{ mode: "runtime", data: { ...wide, datasetId: "ds1" } } as WidgetContext}
      />
    </ExplorerProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
```

Append to `shell/src/builder/widgets/data.test.tsx`:

```tsx
import { ExplorerProvider } from "../ExplorerContext";
```

```tsx
test("list shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const List = getWidget("list")!.Component;
  const ctx = { mode: "runtime", data: state({ datasetId: "ds1", records: [{ id: 1, properties: { nom: "Parc A" } }] }) } as WidgetContext;
  render(<ExplorerProvider enabled><List props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>);
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("table shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ datasetId: "ds1", records: [{ id: 1, properties: { nom: "Parc A" } }] }) } as WidgetContext;
  render(<ExplorerProvider enabled><Table props={{ dataSourceId: "src1", columns: ["nom"] }} ctx={ctx} /></ExplorerProvider>);
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
```

Append to `shell/src/builder/widgets/mapWidget.test.tsx`:

```tsx
import { ExplorerProvider } from "../ExplorerContext";
```

```tsx
test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: { loading: false, error: false, records: [], datasetId: "ds1", url: "https://core/collections/geo/items" } } as unknown as WidgetContext;
  render(<ExplorerProvider enabled><Map props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>);
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
```

Append to `shell/src/builder/widgets/indicator.test.tsx`:

```tsx
import { ExplorerProvider } from "../ExplorerContext";
```

```tsx
test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ datasetId: "ds1", records: [{ id: 1, properties: { pop: 10 } }] }) } as WidgetContext;
  render(<ExplorerProvider enabled><Ind props={{ dataSourceId: "src1", label: "Total" }} ctx={ctx} /></ExplorerProvider>);
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/data.test.tsx src/builder/widgets/mapWidget.test.tsx src/builder/widgets/indicator.test.tsx`
Expected: the 4 new tests FAIL (`Unable to find a label with the text of: Explorer`), all pre-existing tests in these files still PASS.

- [ ] **Step 3: Write minimal implementation**

In `shell/src/builder/widgets/chart.tsx`, add the import after the existing `chartOption` import (line 6):

```tsx
import { ExplorerMenu } from "./ExplorerMenu";
```

Replace the `return` block (lines 112-116):

```tsx
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
            <EChart option={option} onClick={handleClick} />
          </Suspense>
        </div>
      );
```

In `shell/src/builder/widgets/data.tsx`, add the import after the `DataRecord` type import (line 9):

```tsx
import { ExplorerMenu } from "./ExplorerMenu";
```

Replace the `list` widget's `return` block (lines 60-72):

```tsx
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <ul className="flex flex-col gap-0.5 text-sm">
            {data.records.map((r) => (
              <li
                key={String(r.id)}
                className="cursor-pointer truncate border-b border-[var(--gs-color-border)] py-0.5 text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
                onClick={() => selectRecord(r)}
              >
                {String(r.properties[field] ?? r.id)}
              </li>
            ))}
          </ul>
        </div>
      );
```

Replace the `table` widget's opening wrapper `<div className="flex h-full flex-col text-xs">` (line 191) and add the menu right after it, so the block at lines 190-233 becomes:

```tsx
      return (
        <div className="relative flex h-full flex-col text-xs">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                {columns.map((c) => {
                  const key = columnKey(c);
                  return (
                    <th key={key} className="border-b border-[var(--gs-color-border)] p-1">
                      {isCalculatedColumn(c) ? (
                        <span className="font-medium">{columnLabel(c)}</span>
                      ) : (
                        <button type="button" className="flex items-center gap-1 font-medium" onClick={() => toggleSort(key)}>
                          {columnLabel(c)}{sortCol === key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className="cursor-pointer hover:bg-[var(--gs-color-surface)]"
                  onClick={() => selectRecord(r)}
                >
                  {columns.map((c) => <td key={columnKey(c)} className="border-b border-[var(--gs-color-border)] p-1">{cellValue(c, r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {pageCount > 1 && (
            <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-[var(--gs-color-muted)]">
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
              <span>Page {current + 1} / {pageCount}</span>
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
            </div>
          )}
        </div>
      );
```

In `shell/src/builder/widgets/mapWidget.tsx`, add the import after the `MapViewHandle` type import (line 8):

```tsx
import { ExplorerMenu } from "./ExplorerMenu";
```

Replace the `return` block (lines 57-74):

```tsx
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""));
              }}
            />
          </Suspense>
        </div>
      );
```

In `shell/src/builder/widgets/indicator.tsx`, add the import after the `DataSourceSelect` import (line 3):

```tsx
import { ExplorerMenu } from "./ExplorerMenu";
```

Replace the `return` block (lines 42-47):

```tsx
      return (
        <div className="relative flex h-full flex-col items-center justify-center">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
        </div>
      );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/data.test.tsx src/builder/widgets/mapWidget.test.tsx src/builder/widgets/indicator.test.tsx`
Expected: PASS, all tests including the 4 new ones.

Run: `cd shell && npm run test`
Expected: full suite green (no regression in any other widget/test file).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx \
        shell/src/builder/widgets/data.tsx shell/src/builder/widgets/data.test.tsx \
        shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx \
        shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx
git commit -m "feat(shell): wire the explorer menu into chart/table/list/map/indicator (SP-14d)"
```

---

