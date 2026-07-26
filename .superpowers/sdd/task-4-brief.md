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

