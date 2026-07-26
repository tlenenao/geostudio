# SP-14d — Menu « explorer » & panneau « voir les entités » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a « ⋮ explorer » menu to the 5 data-bound widgets (chart, table, list, map, indicator) that opens a read-only side drawer showing the raw entities (table + map) currently matching the app's analytics context (time range × extent × cross-filter).

**Architecture:** Two new React contexts/components in `shell/src/builder/` (`ExplorerContext` for open/close state and gating, `ExplorerDrawer` for the panel itself) plus a shared `ExplorerMenu` button posed into 5 existing widget files. The drawer builds a synthetic `DataSource` (id `"__explorer__"`, never a real widget id) and runs it through the exact same `derivePatch` used by every other widget, so the cross-filter always applies — even when the drawer is opened from the widget that itself set that cross-filter.

**Tech Stack:** React 18, TypeScript, `@tanstack/react-query`, Vitest + Testing Library, Playwright.

## Global Constraints

- No `core` changes anywhere in this plan — `limit`/`offset` and `__gte`/`__lte`/`__in` already exist server-side.
- The menu/drawer render only when `mode !== "edit" && config.interactions === "auto"` — identical gate to `AnalyticsContextIndicator` (SP-14c). An app with `interactions: "manual"` or the builder's edit canvas must never show the `⋮` button.
- Exactly 5 eligible widget types carry the menu: `chart`, `table`, `list`, `map`, `indicator`. Filters (`selectFilter`, `sliderFilter`, `dateRangeFilter`) never do.
- The drawer never writes to `AnalyticsContextState` — no `setCrossFilter`, `setExtent`, or `setTimeRange` call anywhere in `ExplorerDrawer.tsx`. Row selection only calls the drawer's own map's `highlight()`.
- Every interactive element gets an explicit `aria-label` (repo-wide convention, cf. SP-14c ledger).
- All user-facing copy is French.
- The 18+ existing Playwright specs must stay green — this plan is purely additive.
- Client-side cap of 200 rows (`query: { limit: 200 }` on the synthetic source) and client-side pagination at 20 rows/page in the drawer table.

---

## Task 1: `ExplorerContext` — open/close state and gating

**Files:**
- Create: `shell/src/builder/ExplorerContext.tsx`
- Test: `shell/src/builder/ExplorerContext.test.tsx`

**Interfaces:**
- Produces (consumed by every later task):
  - `type ExplorerTarget = { datasetId: string; dataSourceId: string } | null`
  - `function ExplorerProvider({ enabled, children }: { enabled?: boolean; children: ReactNode })`
  - `function useExplorerTarget(): ExplorerTarget`
  - `function useExplorerEnabled(): boolean`
  - `function useOpenExplorer(): (target: { datasetId: string; dataSourceId: string }) => void`
  - `function useCloseExplorer(): () => void`

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/ExplorerContext.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { ExplorerProvider, useCloseExplorer, useExplorerEnabled, useExplorerTarget, useOpenExplorer } from "./ExplorerContext";

function Probe() {
  const target = useExplorerTarget();
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const close = useCloseExplorer();
  return (
    <div>
      <p>enabled:{String(enabled)}</p>
      <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>
      <button onClick={() => open({ datasetId: "ds1", dataSourceId: "src1" })}>open</button>
      <button onClick={() => open({ datasetId: "ds2", dataSourceId: "src2" })}>open-other</button>
      <button onClick={close}>close</button>
    </div>
  );
}

