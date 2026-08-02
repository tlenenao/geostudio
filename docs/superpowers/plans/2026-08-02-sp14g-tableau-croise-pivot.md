# SP-14g — Tableau croisé / pivot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `pivot` widget to the GeoStudio shell builder that renders a 2D crosstab (rows × columns × one or more measures, with row/column totals and a grand total) from an existing `statistics` data source, and wires header clicks into the existing cross-filter mechanism.

**Architecture:** Zero backend changes. The widget consumes the `groupBy` multi-field + `measures` capability already shipped in SP-14f (`core/app/analytics/aggregate.py`, unmodified) via the existing `statistics` `DataSource` type (unmodified `DataSourcePanel.tsx`, unmodified `itemClient.ts`). A new pure function (`buildPivotGrid`) reshapes the tidy rows already returned by `/collections/{id}/aggregate` into a grid with cell/row-total/column-total/grand-total accessors; a new widget component (`pivot.tsx`) renders that grid as an HTML `<table>` and wires row/column header clicks to the existing `setCrossFilter`.

**Tech Stack:** React 18 + TypeScript (shell), Vitest + Testing Library (unit), Playwright (E2E). No core/Python changes in this plan.

## Global Constraints

- Zero changes to `core/`, `itemClient.ts`, or `DataSourcePanel.tsx` — the spec (`docs/superpowers/specs/2026-08-02-sp14g-tableau-croise-pivot-design.md`) requires this plan to be purely additive on the shell side.
- v1 is fixed to exactly 1 rows field + 1 columns field (no row hierarchy) — do not add support for more than 2 `encodings` fields.
- Cross-filter fires only from row/column **header** clicks, never from data cells or the Total row/column — the app's cross-filter model (`AnalyticsContext.tsx:5`, `CrossFilterEntry`) holds a single `{field, value}` pair per dataset and cannot represent a two-field cell filter.
- Missing row×column combinations render as `0` in every measure — do not special-case `avg`/`min`/`max` to show blank instead (documented simplification, spec §1).
- Row/column values sort with `localeCompare` (alphabetical) — no numeric-aware sort, no manual reordering.
- All UI strings are in French, matching the rest of the builder (`labelCls`/`inputCls` conventions from `chart.tsx`).
- Every new file starts with `// SPDX-License-Identifier: Apache-2.0`.
- Commits are conventional (`feat(shell): ... (SP-14g)`), small, one subject per commit.

---

## Task 1: `buildPivotGrid` — pure reshape function

**Files:**
- Create: `shell/src/builder/widgets/pivotTable.ts`
- Test: `shell/src/builder/widgets/pivotTable.test.ts`

**Interfaces:**
- Consumes: `DataRecord` from `shell/src/api/types.ts` (`{ id: string | number; properties: Record<string, unknown>; geometry?: unknown }`, already exists, unmodified).
- Produces (consumed by Task 2):
  ```ts
  export type PivotGrid = {
    rowValues: string[];
    colValues: string[];
    measures: string[];
    cell(row: string, col: string, measure: string): number;
    rowTotal(row: string, measure: string): number;
    colTotal(col: string, measure: string): number;
    grandTotal(measure: string): number;
  };
  export function buildPivotGrid(records: DataRecord[], rowsField: string, colsField: string): PivotGrid | null;
  ```

- [ ] **Step 1: Write the failing test file**

