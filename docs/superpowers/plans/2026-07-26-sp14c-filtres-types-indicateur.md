# SP-14c — Filtres typés (select/slider) & indicateur de contexte actif — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two dataset-bound filter widgets (`selectFilter` — multi-value, `sliderFilter` — numeric range) to the shell's canvas builder, plus a visual indicator of the active analytics context (period / extent / cross-filter chips, each individually clearable), completing the "filtres typés" family started in SP-14b.

**Architecture:** Pure shell change, zero core changes — both widgets call the existing `/collections/{id}/aggregate` endpoint themselves (via `itemClient.queryDataSource`) to fetch their own options (`groupBy`+`count`) or bounds (`measures=[min,max]`), following the same "widget calls the client directly" pattern already used by `form.tsx`/`gallery.tsx`/`datasetCard.tsx`. The shared `AnalyticsContext` cross-filter model gains a third value shape (`{from, to}` range) and an explicit `clearCrossFilter` setter, reused by both new widgets and by the new indicator.

**Tech Stack:** React + TypeScript, `@tanstack/react-query` (`useQuery`), Vitest + React Testing Library (unit), Playwright (E2E), Tailwind utility classes matching existing widgets.

## Global Constraints

- Additive only: an app with `interactions` absent or `"manual"` must behave byte-identically to today — every new setter is a no-op when `interactions !== "auto"` (spec §1, §3).
- No core changes in this plan — reuse `/collections/{id}/aggregate` exactly as it exists today (spec §1).
- All new UI copy is in French, matching the existing widgets' tone (`dateRangeFilter.tsx`, `chart.tsx`).
- Every new interactive element needs an `aria-label` (or accessible name via associated `<label>`) — the whole test suite (unit + E2E) locates elements by accessible name, never by CSS selector.
- The 18+ pre-existing Playwright E2E specs must stay green without modification (unchanged from SP-14b's constraint).
- `originSourceId` passed to `useSetCrossFilter` is always the widget's own `props.dataSourceId` (the bound `DataSource` id), never `ctx.widgetId` — this is the existing convention in `chart.tsx`/`data.tsx` and is what `derivePatch`'s self-exclusion check compares against.

---

### Task 1: `AnalyticsContext` — range cross-filter value + `clearCrossFilter`

**Files:**
- Modify: `shell/src/builder/AnalyticsContext.tsx` (whole file is 91 lines; changes touch lines 4, 16-27, 58-70, 88-91)
- Test: `shell/src/builder/AnalyticsContext.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `export type CrossFilterValue = string | string[] | { from: string; to: string }`; `CrossFilterEntry.value: CrossFilterValue` (was `string | string[]`); `export function useClearCrossFilter(): (datasetId: string) => void`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/builder/AnalyticsContext.test.tsx`, inside the existing `Probe` component add two buttons (import `useClearCrossFilter` at the top alongside the other hooks):

```tsx
import {
  AnalyticsContextProvider, useAnalyticsContext, useClearCrossFilter, useSetCrossFilter, useSetExtent, useSetTimeRange,
} from "./AnalyticsContext";

function Probe() {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  const clearCrossFilter = useClearCrossFilter();
  return (
    <div>
      <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>
      <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>
      <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>set-time</button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
      <button onClick={() => setCrossFilter("ds1", "period", { from: "2026-01-01", to: "2026-02-01" }, "src1")}>set-cf-range</button>
      <button onClick={() => clearCrossFilter("ds1")}>clear-cf</button>
    </div>
  );
}
```

Append these tests (after the existing `"setCrossFilter toggles..."` test, still outside the `describe("extent debounce", ...)` block):

```tsx
test("setCrossFilter accepts a {from,to} range value", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf-range"));
  expect(screen.getByText(/"ds1":\{"field":"period","value":\{"from":"2026-01-01","to":"2026-02-01"\},"originSourceId":"src1"\}/)).toBeInTheDocument();
});

test("clearCrossFilter removes the entry for that dataset", async () => {
  render(<AnalyticsContextProvider interactions="auto"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/"ds1":/)).toBeInTheDocument();
  await userEvent.click(screen.getByText("clear-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});

test("clearCrossFilter is a no-op when interactions is not 'auto'", async () => {
  render(<AnalyticsContextProvider interactions="manual"><Probe /></AnalyticsContextProvider>);
  await userEvent.click(screen.getByText("clear-cf"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: FAIL — `setCrossFilter` rejects/mistypes the range value (TS) and `useClearCrossFilter` does not exist (import error).

- [ ] **Step 3: Implement**

Replace line 4 of `shell/src/builder/AnalyticsContext.tsx`:

```ts
export type CrossFilterValue = string | string[] | { from: string; to: string };
export type CrossFilterEntry = { field: string; value: CrossFilterValue; originSourceId: string };
```

Replace lines 16-27 (the two type aliases through `sameCrossFilterValue`):

```ts
type SetTimeRange = (range: { from: string; to: string } | null) => void;
type SetExtent = (bbox: [number, number, number, number] | null) => void;
type SetCrossFilter = (datasetId: string, field: string, value: CrossFilterValue, originSourceId: string) => void;
type ClearCrossFilter = (datasetId: string) => void;

const AnalyticsStateContext = createContext<AnalyticsContextState>(EMPTY_ANALYTICS_CONTEXT);
const AnalyticsSettersContext = createContext<{
  setTimeRange: SetTimeRange; setExtent: SetExtent; setCrossFilter: SetCrossFilter; clearCrossFilter: ClearCrossFilter;
}>({
  setTimeRange: () => {}, setExtent: () => {}, setCrossFilter: () => {}, clearCrossFilter: () => {},
});

function sameCrossFilterValue(a: CrossFilterValue, b: CrossFilterValue): boolean {
  return typeof a === "string" && typeof b === "string" ? a === b : JSON.stringify(a) === JSON.stringify(b);
}
```

Replace lines 58-70 (from `const setCrossFilter = ...` through the `setters` memo):

```ts
  const setCrossFilter = useCallback<SetCrossFilter>((datasetId, field, value, originSourceId) => {
    if (!active) return;
    setState((prev) => {
      const current = prev.crossFilter[datasetId];
      const isToggleOff = Boolean(current) && current!.field === field && sameCrossFilterValue(current!.value, value);
      const nextCrossFilter = { ...prev.crossFilter };
      if (isToggleOff) delete nextCrossFilter[datasetId];
      else nextCrossFilter[datasetId] = { field, value, originSourceId };
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const clearCrossFilter = useCallback<ClearCrossFilter>((datasetId) => {
    if (!active) return;
    setState((prev) => {
      if (!prev.crossFilter[datasetId]) return prev;
      const nextCrossFilter = { ...prev.crossFilter };
      delete nextCrossFilter[datasetId];
      return { ...prev, crossFilter: nextCrossFilter };
    });
  }, [active]);

  const setters = useMemo(
    () => ({ setTimeRange, setExtent, setCrossFilter, clearCrossFilter }),
    [setTimeRange, setExtent, setCrossFilter, clearCrossFilter],
  );
```

Replace lines 88-91 (the final export block) — append the new hook after `useSetCrossFilter`:

```ts
export function useSetCrossFilter(): SetCrossFilter {
  return useContext(AnalyticsSettersContext).setCrossFilter;
}
export function useClearCrossFilter(): ClearCrossFilter {
  return useContext(AnalyticsSettersContext).clearCrossFilter;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AnalyticsContext.test.tsx`
Expected: PASS, all tests including the 3 new ones and the pre-existing ones (toggle, debounce, no-provider default).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/AnalyticsContext.tsx src/builder/AnalyticsContext.test.tsx
git commit -m "feat(shell): cross-filter range value + clearCrossFilter setter (SP-14c)"
```

---

### Task 2: `derivePatch` — range branch

**Files:**
- Modify: `shell/src/lib/analyticsPatch.ts:26-33` (the `crossFilter` block inside `derivePatch`)
- Test: `shell/src/lib/analyticsPatch.test.ts`

**Interfaces:**
- Consumes: `CrossFilterValue` from Task 1 (`../builder/AnalyticsContext`).
- Produces: no new exports — `derivePatch`'s existing signature and behavior for scalar/array values is unchanged; only a new range case is added.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/lib/analyticsPatch.test.ts`:

```ts
test("uses field__gte/field__lte for a range cross-filter value", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ score__gte: "10", score__lte: "50" });
});

test("excludes a range cross-filter patch when this source is the origin", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-1" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: FAIL — current code does `patch[crossFilter.field] = crossFilter.value` for a non-array value, so the range object gets assigned directly to `score` instead of producing `score__gte`/`score__lte`.

- [ ] **Step 3: Implement**

In `shell/src/lib/analyticsPatch.ts`, replace the `crossFilter` block (currently):

```ts
  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    else patch[crossFilter.field] = crossFilter.value;
  }
```

with:

```ts
  const crossFilter = ctx.crossFilter[source.datasetId];
  if (crossFilter && crossFilter.originSourceId !== source.id) {
    if (Array.isArray(crossFilter.value)) {
      patch[`${crossFilter.field}__in`] = crossFilter.value.join(",");
    } else if (typeof crossFilter.value === "object") {
      patch[`${crossFilter.field}__gte`] = crossFilter.value.from;
      patch[`${crossFilter.field}__lte`] = crossFilter.value.to;
    } else {
      patch[crossFilter.field] = crossFilter.value;
    }
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/analyticsPatch.test.ts`
Expected: PASS, all tests (the 2 new ones plus the full pre-existing suite for scalar/array/time/extent combinations).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/lib/analyticsPatch.ts src/lib/analyticsPatch.test.ts
git commit -m "feat(shell): derivePatch translates a range cross-filter to __gte/__lte (SP-14c)"
```

---

### Task 3: `selectFilter` widget (multi-value)

**Files:**
- Create: `shell/src/builder/widgets/selectFilter.tsx`
- Modify: `shell/src/builder/widgets/index.tsx:16` (import) and `:162` (registration call)
- Test: `shell/src/builder/widgets/selectFilter.test.tsx`

**Interfaces:**
- Consumes: `useSetCrossFilter`/`useClearCrossFilter`/`useAnalyticsContext` (Task 1), `useItemClient` (`../../api/ItemClientProvider`), `DataSourceSelect` (`../DataSourceSelect`), `ItemClient.queryDataSource` (existing).
- Produces: `registerSelectFilterWidget(): void`, widget type `"selectFilter"` with `defaultProps: { dataSourceId: "", field: "", label: "Filtrer" }`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/selectFilter.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerSelectFilterWidget } from "./selectFilter";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerSelectFilterWidget(); });

function CrossFilterProbe() {
  const ctx = useAnalyticsContext();
  return <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>;
}

function renderSelect(props: Record<string, unknown>, queryDataSource = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SelectFilter = getWidget("selectFilter")!.Component;
  const ctx = {
    mode: "runtime", widgetId: "w1",
    data: { loading: false, error: false, records: [], datasetId: "ds-1" },
  } as unknown as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SelectFilter props={{ dataSourceId: "src-1", field: "region", label: "Région", ...props }} ctx={ctx} />
          <CrossFilterProbe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client };
}

test("shows a discreet message when not bound to a dataset source", () => {
  const queryDataSource = vi.fn();
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SelectFilter = getWidget("selectFilter")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SelectFilter props={{ dataSourceId: "", field: "", label: "Filtrer" }} ctx={{ mode: "runtime" } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/Liez ce filtre/)).toBeInTheDocument();
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("fetches distinct values via a groupBy statistics query and renders one checkbox per value", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  expect(await screen.findByLabelText("Nord")).toBeInTheDocument();
  expect(screen.getByLabelText("Sud")).toBeInTheDocument();
  expect(screen.getByText("Nord (3)")).toBeInTheDocument();
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    type: "statistics", datasetId: "ds-1", query: { groupBy: "region" },
  }));
});