test("openExplorer is a silent no-op when the provider is disabled", async () => {
  render(<ExplorerProvider enabled={false}><Probe /></ExplorerProvider>);
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("openExplorer sets the target when enabled", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  expect(screen.getByText("enabled:true")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("opening a second target while one is open replaces it (last one wins)", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("open-other"));
  expect(screen.getByText("target:ds2/src2")).toBeInTheDocument();
});

test("closeExplorer clears the target", async () => {
  render(<ExplorerProvider enabled><Probe /></ExplorerProvider>);
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(screen.getByText("close"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});

test("hooks work with no provider mounted at all (default disabled, no-op)", async () => {
  render(<Probe />);
  expect(screen.getByText("enabled:false")).toBeInTheDocument();
  await userEvent.click(screen.getByText("open"));
  expect(screen.getByText("target:none")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/ExplorerContext.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerContext"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/ExplorerContext.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type ExplorerTarget = { datasetId: string; dataSourceId: string } | null;

type OpenExplorer = (target: { datasetId: string; dataSourceId: string }) => void;
type CloseExplorer = () => void;

const ExplorerTargetContext = createContext<ExplorerTarget>(null);
const ExplorerEnabledContext = createContext<boolean>(false);
const ExplorerSettersContext = createContext<{ open: OpenExplorer; close: CloseExplorer }>({
  open: () => {}, close: () => {},
});

export function ExplorerProvider({
  enabled = false, children,
}: {
  enabled?: boolean;
  children: ReactNode;
}) {
  const [target, setTarget] = useState<ExplorerTarget>(null);

  const open = useCallback<OpenExplorer>((next) => {
    if (!enabled) return;
    setTarget(next);
  }, [enabled]);

  const close = useCallback<CloseExplorer>(() => {
    setTarget(null);
  }, []);

  const setters = useMemo(() => ({ open, close }), [open, close]);

  return (
    <ExplorerEnabledContext.Provider value={enabled}>
      <ExplorerSettersContext.Provider value={setters}>
        <ExplorerTargetContext.Provider value={target}>{children}</ExplorerTargetContext.Provider>
      </ExplorerSettersContext.Provider>
    </ExplorerEnabledContext.Provider>
  );
}

export function useExplorerTarget(): ExplorerTarget {
  return useContext(ExplorerTargetContext);
}
export function useExplorerEnabled(): boolean {
  return useContext(ExplorerEnabledContext);
}
export function useOpenExplorer(): OpenExplorer {
  return useContext(ExplorerSettersContext).open;
}
export function useCloseExplorer(): CloseExplorer {
  return useContext(ExplorerSettersContext).close;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/ExplorerContext.test.tsx`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/ExplorerContext.tsx shell/src/builder/ExplorerContext.test.tsx
git commit -m "feat(shell): ExplorerContext — open/close state for the analytics drill panel (SP-14d)"
```

---

## Task 2: `ExplorerMenu` — the shared `⋮` button

**Files:**
- Create: `shell/src/builder/widgets/ExplorerMenu.tsx`
- Test: `shell/src/builder/widgets/ExplorerMenu.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `useExplorerEnabled()`, `useOpenExplorer()`, `useExplorerTarget()` from `../ExplorerContext`.
- Produces (consumed by Task 3): `function ExplorerMenu({ datasetId, dataSourceId }: { datasetId: string | undefined; dataSourceId: string })`. Renders `null` unless `useExplorerEnabled()` is true and `datasetId` is truthy. Renders a button `aria-label="Explorer"` that toggles a one-item menu; the item `aria-label="Voir les entités"` calls `useOpenExplorer()({ datasetId, dataSourceId })` and closes the menu.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/widgets/ExplorerMenu.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { ExplorerMenu } from "./ExplorerMenu";
import { ExplorerProvider, useExplorerTarget } from "../ExplorerContext";

function TargetProbe() {
  const target = useExplorerTarget();
  return <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>;
}

test("renders nothing when the explorer is disabled", () => {
  render(
    <ExplorerProvider enabled={false}>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("renders nothing when there is no datasetId", () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId={undefined} dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("clicking the button then the menu item opens the explorer with the right target", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
      <TargetProbe />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("the menu closes again after selecting the item", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerMenu"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/widgets/ExplorerMenu.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";

export function ExplorerMenu({
  datasetId, dataSourceId,
}: {
  datasetId: string | undefined;
  dataSourceId: string;
}) {
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!enabled || !datasetId) return null;

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label="Explorer"
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        onClick={() => setMenuOpen((v) => !v)}
      >
        ⋮
      </button>
      {menuOpen && (
        <div className="absolute right-0 top-full mt-1 whitespace-nowrap rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-sm">
          <button
            type="button"
            aria-label="Voir les entités"
            className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
            onClick={() => {
              setMenuOpen(false);
              open({ datasetId, dataSourceId });
            }}
          >
            Voir les entités
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/ExplorerMenu.tsx shell/src/builder/widgets/ExplorerMenu.test.tsx
git commit -m "feat(shell): ExplorerMenu — shared ⋮ button, one item Voir les entités (SP-14d)"
```

---

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

## Task 4: `ExplorerDrawer` — the drill panel (table + map)

**Files:**
- Create: `shell/src/builder/ExplorerDrawer.tsx`
- Test: `shell/src/builder/ExplorerDrawer.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `useExplorerTarget()`, `useCloseExplorer()` from `./ExplorerContext`.
- Consumes (existing code): `useAnalyticsContext()` from `./AnalyticsContext`; `derivePatch(source, ctx, datasets)` from `../lib/analyticsPatch`; `useItemClient()` from `../api/ItemClientProvider`; `MapView`/`MapViewHandle` from `../map/MapView`; types `DataRecord`, `DataSource`, `MapConfig` from `../api/types`.
- Produces (consumed by Task 5): `function ExplorerDrawer(): ReactNode` — a self-contained component with no props, reads everything from context. Renders `null` when `useExplorerTarget()` is `null`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/ExplorerDrawer.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useImperativeHandle } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ExplorerDrawer } from "./ExplorerDrawer";
import { ExplorerProvider, useOpenExplorer } from "./ExplorerContext";
import { AnalyticsContextProvider, useSetCrossFilter } from "./AnalyticsContext";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { DatasetConfig, DataRecord, ItemClient } from "../api/types";

const highlightSpy = vi.fn();

vi.mock("../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config }: { config: { layers: { url?: string }[] } },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: vi.fn(), highlight: highlightSpy }));
      return <div data-testid="mapview" data-url={config.layers[0]?.url ?? ""} />;
    },
  ),
}));

function Opener({ datasetId, dataSourceId }: { datasetId: string; dataSourceId: string }) {
  const open = useOpenExplorer();
  return <button onClick={() => open({ datasetId, dataSourceId })}>open</button>;
}

function CrossFilterSetter() {
  const setCrossFilter = useSetCrossFilter();
  // originSourceId "src1" matches the dataSourceId used by <Opener> below on
  // purpose — proves the drawer stays filtered even "from" its own origin,
  // since its synthetic query source id is always "__explorer__", never a
  // real widget id (design §4).
  return <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>;
}

function renderDrawer(opts: { queryDataSource?: ReturnType<typeof vi.fn> } = {}) {
  const dataset: DatasetConfig = { source: "collection", collectionId: "col-1", columns: { nom: { label: "Nom" } } };
  const getDatasetConfig = vi.fn().mockResolvedValue(dataset);
  const queryDataSource = opts.queryDataSource ?? vi.fn().mockResolvedValue([]);
  const featuresUrl = vi.fn().mockReturnValue("https://core.test/collections/col-1/items?region=Nord");
  const client = { getDatasetConfig, queryDataSource, featuresUrl } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <ExplorerProvider enabled>
            <Opener datasetId="ds1" dataSourceId="src1" />
            <CrossFilterSetter />
            <ExplorerDrawer />
          </ExplorerProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { queryDataSource, featuresUrl };
}

beforeEach(() => { highlightSpy.mockClear(); });

test("renders nothing when no target is open", () => {
  renderDrawer();
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("opening a target queries the raw dataset features with the analytics context applied, even from its own origin widget", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
  ]);
  renderDrawer({ queryDataSource });
  await userEvent.click(screen.getByText("set-cf"));
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc A");
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    id: "__explorer__",
    datasetId: "ds1",
    query: expect.objectContaining({ limit: 200, region: "Nord" }),
  }));
});

test("table column headers use the dataset's business labels when available", async () => {
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "Parc A" } }]) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText("Nom")).toBeInTheDocument();
});

test("shows the 200-row cap message when the limit is reached", async () => {
  const records: DataRecord[] = Array.from({ length: 200 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText(/200 premières affichées/)).toBeInTheDocument();
});

test("paginates 20 rows at a time", async () => {
  const records: DataRecord[] = Array.from({ length: 25 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc 0");
  expect(screen.queryByText("Parc 20")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(await screen.findByText("Parc 20")).toBeInTheDocument();
  expect(screen.queryByText("Parc 0")).not.toBeInTheDocument();
});

test("clicking a row highlights it on the drawer's own map without touching the analytics context", async () => {
  const record = { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } };
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([record]) });
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByText("Parc A"));
  expect(highlightSpy).toHaveBeenCalledWith(record.geometry);
});

test("closing via the close button clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByRole("button", { name: "Fermer le panneau" }));
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("closing via Escape clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await screen.findByRole("button", { name: "Fermer le panneau" });
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerDrawer"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/ExplorerDrawer.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCloseExplorer, useExplorerTarget } from "./ExplorerContext";
import { useAnalyticsContext } from "./AnalyticsContext";
import { useItemClient } from "../api/ItemClientProvider";
import { derivePatch } from "../lib/analyticsPatch";
import type { DataRecord, DataSource, MapConfig } from "../api/types";
import type { MapViewHandle } from "../map/MapView";

const MapView = lazy(() => import("../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";
const EXPLORER_LIMIT = 200;
const PAGE_SIZE = 20;

function columnsOf(records: DataRecord[]): string[] {
  return records[0] ? Object.keys(records[0].properties) : [];
}

export function ExplorerDrawer() {
  const target = useExplorerTarget();
  const close = useCloseExplorer();
  const analyticsCtx = useAnalyticsContext();
  const client = useItemClient();
  const mapHandle = useRef<MapViewHandle>(null);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  useEffect(() => {
    setPage(0);
    setSelectedId(null);
  }, [target?.datasetId]);

  useEffect(() => {
    if (!target) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [target, close]);

  const datasetQuery = useQuery({
    queryKey: ["dataset", target?.datasetId],
    queryFn: () => client.getDatasetConfig(target!.datasetId),
    enabled: Boolean(target),
  });
  const dataset = datasetQuery.data;

  const source: DataSource | null = target
    ? { id: "__explorer__", type: "features", service: "core", layer: "", datasetId: target.datasetId, query: { limit: EXPLORER_LIMIT } }
    : null;
  const patch = source && dataset ? derivePatch(source, analyticsCtx, { [target!.datasetId]: dataset }) : {};
  const merged: DataSource | null = source ? { ...source, query: { ...source.query, ...patch } } : null;

  const recordsQuery = useQuery({
    queryKey: ["datasource-explorer", target?.datasetId, merged?.query],
    queryFn: () => client.queryDataSource(merged!),
    enabled: Boolean(merged && dataset),
  });

  if (!target) return null;

  const records = recordsQuery.data ?? [];
  const columns = columnsOf(records);
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const shown = records.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  const mapConfig: MapConfig = {
    basemap: { style: DEFAULT_STYLE },
    view: { center: [2.4, 46.6], zoom: 5 },
    layers: merged ? [{ id: "explorer", title: "Entités", visible: true, kind: "feature", url: client.featuresUrl(merged) }] : [],
  };

  function selectRecord(r: DataRecord) {
    setSelectedId(r.id);
    mapHandle.current?.highlight(r.geometry ?? null);
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-lg">
      <div className="flex items-center justify-between border-b border-[var(--gs-color-border)] p-2">
        <h2 className="text-sm font-medium text-[var(--gs-color-text)]">
          Entités — {dataset?.collectionId ?? target.datasetId}
        </h2>
        <button type="button" aria-label="Fermer le panneau" className="text-lg text-[var(--gs-color-muted)]" onClick={close}>
          ×
        </button>
      </div>
      <div className="h-48 shrink-0">
        <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
          <MapView ref={mapHandle} config={mapConfig} />
        </Suspense>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto p-2 text-xs">
        {recordsQuery.isLoading && <p className="text-[var(--gs-color-muted)]">Chargement…</p>}
        {recordsQuery.isError && <p className="text-red-600">Erreur de données</p>}
        {!recordsQuery.isLoading && !recordsQuery.isError && records.length === 0 && (
          <p className="text-[var(--gs-color-muted)]">Aucune entité</p>
        )}
        {records.length >= EXPLORER_LIMIT && (
          <p className="mb-2 text-[var(--gs-color-muted)]">
            Affinez le contexte (période, emprise, filtre) pour voir l'ensemble des entités — {EXPLORER_LIMIT} premières affichées.
          </p>
        )}
        {shown.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b border-[var(--gs-color-border)] p-1 font-medium">
                    {dataset?.columns[c]?.label ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className={`cursor-pointer hover:bg-[var(--gs-color-surface)] ${selectedId === r.id ? "bg-[var(--gs-color-surface)]" : ""}`}
                  onClick={() => selectRecord(r)}
                >
                  {columns.map((c) => (
                    <td key={c} className="border-b border-[var(--gs-color-border)] p-1">
                      {String(r.properties[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pageCount > 1 && (
          <div className="mt-auto flex items-center justify-between pt-2 text-[10px] text-[var(--gs-color-muted)]">
            <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
            <span>Page {current + 1} / {pageCount}</span>
            <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/ExplorerDrawer.test.tsx`
Expected: PASS (8/8).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/ExplorerDrawer.tsx shell/src/builder/ExplorerDrawer.test.tsx
git commit -m "feat(shell): ExplorerDrawer — table+map drill panel for the active analytics context (SP-14d)"
```

---

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

## Task 6: E2E — explorer menu and drill panel

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts` (append new scenarios; reuses the existing `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` helpers already defined in the file, cf. SP-14b/14c)

**Interfaces:**
- Consumes: the running app built by Tasks 1-5 (`⋮ Explorer` button, `Voir les entités` menu item, `Fermer le panneau` close button) through the real UI — no direct import of shell source.

- [ ] **Step 1: Write the failing E2E tests**

Append to `shell/e2e/analytics-context.spec.ts`, after the last existing `test(...)` block, before the file's closing:

```ts
// -------------------------------------------------------------------------
// Scénario 3 (SP-14d) — menu « explorer » : « Voir les entités » montre les
// lignes filtrées par le cross-filter courant, que le panneau soit ouvert
// depuis un autre widget ou depuis le widget qui a lui-même posé le filtre.
// -------------------------------------------------------------------------
test("voir les entités shows cross-filtered rows, even opened from the widget that set the filter", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }, { name: "valeur", type: "number" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    const cat = new URL(route.request().url()).searchParams.get("categorie");
    const all = [
      { id: 1, properties: { categorie: "Nord", valeur: 100 } },
      { id: 2, properties: { categorie: "Sud", valeur: 100 } },
    ];
    const features = cat ? all.filter((f) => f.properties.categorie === cat) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Explorer");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");
  const nordBar = { x: box.width * 0.3, y: box.height * 0.42 };
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: nordBar });
  await filteredReq;

  // Ouvrir « Voir les entités » depuis la Table (widget différent de l'origine
  // du clic) — le graphique est ajouté en premier, donc son bouton Explorer
  // est `.first()`, celui de la table `.last()`.
  await page.getByRole("button", { name: "Explorer" }).last().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
  await page.getByRole("button", { name: "Fermer le panneau" }).click();
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();

  // Ouvrir « Voir les entités » depuis le Graphique lui-même (l'origine du
  // clic) — reste filtré, contrairement au graphique qui s'affiche lui-même
  // sans filtre (design §4 : la requête synthétique du tiroir n'a jamais
  // l'id d'un widget réel).
  await page.getByRole("button", { name: "Explorer" }).first().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();

  // Fermer via Échap (plutôt que la croix, déjà couvert plus haut) — l'app
  // sous-jacente et son cross-filter restent inchangés.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 4 (SP-14d) — non-régression : une app `interactions: "manual"`
// n'affiche jamais le bouton « explorer », quel que soit le widget.
// -------------------------------------------------------------------------
test("the explorer menu never appears when interactions is manual", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({ json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "categorie", type: "string" }] } });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [{ id: 1, properties: { categorie: "Nord" } }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Manuel");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Interactions automatiques (cross-filter)").uncheck();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Explorer" })).toHaveCount(0);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts`
Expected: the 2 new scenarios FAIL against a `dev` build that predates Task 1-5 (no `⋮` button exists yet). If run *after* Tasks 1-5 are already merged (normal execution order of this plan), this step instead confirms they PASS — in that case treat Step 2 as already satisfied and proceed straight to Step 4's full run.

- [ ] **Step 3: Fix up selectors if needed**

Tasks 1-5 already implement everything these scenarios exercise. If a selector doesn't match (e.g. accessible name differs, or `.first()`/`.last()` ordering doesn't match actual DOM order), adjust the locator in the test — the underlying feature code does not change for this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts`
Expected: PASS, all scenarios in the file (previous SP-14b/14c ones + the 2 new SP-14d ones).

Run: `cd shell && npm run e2e`
Expected: full E2E suite green (previous 19 specs unaffected, `analytics-context.spec.ts` now covers SP-14d too).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(shell): E2E voir les entités — cross-filtered even from origin, non-regression manual (SP-14d)"
```

---

## Final Verification

- [ ] Run the full check used at the end of every SP-14 sub-part:

```bash
cd shell && npm run build && npm run test && npm run e2e
```

Expected: `tsc --noEmit` clean, `vite build` succeeds, full unit suite green (previous total + 23 new tests: 5 Task 1 + 4 Task 2 + 5 Task 3 + 8 Task 4 + 1 Task 5 — the exact count is whatever `npm run test`'s summary line reports), full E2E suite green (previous 19 specs + 2 new SP-14d scenarios in `analytics-context.spec.ts`).