Create `shell/src/builder/widgets/pivotTable.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { buildPivotGrid } from "./pivotTable";
import type { DataRecord } from "../../api/types";

const oneMeasure: DataRecord[] = [
  { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10 } },
  { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 5 } },
  { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 3 } },
  // "Sud"/"Q2" is deliberately absent — exercises the missing-combination fill.
];

test("builds a grid with cells, row totals, column totals and a grand total", () => {
  const grid = buildPivotGrid(oneMeasure, "region", "quarter");
  expect(grid).not.toBeNull();
  expect(grid!.rowValues).toEqual(["Nord", "Sud"]);
  expect(grid!.colValues).toEqual(["Q1", "Q2"]);
  expect(grid!.measures).toEqual(["sum_amount"]);
  expect(grid!.cell("Nord", "Q1", "sum_amount")).toBe(10);
  expect(grid!.cell("Nord", "Q2", "sum_amount")).toBe(5);
  expect(grid!.cell("Sud", "Q1", "sum_amount")).toBe(3);
  expect(grid!.rowTotal("Nord", "sum_amount")).toBe(15);
  expect(grid!.rowTotal("Sud", "sum_amount")).toBe(3);
  expect(grid!.colTotal("Q1", "sum_amount")).toBe(13);
  expect(grid!.colTotal("Q2", "sum_amount")).toBe(5);
  expect(grid!.grandTotal("sum_amount")).toBe(18);
});

test("a missing row×column combination reads as 0 in the cell", () => {
  const grid = buildPivotGrid(oneMeasure, "region", "quarter")!;
  expect(grid.cell("Sud", "Q2", "sum_amount")).toBe(0);
});

test("supports multiple measures, preserving the first record's property order", () => {
  const records: DataRecord[] = [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10, avg_amount: 5 } },
    { id: "2", properties: { region: "Sud", quarter: "Q1", sum_amount: 4, avg_amount: 2 } },
  ];
  const grid = buildPivotGrid(records, "region", "quarter")!;
  expect(grid.measures).toEqual(["sum_amount", "avg_amount"]);
  expect(grid.cell("Nord", "Q1", "avg_amount")).toBe(5);
  expect(grid.rowTotal("Nord", "avg_amount")).toBe(5);
});

test("returns null when rowsField or colsField is empty", () => {
  expect(buildPivotGrid(oneMeasure, "", "quarter")).toBeNull();
  expect(buildPivotGrid(oneMeasure, "region", "")).toBeNull();
});

test("returns null when records do not carry the configured fields", () => {
  const records: DataRecord[] = [{ id: "1", properties: { other: 1 } }];
  expect(buildPivotGrid(records, "region", "quarter")).toBeNull();
});

test("returns null when no measure column remains after excluding rows/columns fields", () => {
  const records: DataRecord[] = [{ id: "1", properties: { region: "Nord", quarter: "Q1" } }];
  expect(buildPivotGrid(records, "region", "quarter")).toBeNull();
});

test("returns null for an empty records array", () => {
  expect(buildPivotGrid([], "region", "quarter")).toBeNull();
});

test("normalizes null/undefined/empty-string row values to the same placeholder label", () => {
  const records: DataRecord[] = [
    { id: "1", properties: { region: null, quarter: "Q1", sum_amount: 1 } },
    { id: "2", properties: { region: undefined, quarter: "Q1", sum_amount: 2 } },
  ];
  const grid = buildPivotGrid(records, "region", "quarter")!;
  expect(grid.rowValues).toEqual(["—"]);
  expect(grid.cell("—", "Q1", "sum_amount")).toBe(3);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npm run test -- pivotTable.test.ts`