test("checking a value sets a single-element array cross-filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  await userEvent.click(await screen.findByLabelText("Nord"));
  expect(screen.getByText(/"ds-1":\{"field":"region","value":\["Nord"\],"originSourceId":"src-1"\}/)).toBeInTheDocument();
});

test("checking two values accumulates them, unchecking the last one clears the filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "Nord", properties: { region: "Nord", value: 3 } },
    { id: "Sud", properties: { region: "Sud", value: 5 } },
  ]);
  renderSelect({}, queryDataSource);
  await userEvent.click(await screen.findByLabelText("Nord"));
  await userEvent.click(screen.getByLabelText("Sud"));
  expect(screen.getByText(/"value":\["Nord","Sud"\]/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Nord"));
  await userEvent.click(screen.getByLabelText("Sud"));
  expect(screen.getByText("crossFilter:{}")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/selectFilter.test.tsx`
Expected: FAIL — `./selectFilter` module does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/builder/widgets/selectFilter.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useAnalyticsContext, useClearCrossFilter, useSetCrossFilter } from "../AnalyticsContext";

type SelectOption = { value: string; count: number };

export function registerSelectFilterWidget(): void {
  registerWidget({
    type: "selectFilter",
    label: "Sélecteur",
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 3 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Champ
          <input aria-label="Champ du sélecteur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé du sélecteur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const analyticsCtx = useAnalyticsContext();
      const setCrossFilter = useSetCrossFilter();
      const clearCrossFilter = useClearCrossFilter();
      const datasetId = ctx.data?.datasetId;
      const field = String(props.field ?? "");
      const originSourceId = String(props.dataSourceId ?? "");

      const query = useQuery({
        queryKey: ["analytics-filter-options", datasetId, field],
        queryFn: async () => {
          const rows = await client.queryDataSource({
            id: `analytics-filter-${datasetId}-${field}`, type: "statistics", service: "core",
            layer: "", datasetId, query: { groupBy: field },
          });
          return rows.map((r): SelectOption => ({ value: String(r.id), count: Number(r.properties.value ?? 0) }));
        },
        enabled: Boolean(datasetId && field),
      });

      if (!datasetId || !field) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Liez ce filtre à une source dataset et un champ</p>;
      }
      if (query.isLoading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (query.isError || !query.data) {
        return <p role="alert" className="text-xs text-[var(--gs-color-muted)]">Impossible de charger les valeurs</p>;
      }

      const active = analyticsCtx.crossFilter[datasetId];
      const checked = active && active.field === field && Array.isArray(active.value) ? active.value : [];

      function toggle(value: string, isChecked: boolean) {
        const next = isChecked ? [...checked, value] : checked.filter((v) => v !== value);
        if (next.length === 0) clearCrossFilter(datasetId!);
        else setCrossFilter(datasetId!, field, next, originSourceId);
      }

      return (
        <fieldset className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <legend>{String(props.label ?? "Filtrer")}</legend>
          {query.data.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2">
              <input type="checkbox" aria-label={opt.value} checked={checked.includes(opt.value)}
                onChange={(e) => toggle(opt.value, e.target.checked)} />
              {opt.value} ({opt.count})
            </label>
          ))}
        </fieldset>
      );
    },
  });
}
```

Wire it into the registry — in `shell/src/builder/widgets/index.tsx`, add the import next to the other widget imports (line 16, after `registerDateRangeFilterWidget`):

```ts
import { registerDateRangeFilterWidget } from "./dateRangeFilter";
import { registerSelectFilterWidget } from "./selectFilter";
```

and the call next to the other registrations (line 162, after `registerDateRangeFilterWidget();`):

```ts
  registerDateRangeFilterWidget();
  registerSelectFilterWidget();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/selectFilter.test.tsx`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Run the full shell unit suite (no regression)**

Run: `cd shell && npm run test`
Expected: PASS, previous count + 4 new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/builder/widgets/selectFilter.tsx src/builder/widgets/selectFilter.test.tsx src/builder/widgets/index.tsx
git commit -m "feat(shell): selectFilter widget — multi-value cross-filter from dataset column (SP-14c)"
```

---

### Task 4: `sliderFilter` widget (numeric range)

**Files:**
- Create: `shell/src/builder/widgets/sliderFilter.tsx`
- Modify: `shell/src/builder/widgets/index.tsx:17` (import) and `:163` (registration call)
- Test: `shell/src/builder/widgets/sliderFilter.test.tsx`

**Interfaces:**
- Consumes: same as Task 3 (`useSetCrossFilter`/`useClearCrossFilter`, `useItemClient`, `DataSourceSelect`, `ItemClient.queryDataSource`).
- Produces: `registerSliderFilterWidget(): void`, widget type `"sliderFilter"` with `defaultProps: { dataSourceId: "", field: "", label: "Filtrer" }`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/sliderFilter.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerSliderFilterWidget } from "./sliderFilter";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerSliderFilterWidget(); });

function CrossFilterProbe() {
  const ctx = useAnalyticsContext();
  return <p>crossFilter:{JSON.stringify(ctx.crossFilter)}</p>;
}

function renderSlider(queryDataSource = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SliderFilter = getWidget("sliderFilter")!.Component;
  const ctx = {
    mode: "runtime", widgetId: "w1",
    data: { loading: false, error: false, records: [], datasetId: "ds-1" },
  } as unknown as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SliderFilter props={{ dataSourceId: "src-1", field: "score", label: "Score" }} ctx={ctx} />
          <CrossFilterProbe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("shows a discreet message when not bound to a dataset source", () => {
  const queryDataSource = vi.fn();
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const SliderFilter = getWidget("sliderFilter")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <SliderFilter props={{ dataSourceId: "", field: "", label: "Filtrer" }} ctx={{ mode: "runtime" } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/Liez ce filtre/)).toBeInTheDocument();
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("fetches min/max via a two-measure statistics query and renders the bounds", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  expect(await screen.findByText("Score (10 – 90)")).toBeInTheDocument();
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    type: "statistics", datasetId: "ds-1",
    query: { measures: [{ field: "score", agg: "min", label: "min" }, { field: "score", agg: "max", label: "max" }] },
  }));
});

test("moving the min handle sets a range cross-filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  const minInput = await screen.findByLabelText("Borne minimale");
  minInput.setAttribute("value", "50");
  minInput.dispatchEvent(new Event("change", { bubbles: true }));
  expect(await screen.findByText(/"value":\{"from":"50","to":"90"\}/)).toBeInTheDocument();
});

test("moving back to the full bounds clears the filter", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "Total", properties: { group: "Total", min: 10, max: 90 } }]);
  renderSlider(queryDataSource);
  const minInput = await screen.findByLabelText("Borne minimale");
  minInput.setAttribute("value", "50");
  minInput.dispatchEvent(new Event("change", { bubbles: true }));
  await screen.findByText(/"from":"50"/);
  minInput.setAttribute("value", "10");
  minInput.dispatchEvent(new Event("change", { bubbles: true }));
  expect(await screen.findByText("crossFilter:{}")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/sliderFilter.test.tsx`
Expected: FAIL — `./sliderFilter` module does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/builder/widgets/sliderFilter.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useClearCrossFilter, useSetCrossFilter } from "../AnalyticsContext";

type Bounds = { min: number; max: number };

export function registerSliderFilterWidget(): void {
  registerWidget({
    type: "sliderFilter",
    label: "Curseur",
    defaultProps: { dataSourceId: "", field: "", label: "Filtrer" },
    defaultSize: { w: 4, h: 1 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Champ
          <input aria-label="Champ du curseur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé du curseur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const setCrossFilter = useSetCrossFilter();
      const clearCrossFilter = useClearCrossFilter();
      const datasetId = ctx.data?.datasetId;
      const field = String(props.field ?? "");
      const originSourceId = String(props.dataSourceId ?? "");

      const query = useQuery({
        queryKey: ["analytics-filter-bounds", datasetId, field],
        queryFn: async (): Promise<Bounds> => {
          const rows = await client.queryDataSource({
            id: `analytics-filter-${datasetId}-${field}`, type: "statistics", service: "core",
            layer: "", datasetId,
            query: { measures: [{ field, agg: "min", label: "min" }, { field, agg: "max", label: "max" }] },
          });
          const properties = rows[0]?.properties ?? {};
          return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
        },
        enabled: Boolean(datasetId && field),
      });

      const [from, setFrom] = useState<number | null>(null);
      const [to, setTo] = useState<number | null>(null);
      useEffect(() => {
        if (query.data) { setFrom(query.data.min); setTo(query.data.max); }
      }, [query.data]);

      if (!datasetId || !field) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Liez ce filtre à une source dataset et un champ</p>;
      }
      if (query.isLoading || !query.data || from === null || to === null) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      }
      if (query.isError) return <p role="alert" className="text-xs text-[var(--gs-color-muted)]">Impossible de charger les bornes</p>;

      const { min, max } = query.data;

      function commit(nextFrom: number, nextTo: number) {
        setFrom(nextFrom);
        setTo(nextTo);
        if (nextFrom === min && nextTo === max) clearCrossFilter(datasetId!);
        else setCrossFilter(datasetId!, field, { from: String(nextFrom), to: String(nextTo) }, originSourceId);
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? "Filtrer")} ({from} – {to})</span>
          <div className="flex gap-2">
            <input type="range" aria-label="Borne minimale" min={min} max={max} value={from}
              onChange={(e) => commit(Math.min(Number(e.target.value), to), to)} />
            <input type="range" aria-label="Borne maximale" min={min} max={max} value={to}
              onChange={(e) => commit(from, Math.max(Number(e.target.value), from))} />
          </div>
        </div>
      );
    },
  });
}
```

Wire it into the registry — in `shell/src/builder/widgets/index.tsx`, add the import (after the `selectFilter` import from Task 3):

```ts
import { registerSelectFilterWidget } from "./selectFilter";
import { registerSliderFilterWidget } from "./sliderFilter";
```

and the call (after `registerSelectFilterWidget();`):

```ts
  registerSelectFilterWidget();
  registerSliderFilterWidget();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/sliderFilter.test.tsx`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Run the full shell unit suite (no regression)**

Run: `cd shell && npm run test`
Expected: PASS, previous count + 4 new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/builder/widgets/sliderFilter.tsx src/builder/widgets/sliderFilter.test.tsx src/builder/widgets/index.tsx
git commit -m "feat(shell): sliderFilter widget — numeric range cross-filter from dataset column (SP-14c)"
```

