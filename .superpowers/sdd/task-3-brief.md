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