Expected: FAIL — `Cannot find module './pivotTable'` (file does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `shell/src/builder/widgets/pivotTable.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { DataRecord } from "../../api/types";

export type PivotGrid = {
  rowValues: string[];
  colValues: string[];
  measures: string[];
  cell(row: string, col: string, measure: string): number;
  rowTotal(row: string, measure: string): number;
  colTotal(col: string, measure: string): number;
  grandTotal(measure: string): number;
};

const EMPTY_LABEL = "—";
const KEY_SEP = "::";

function normalizeLabel(value: unknown): string {
  if (value === null || value === undefined || value === "") return EMPTY_LABEL;
  return String(value);
}

function cellKey(row: string, col: string, measure: string): string {
  return `${row}${KEY_SEP}${col}${KEY_SEP}${measure}`;
}

// Reshapes the tidy rows already returned by a `groupBy: [rowsField,
// colsField]` + `measures` statistics DataSource (core, SP-14f, unchanged)
// into a 2D crosstab, entirely client-side — see SP-14g design §2-3 for why
// no core change is needed.
export function buildPivotGrid(records: DataRecord[], rowsField: string, colsField: string): PivotGrid | null {
  if (!rowsField || !colsField || records.length === 0) return null;
  const first = records[0].properties;
  if (!(rowsField in first) || !(colsField in first)) return null;
  const measures = Object.keys(first).filter((k) => k !== rowsField && k !== colsField);
  if (measures.length === 0) return null;

  const rowSet = new Set<string>();
  const colSet = new Set<string>();
  const values = new Map<string, number>();

  for (const record of records) {
    const rowVal = normalizeLabel(record.properties[rowsField]);
    const colVal = normalizeLabel(record.properties[colsField]);
    rowSet.add(rowVal);
    colSet.add(colVal);
    for (const measure of measures) {
      const raw = Number(record.properties[measure] ?? 0);
      values.set(cellKey(rowVal, colVal, measure), Number.isFinite(raw) ? raw : 0);
    }
  }

  const rowValues = [...rowSet].sort((a, b) => a.localeCompare(b));
  const colValues = [...colSet].sort((a, b) => a.localeCompare(b));

  function cell(row: string, col: string, measure: string): number {
    return values.get(cellKey(row, col, measure)) ?? 0;
  }
  function rowTotal(row: string, measure: string): number {
    return colValues.reduce((sum, col) => sum + cell(row, col, measure), 0);
  }
  function colTotal(col: string, measure: string): number {
    return rowValues.reduce((sum, row) => sum + cell(row, col, measure), 0);
  }
  function grandTotal(measure: string): number {
    return rowValues.reduce((sum, row) => sum + rowTotal(row, measure), 0);
  }

  return { rowValues, colValues, measures, cell, rowTotal, colTotal, grandTotal };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npm run test -- pivotTable.test.ts`
Expected: PASS — 8 tests green.

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/widgets/pivotTable.ts src/builder/widgets/pivotTable.test.ts
git commit -m "feat(shell): buildPivotGrid reshapes tidy multi-field groupBy rows into a crosstab (SP-14g)"
```

---

## Task 2: `pivot` widget — PropsPanel, Component, cross-filter, registration

**Files:**
- Create: `shell/src/builder/widgets/pivot.tsx`
- Create: `shell/src/builder/widgets/pivot.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`

**Interfaces:**
- Consumes: `buildPivotGrid`, `PivotGrid` from Task 1 (`./pivotTable`); `registerWidget`, `WidgetContext` from `../registry`; `DataSourceSelect` from `../DataSourceSelect`; `useSetCrossFilter` from `../AnalyticsContext`; `ExplorerMenu` from `./ExplorerMenu` (all pre-existing, unmodified — same imports `chart.tsx` already uses).
- Produces: registers widget type `"pivot"` in the global registry (consumed by the builder UI and by Task 3's E2E tests via the `"Pivot"` palette button — **not** `"Tableau croisé"`: that label starts with the substring `"Table"`, and Playwright's `getByRole` name matching is substring-based by default, so it would silently start matching every existing `page.getByRole("button", { name: "Table" })` call already in this file — a real regression, not just a style choice).

- [ ] **Step 1: Write the failing test file**

Create `shell/src/builder/widgets/pivot.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState =>
  ({ loading: false, error: false, records: [], ...over });

// Small fixture for behavioural tests (config message, cross-filter, explorer
// menu). Deliberately 2 columns, not 1: with a single column a row's total
// would equal its only cell (same rendered text, e.g. both "10") and the
// "never cross-filters from a data cell" test below needs to click a cell
// whose text is unambiguous.
const small = state({
  datasetId: "ds-1",
  records: [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10 } },
    { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 6 } },
    { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 3 } },
  ],
});

// Fixture with globally-distinct numbers, for rendering assertions where every
// cell/total/grand-total must resolve to a unique element via getByRole.
const distinct = state({
  datasetId: "ds-1",
  records: [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 100 } },
    { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 23 } },
    { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 7 } },
    { id: "4", properties: { region: "Sud", quarter: "Q2", sum_amount: 41 } },
  ],
});

test("registers with a 6x4 default size", () => {
  expect(getWidget("pivot")!.defaultSize).toEqual({ w: 6, h: 4 });
});

test("PropsPanel edits the rows and columns encodings", async () => {
  // DataSourceSelect (rendered by every widget's PropsPanel) calls
  // useItemClient() internally — it throws without an ItemClientProvider
  // ancestor, and useItems (react-query) needs a QueryClientProvider too.
  // Same wrapping as chart.test.tsx's "PropsPanel edits..." test.
  const onChange = vi.fn();
  const Panel = getWidget("pivot")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{}} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByLabelText("Champ lignes"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { rows: "r" } }));
  await userEvent.type(screen.getByLabelText("Champ colonnes"), "c");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { columns: "c" } }));
});

test("shows loading, error and empty states", () => {
  const Pivot = getWidget("pivot")!.Component;
  const { rerender } = render(<Pivot props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<Pivot props={{}} ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext} />);
  expect(screen.getByText(/erreur/i)).toBeInTheDocument();
  rerender(<Pivot props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("shows a configuration message when rows/columns encodings are not set", () => {
  const Pivot = getWidget("pivot")!.Component;
  render(<Pivot props={{}} ctx={{ mode: "runtime", data: small } as WidgetContext} />);
  expect(screen.getByText(/configurez les champs lignes et colonnes/i)).toBeInTheDocument();
});

test("renders row/column headers, cells and totals", () => {
  const Pivot = getWidget("pivot")!.Component;
  render(<Pivot props={{ encodings: { rows: "region", columns: "quarter" } }} ctx={{ mode: "runtime", data: distinct } as WidgetContext} />);
  expect(screen.getByRole("button", { name: "Nord" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Q1" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "100" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "23" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "123" })).toBeInTheDocument(); // row total Nord (100+23)
  expect(screen.getByRole("cell", { name: "107" })).toBeInTheDocument(); // col total Q1 (100+7)
  expect(screen.getByRole("cell", { name: "171" })).toBeInTheDocument(); // grand total
});

test("clicking a row header cross-filters on the rows field", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nord" }));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("clicking a column header cross-filters on the columns field", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Q1" }));
  expect(await screen.findByText("cf:quarter=Q1")).toBeInTheDocument();
});

test("never cross-filters from a data cell or the Total row/column", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("cell", { name: "10" }));
  // Both the Total column header and the Total row header render the text
  // "Total" — two matches on purpose, click both to prove neither filters.
  for (const totalCell of screen.getAllByText("Total")) {
    await userEvent.click(totalCell);
  }
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Pivot = getWidget("pivot")!.Component;
  render(
    <ExplorerProvider enabled>
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
    </ExplorerProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npm run test -- pivot.test.tsx`
Expected: FAIL — `getWidget("pivot")` returns `undefined` (`Cannot read properties of undefined (reading 'defaultSize')` on the first test), since neither `pivot.tsx` nor its registration in `index.tsx` exist yet.

- [ ] **Step 3: Write the widget implementation**

Create `shell/src/builder/widgets/pivot.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useSetCrossFilter } from "../AnalyticsContext";
import { buildPivotGrid } from "./pivotTable";
import { ExplorerMenu } from "./ExplorerMenu";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";
const thCls = "border-b border-[var(--gs-color-border)] p-1";

type PivotEncodings = { rows?: string; columns?: string };

export function registerPivotWidget(): void {
  registerWidget({
    type: "pivot",
    // Not "Tableau croisé": that label starts with "Table", and every E2E
    // scenario in this file locates the existing Table widget's palette
    // button via `getByRole("button", { name: "Table" })` — Playwright's
    // name matching is substring-based by default, so "Table" would start
    // matching this button too (strict-mode violation) across the whole
    // existing suite. "Pivot" collides with no existing widget label.
    label: "Pivot",
    defaultProps: { dataSourceId: "", encodings: { rows: "", columns: "" }, title: "" },
    defaultSize: { w: 6, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => {
      const encodings = (props.encodings as PivotEncodings | undefined) ?? {};
      const setEncodings = (patch: PivotEncodings) => onChange({ ...props, encodings: { ...encodings, ...patch } });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className={labelCls}>Champ lignes
            <input aria-label="Champ lignes" className={inputCls}
              value={String(encodings.rows ?? "")} onChange={(e) => setEncodings({ rows: e.target.value })} />
          </label>
          <label className={labelCls}>Champ colonnes
            <input aria-label="Champ colonnes" className={inputCls}
              value={String(encodings.columns ?? "")} onChange={(e) => setEncodings({ columns: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du tableau croisé" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => onChange({ ...props, title: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const setCrossFilter = useSetCrossFilter();
      const data = ctx.data;
      const encodings = (props.encodings as PivotEncodings | undefined) ?? {};
      const rowsField = String(encodings.rows ?? "");
      const colsField = String(encodings.columns ?? "");
      const dataSourceId = String(props.dataSourceId ?? "");

      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;

      const grid = buildPivotGrid(data.records, rowsField, colsField);
      if (!grid) return <p className="text-xs text-[var(--gs-color-muted)]">Configurez les champs lignes et colonnes</p>;

      function clickRow(rowValue: string) {
        if (data?.datasetId) setCrossFilter(data.datasetId, rowsField, rowValue, dataSourceId);
      }
      function clickCol(colValue: string) {
        if (data?.datasetId) setCrossFilter(data.datasetId, colsField, colValue, dataSourceId);
      }

      const showMeasureRow = grid.measures.length > 1;

      return (
        <div className="relative h-full overflow-auto text-xs">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={dataSourceId} />
          {props.title ? <p className="mb-1 font-medium">{String(props.title)}</p> : null}
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                <th className={thCls} />
                {grid.colValues.map((col) => (
                  <th key={col} colSpan={grid.measures.length} className={thCls}>
                    <button type="button" className="font-medium" onClick={() => clickCol(col)}>{col}</button>
                  </th>
                ))}
                <th colSpan={grid.measures.length} className={`${thCls} font-medium`}>Total</th>
              </tr>
              {showMeasureRow && (
                <tr>
                  <th className={thCls} />
                  {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                    <th key={`${col}-${m}`} className={`${thCls} font-normal text-[var(--gs-color-muted)]`}>{m}</th>
                  )))}
                  {grid.measures.map((m) => (
                    <th key={`total-${m}`} className={`${thCls} font-normal text-[var(--gs-color-muted)]`}>{m}</th>
                  ))}
                </tr>
              )}
            </thead>
            <tbody>
              {grid.rowValues.map((row) => (
                <tr key={row}>
                  <th scope="row" className={`${thCls} text-left font-medium`}>
                    <button type="button" onClick={() => clickRow(row)}>{row}</button>
                  </th>
                  {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                    <td key={`${col}-${m}`} className={thCls}>{grid.cell(row, col, m)}</td>
                  )))}
                  {grid.measures.map((m) => (
                    <td key={`total-${m}`} className={`${thCls} font-medium`}>{grid.rowTotal(row, m)}</td>
                  ))}
                </tr>
              ))}
              <tr>
                <th scope="row" className="p-1 text-left font-medium">Total</th>
                {grid.colValues.flatMap((col) => grid.measures.map((m) => (
                  <td key={`total-${col}-${m}`} className="p-1 font-medium">{grid.colTotal(col, m)}</td>
                )))}
                {grid.measures.map((m) => (
                  <td key={`grand-${m}`} className="p-1 font-medium">{grid.grandTotal(m)}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Wire the widget into the builder registry**

In `shell/src/builder/widgets/index.tsx`, add the import next to the other widget imports (near `import { registerChartWidget } from "./chart";`):

```ts
import { registerPivotWidget } from "./pivot";
```

Then add the registration call in `registerBuiltinWidgets()`, next to `registerChartWidget();`:

```ts
  registerChartWidget();
  registerPivotWidget();
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npm run test -- pivot.test.tsx`
Expected: PASS — 9 tests green.

- [ ] **Step 6: Run the full unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS — all existing suites remain green, plus the new `pivotTable.test.ts` and `pivot.test.tsx`.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/builder/widgets/pivot.tsx src/builder/widgets/pivot.test.tsx src/builder/widgets/index.tsx
git commit -m "feat(shell): pivot widget renders a crosstab with row/column-header cross-filter (SP-14g)"
```

---

## Task 3: E2E — render, row-header cross-filter, column-header cross-filter, unconfigured state

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` (all already defined at the top of this file, unmodified); the `pivot` widget registered in Task 2, addressable in the builder UI via the palette button labelled `"Pivot"` and props-panel fields labelled `"Champ lignes"` / `"Champ colonnes"`.
- Produces: nothing consumed by later tasks — this is the last task in the plan.

- [ ] **Step 1: Write the three E2E tests**

Append to the end of `shell/e2e/analytics-context.spec.ts` (after the last existing test, the histogram scenario):

```ts
// -------------------------------------------------------------------------
// Scénario 19 (SP-14g) — tableau croisé : rend une grille avec totaux à
// partir d'une source statistiques à groupBy 2 champs (region, quarter),
// puis un clic sur un en-tête de LIGNE cross-filtre une table réelle sur le
// même dataset.
//
// Choix de fixture délibérés pour éviter toute ambiguïté de sélecteur :
// - Les 4 combinaisons région×trimestre sont TOUTES présentes (aucune
//   cellule à 0) : avec seulement 2 colonnes, un total de colonne égal à
//   l'unique cellule non nulle de cette colonne serait indiscernable d'une
//   cellule de donnée (`getByRole("cell", ...)` échouerait en mode strict).
//   Les 9 valeurs affichées (4 cellules + 2 totaux de ligne + 2 totaux de
//   colonne + 1 grand total) sont choisies deux à deux distinctes.
// - La table brute affiche une seule colonne calculée "label" (ex.
//   "Nord-Q1"), pas les champs bruts région/trimestre/valeur — sinon ses
//   propres cellules dupliqueraient soit les nombres du pivot, soit ses
//   propres libellés "Nord"/"Q1" entre les 2 lignes qui les partagent.
// -------------------------------------------------------------------------
test("a pivot renders row/column totals and a row-header click cross-filters a table on the same dataset (SP-14g)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/sales/schema", async (route) => {
    await route.fulfill({
      json: { collection: "sales", pk: "id", geometry: null,
        fields: [{ name: "region", type: "string" }, { name: "quarter", type: "string" }, { name: "label", type: "string" }] },
    });
  });
  await page.route("**/collections/sales/items*", async (route) => {
    const url = new URL(route.request().url());
    const region = url.searchParams.get("region");
    const quarter = url.searchParams.get("quarter");
    const all = [
      { id: 1, properties: { region: "Nord", quarter: "Q1", label: "Nord-Q1" } },
      { id: 2, properties: { region: "Nord", quarter: "Q2", label: "Nord-Q2" } },
      { id: 3, properties: { region: "Sud", quarter: "Q1", label: "Sud-Q1" } },
      { id: 4, properties: { region: "Sud", quarter: "Q2", label: "Sud-Q2" } },
    ];
    const features = all.filter((f) =>
      (!region || f.properties.region === region) && (!quarter || f.properties.quarter === quarter));
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/sales/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: ["region", "quarter"],
        rows: [
          { region: "Nord", quarter: "Q1", value: 100 },
          { region: "Nord", quarter: "Q2", value: 23 },
          { region: "Sud", quarter: "Q1", value: 7 },
          { region: "Sud", quarter: "Q2", value: 41 },
        ],
      },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "sales", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Pivot cross-filter");
  await addFeaturesSource(page, "sales");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "sales");
  await promoteLastSource(page, 2);

  // Source 1 → basculée en statistiques, groupBy à 2 champs pour le pivot.
  await page.getByLabel(/Type de la source/).first().selectOption("statistics");
  await page.getByLabel(/Grouper par/).first().fill("region,quarter");
  await page.getByLabel(/Agrégation \(source/).first().selectOption("sum");
  await page.getByLabel(/Champ agrégé/).first().fill("value");

  await page.getByRole("button", { name: "Pivot" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ lignes").fill("region");
  await page.getByLabel("Champ colonnes").fill("quarter");

  // Source 2 → table brute liée au même dataset partagé, restreinte à la
  // colonne "label" pour ne jamais dupliquer un texte affiché par le pivot.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });
  await page.getByLabel("Colonnes").fill("label");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");

  // Grille rendue : cellules et totaux attendus, valeurs connues du fixture.
  // `exact: true` partout : Playwright fait un match par sous-chaîne par
  // défaut sur `name`, et "7"/"23" sont des sous-chaînes de "107"/"123".
  await expect(page.getByRole("cell", { name: "100", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "23", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "7", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "123", exact: true })).toBeVisible(); // total de ligne Nord (100+23)
  await expect(page.getByRole("cell", { name: "107", exact: true })).toBeVisible(); // total de colonne Q1 (100+7)
  await expect(page.getByRole("cell", { name: "171", exact: true })).toBeVisible(); // grand total

  // La table montre les 4 lignes avant tout clic.
  await expect(page.getByText("Sud-Q1")).toBeVisible();
  await expect(page.getByText("Sud-Q2")).toBeVisible();

  // Clic sur l'en-tête de ligne "Nord" → la table ne montre plus que Nord.
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/sales/items") && r.url().includes("region=Nord"));
  await page.getByRole("button", { name: "Nord", exact: true }).click();
  await filteredReq;
  await expect(page.getByText("Nord-Q1")).toBeVisible();
  await expect(page.getByText("Nord-Q2")).toBeVisible();
  await expect(page.getByText("Sud-Q1")).toBeHidden();
  await expect(page.getByText("Sud-Q2")).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 20 (SP-14g) — même montage que le scénario 19, mais le clic est
// sur un en-tête de COLONNE : preuve que le filtre porte sur le champ
// colonnes (`quarter`), pas sur le champ lignes.
// -------------------------------------------------------------------------
test("a pivot column-header click cross-filters a table on the columns field (SP-14g)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/sales/schema", async (route) => {
    await route.fulfill({
      json: { collection: "sales", pk: "id", geometry: null,
        fields: [{ name: "region", type: "string" }, { name: "quarter", type: "string" }, { name: "label", type: "string" }] },
    });
  });
  await page.route("**/collections/sales/items*", async (route) => {
    const url = new URL(route.request().url());
    const region = url.searchParams.get("region");
    const quarter = url.searchParams.get("quarter");
    const all = [
      { id: 1, properties: { region: "Nord", quarter: "Q1", label: "Nord-Q1" } },
      { id: 2, properties: { region: "Nord", quarter: "Q2", label: "Nord-Q2" } },
      { id: 3, properties: { region: "Sud", quarter: "Q1", label: "Sud-Q1" } },
      { id: 4, properties: { region: "Sud", quarter: "Q2", label: "Sud-Q2" } },
    ];
    const features = all.filter((f) =>
      (!region || f.properties.region === region) && (!quarter || f.properties.quarter === quarter));
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/sales/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: ["region", "quarter"],
        rows: [
          { region: "Nord", quarter: "Q1", value: 100 },
          { region: "Nord", quarter: "Q2", value: 23 },
          { region: "Sud", quarter: "Q1", value: 7 },
          { region: "Sud", quarter: "Q2", value: 41 },
        ],
      },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "sales", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Pivot column cross-filter");
  await addFeaturesSource(page, "sales");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "sales");
  await promoteLastSource(page, 2);

  await page.getByLabel(/Type de la source/).first().selectOption("statistics");
  await page.getByLabel(/Grouper par/).first().fill("region,quarter");
  await page.getByLabel(/Agrégation \(source/).first().selectOption("sum");
  await page.getByLabel(/Champ agrégé/).first().fill("value");

  await page.getByRole("button", { name: "Pivot" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ lignes").fill("region");
  await page.getByLabel("Champ colonnes").fill("quarter");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });
  await page.getByLabel("Colonnes").fill("label");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");

  // Clic sur l'en-tête de colonne "Q1" → seules les lignes du trimestre Q1
  // restent (Nord-Q1 et Sud-Q1), quelle que soit la région.
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/sales/items") && r.url().includes("quarter=Q1"));
  await page.getByRole("button", { name: "Q1", exact: true }).click();
  await filteredReq;
  await expect(page.getByText("Nord-Q1")).toBeVisible();
  await expect(page.getByText("Sud-Q1")).toBeVisible();
  await expect(page.getByText("Nord-Q2")).toBeHidden();
  await expect(page.getByText("Sud-Q2")).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 21 (SP-14g) — un pivot sans champs lignes/colonnes configurés
// affiche un message de configuration, ne plante jamais.
// -------------------------------------------------------------------------
test("an unconfigured pivot (no rows/columns fields) shows a configuration message (SP-14g)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }, { name: "valeur", type: "number" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { categorie: "Nord", valeur: 100 } },
    ] } });
  });

  await createApp(page, "Pivot unconfigured");
  await addFeaturesSource(page, "analytics");

  await page.getByRole("button", { name: "Pivot" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByText("Configurez les champs lignes et colonnes")).toBeVisible();
});
```

- [ ] **Step 2: Run the three new E2E tests**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts -g "SP-14g"`
Expected: PASS — 3 tests green. If a selector or assertion fails, use Playwright's trace/HTML report (`npx playwright show-report`) to inspect the actual DOM and adjust the test to match real rendered output — do not change the widget implementation to satisfy an incorrect test expectation without re-checking the spec first.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS — all existing specs remain green (39+ scenarios), plus the 3 new SP-14g scenarios.

- [ ] **Step 4: Run the full non-regression check (unit + build)**

Run: `cd shell && npm run test && npm run build`
Expected: PASS — full Vitest suite green, `tsc --noEmit` clean, Vite build succeeds.

- [ ] **Step 5: Commit**

```bash
cd shell && git add e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover pivot rendering, totals, row/column-header cross-filter and unconfigured state (SP-14g)"
```