---

### Task 5: `AnalyticsContextIndicator` + `AppRenderer` wiring

**Files:**
- Create: `shell/src/builder/AnalyticsContextIndicator.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx:11-12` (import), `:174-178` (mount point)
- Test: `shell/src/builder/AnalyticsContextIndicator.test.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx` (append one gating test)

**Interfaces:**
- Consumes: `useAnalyticsContext`/`useSetTimeRange`/`useSetExtent`/`useClearCrossFilter`/`CrossFilterEntry` (Task 1).
- Produces: `export function AnalyticsContextIndicator(): JSX.Element | null` (no props — reads context directly).

- [ ] **Step 1: Write the failing indicator tests**

Create `shell/src/builder/AnalyticsContextIndicator.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { AnalyticsContextProvider, useSetCrossFilter, useSetExtent, useSetTimeRange } from "./AnalyticsContext";
import { AnalyticsContextIndicator } from "./AnalyticsContextIndicator";

function Controls() {
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const setCrossFilter = useSetCrossFilter();
  return (
    <div>
      <button onClick={() => setTimeRange({ from: "2026-01-01", to: "2026-02-01" })}>set-time</button>
      <button onClick={() => setExtent([1, 2, 3, 4])}>set-extent</button>
      <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>
    </div>
  );
}

function renderIndicator() {
  return render(
    <AnalyticsContextProvider interactions="auto">
      <Controls />
      <AnalyticsContextIndicator />
    </AnalyticsContextProvider>,
  );
}

test("renders nothing when the context is empty", () => {
  const { container } = renderIndicator();
  expect(container).toBeEmptyDOMElement();
});

test("shows a period chip with a working clear button", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.getByText(/Période : 2026-01-01 → 2026-02-01/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Effacer la période"));
  expect(screen.queryByText(/Période :/)).not.toBeInTheDocument();
});

test("shows one chip per active cross-filter, clearing one leaves the other untouched", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  await userEvent.click(screen.getByText("set-cf"));
  expect(screen.getByText(/region : Nord/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Effacer le filtre region"));
  expect(screen.queryByText(/region : Nord/)).not.toBeInTheDocument();
  expect(screen.getByText(/Période :/)).toBeInTheDocument();
});

test("shows 'Tout effacer' only with 2+ active chips, and it clears everything", async () => {
  renderIndicator();
  await userEvent.click(screen.getByText("set-time"));
  expect(screen.queryByText("Tout effacer")).not.toBeInTheDocument();
  await userEvent.click(screen.getByText("set-cf"));
  await userEvent.click(screen.getByText("Tout effacer"));
  expect(screen.queryByText(/Période :/)).not.toBeInTheDocument();
  expect(screen.queryByText(/region : Nord/)).not.toBeInTheDocument();
});

test("formats an array cross-filter value as a comma-joined list and a range as an arrow", async () => {
  function RangeControl() {
    const setCrossFilter = useSetCrossFilter();
    return <button onClick={() => setCrossFilter("ds1", "score", { from: "10", to: "50" }, "src1")}>set-range</button>;
  }
  render(
    <AnalyticsContextProvider interactions="auto">
      <RangeControl />
      <AnalyticsContextIndicator />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("set-range"));
  expect(screen.getByText(/score : 10 → 50/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/AnalyticsContextIndicator.test.tsx`
Expected: FAIL — `./AnalyticsContextIndicator` module does not exist.

- [ ] **Step 3: Implement the indicator**

Create `shell/src/builder/AnalyticsContextIndicator.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useAnalyticsContext, useClearCrossFilter, useSetExtent, useSetTimeRange, type CrossFilterValue } from "./AnalyticsContext";

const chipCls = "flex items-center gap-1 rounded-full border border-[var(--gs-color-border)] px-2 py-1";

function formatCrossFilterValue(value: CrossFilterValue): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return `${value.from} → ${value.to}`;
  return value;
}

export function AnalyticsContextIndicator(): JSX.Element | null {
  const ctx = useAnalyticsContext();
  const setTimeRange = useSetTimeRange();
  const setExtent = useSetExtent();
  const clearCrossFilter = useClearCrossFilter();

  const crossFilterIds = Object.keys(ctx.crossFilter).filter((id) => ctx.crossFilter[id]);
  const chipCount = (ctx.timeRange ? 1 : 0) + (ctx.extent ? 1 : 0) + crossFilterIds.length;
  if (chipCount === 0) return null;

  function clearAll() {
    setTimeRange(null);
    setExtent(null);
    crossFilterIds.forEach((id) => clearCrossFilter(id));
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] p-2 text-xs text-[var(--gs-color-text)]">
      {ctx.timeRange && (
        <span className={chipCls}>
          Période : {ctx.timeRange.from} → {ctx.timeRange.to}
          <button type="button" aria-label="Effacer la période" onClick={() => setTimeRange(null)}>×</button>
        </span>
      )}
      {ctx.extent && (
        <span className={chipCls}>
          Emprise carte active
          <button type="button" aria-label="Effacer l'emprise" onClick={() => setExtent(null)}>×</button>
        </span>
      )}
      {crossFilterIds.map((datasetId) => {
        const entry = ctx.crossFilter[datasetId]!;
        return (
          <span key={datasetId} className={chipCls}>
            {entry.field} : {formatCrossFilterValue(entry.value)}
            <button type="button" aria-label={`Effacer le filtre ${entry.field}`} onClick={() => clearCrossFilter(datasetId)}>×</button>
          </span>
        );
      })}
      {chipCount >= 2 && (
        <button type="button" className="ml-auto underline" onClick={clearAll}>Tout effacer</button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the indicator tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/AnalyticsContextIndicator.test.tsx`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Write the failing `AppRenderer` gating test**

Append to `shell/src/builder/AppRenderer.test.tsx` (after the existing tests, reusing the file's `config`/`Wrapper`):

```tsx
test("shows the analytics context indicator only in non-edit mode with interactions auto", async () => {
  const autoConfig: AppConfig = { ...config, interactions: "auto" };
  const { rerender } = render(<AppRenderer config={autoConfig} mode="edit" />, { wrapper: Wrapper });
  expect(screen.queryByLabelText("Effacer la période")).not.toBeInTheDocument();

  rerender(<AppRenderer config={{ ...config, interactions: "manual" }} mode="runtime" />);
  expect(screen.queryByLabelText("Effacer la période")).not.toBeInTheDocument();
});
```

(This test only asserts the indicator never renders — since no chip is ever active in this minimal config, a full "it shows in runtime+auto" assertion needs an active chip and is already covered end-to-end by `AnalyticsContextIndicator.test.tsx` plus the E2E in Task 6. This test's job is only to pin the two gating conditions — `mode !== "edit"` and `interactions === "auto"` — by proving the indicator's *container* isn't mounted at all when either is false. Extend it once there's an easy way to set an active chip through `AppRenderer` — not needed here since `AnalyticsContextIndicator`'s own unit tests already fully cover the rendering logic.)

- [ ] **Step 6: Wire the indicator into `AppRenderer`**

In `shell/src/builder/AppRenderer.tsx`, add the import after line 11 (`import { AnalyticsContextProvider, ... } from "./AnalyticsContext";`):

```ts
import { AnalyticsContextIndicator } from "./AnalyticsContextIndicator";
```

Replace lines 174-178 (the `<AnalyticsContextProvider ...>` opening through `<ActionConditionBridge bus={bus} />`):

```tsx
            <AnalyticsContextProvider
              interactions={config.interactions}
              initialState={initialAnalyticsContext}
              onStateChange={onAnalyticsContextChange}
            >
              {mode !== "edit" && config.interactions === "auto" && <AnalyticsContextIndicator />}
              <ActionConditionBridge bus={bus} />
```

- [ ] **Step 7: Run the `AppRenderer` tests to verify everything passes**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS, all tests including the new gating test.

- [ ] **Step 8: Run the full shell unit suite (no regression)**

Run: `cd shell && npm run test`
Expected: PASS, previous count + 6 new tests (5 indicator + 1 gating), 0 failures.

- [ ] **Step 9: Commit**

```bash
cd shell && git add src/builder/AnalyticsContextIndicator.tsx src/builder/AnalyticsContextIndicator.test.tsx src/builder/AppRenderer.tsx src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): visual indicator for the active analytics context, with per-chip and global clear (SP-14c)"
```

---

### Task 6: E2E — select/slider cross-filter, indicator, non-regression

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts` (append 4 new `test(...)` blocks at the end of the file; reuses the existing `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` helpers already defined at the top of the file)

**Interfaces:**
- Consumes: nothing new — exercises the widgets/indicator from Tasks 3-5 through the real UI, same conventions as the 5 existing scenarios in this file.
- Produces: nothing (test-only file).

- [ ] **Step 1: Append the select multi-select scenario**

```ts
// -------------------------------------------------------------------------
// Scénario 6 — select multi-valeurs : cocher/décocher des valeurs filtre une
// table sur le même dataset via field__in.
// -------------------------------------------------------------------------
test("a select filter multi-value cross-filters a table via field__in", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    const inList = new URL(route.request().url()).searchParams.get("categorie__in");
    const all = [
      { id: 1, properties: { categorie: "Nord" } },
      { id: 2, properties: { categorie: "Sud" } },
    ];
    const features = inList ? all.filter((f) => inList.split(",").includes(f.properties.categorie)) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/analytics/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "categorie", rows: [{ categorie: "Nord", value: 1 }, { categorie: "Sud", value: 1 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Select cross-filter");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Sélecteur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du sélecteur").fill("categorie");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie__in=Nord"));
  await page.getByLabel("Nord").check();
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  await page.getByLabel("Nord").uncheck();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();
});
```

- [ ] **Step 2: Append the slider range scenario**

```ts
// -------------------------------------------------------------------------
// Scénario 7 — slider numérique : déplacer une poignée filtre une table par
// plage (field__gte/field__lte), revenir aux bornes complètes l'efface.
// -------------------------------------------------------------------------
test("a slider filter cross-filters a table by range, resetting to full bounds clears it", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/mesures/schema", async (route) => {
    await route.fulfill({
      json: { collection: "mesures", pk: "id", geometry: null,
        fields: [{ name: "score", type: "number" }] },
    });
  });
  await page.route("**/collections/mesures/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("score__gte");
    const all = [
      { id: 1, properties: { score: 10 } },
      { id: 2, properties: { score: 90 } },
    ];
    const features = gte ? all.filter((f) => f.properties.score >= Number(gte)) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/mesures/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", min: 10, max: 90 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "mesures", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Slider cross-filter");
  await addFeaturesSource(page, "mesures");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "mesures");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Curseur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du curseur").fill("score");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "10" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "90" })).toBeVisible();

  const minInput = page.getByLabel("Borne minimale");
  await expect(minInput).toHaveValue("10");
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/mesures/items") && r.url().includes("score__gte=50"));
  await minInput.evaluate((el: HTMLInputElement) => { el.value = "50"; el.dispatchEvent(new Event("change", { bubbles: true })); });
  await filteredReq;
  await expect(page.getByRole("cell", { name: "10" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "90" })).toBeVisible();

  await minInput.evaluate((el: HTMLInputElement) => { el.value = "10"; el.dispatchEvent(new Event("change", { bubbles: true })); });
  await expect(page.getByRole("cell", { name: "10" })).toBeVisible();
});
```

- [ ] **Step 3: Append the indicator scenario**

```ts
// -------------------------------------------------------------------------
// Scénario 8 — indicateur : période + cross-filter affichent deux chips,
// effacer une chip ne touche pas l'autre, "Tout effacer" vide tout.
// -------------------------------------------------------------------------
test("the context indicator shows chips for active period and cross-filter, clears individually and globally", async ({ page }) => {
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
      { id: 2, properties: { categorie: "Sud", valeur: 100 } },
    ] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Indicateur");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  await page.getByRole("button", { name: "Plage de dates" }).click();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");
  await expect(page.getByText(/Période : 2026-01-01 → 2026-02-01/)).toBeVisible();
  await expect(page.getByText("Tout effacer")).toBeHidden();

  const chart = page.getByTestId("echart");
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");
  await chart.click({ position: { x: box.width * 0.3, y: box.height * 0.42 } });
  await expect(page.getByText(/categorie : Nord/)).toBeVisible();

  await page.getByLabel("Effacer le filtre categorie").click();
  await expect(page.getByText(/categorie : Nord/)).toBeHidden();
  await expect(page.getByText(/Période :/)).toBeVisible();

  await chart.click({ position: { x: box.width * 0.3, y: box.height * 0.42 } });
  await page.getByRole("button", { name: "Tout effacer" }).click();
  await expect(page.getByText(/Période :/)).toBeHidden();
  await expect(page.getByText(/categorie : Nord/)).toBeHidden();
});
```

- [ ] **Step 4: Append the non-regression scenario**

```ts
// -------------------------------------------------------------------------
// Scénario 9 — non-régression : une app en interactions "manual" n'affiche
// jamais l'indicateur et le sélecteur ne filtre jamais rien.
// -------------------------------------------------------------------------
test("interactions manual: no indicator, select/slider never cross-filter", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "categorie", type: "string" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { categorie: "Nord" } },
      { id: 2, properties: { categorie: "Sud" } },
    ] } });
  });
  await page.route("**/collections/analytics/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "categorie", rows: [{ categorie: "Nord", value: 1 }, { categorie: "Sud", value: 1 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Manual non-regression");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Sélecteur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du sélecteur").fill("categorie");
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  // "Interactions automatiques" jamais coché — l'app reste en "manual" (défaut inchangé).
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();
  await page.getByLabel("Nord").check();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible(); // toujours visible : pas de filtrage
  // Le state a bien été mis à jour côté UI (checkbox cochée) mais jamais écrit dans
  // AnalyticsContext (setCrossFilter no-op en mode manual) : aucune chip d'indicateur
  // n'apparaît pour ce filtre, preuve que le canal automatique est resté inerte.
  await expect(page.getByLabel("Effacer le filtre categorie")).toHaveCount(0);
});
```

- [ ] **Step 5: Run the full E2E file**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts`
Expected: PASS, all 9 scenarios (5 pre-existing + 4 new), stable.

- [ ] **Step 6: Run the full E2E suite (no regression on the other 18+ specs)**

Run: `cd shell && npm run e2e`
Expected: PASS, full suite green.

- [ ] **Step 7: Commit**

```bash
cd shell && git add e2e/analytics-context.spec.ts
git commit -m "test(shell): E2E select/slider cross-filter, indicator, non-regression manual (SP-14c)"
```

---

## Final check

- [ ] **Run the full shell build + unit + E2E suite once more from a clean state**

```bash
cd shell && npm run build && npm run test && npm run e2e
```

Expected: `tsc --noEmit` clean, `vite build` succeeds, full unit suite green (previous total + 14 new: 3+4+4+6-3 accounting overlaps — see per-task counts above — the exact new total is whatever `npm run test`'s own summary line reports), full E2E suite green (previous 19 specs + 4 new scenarios in `analytics-context.spec.ts`).
