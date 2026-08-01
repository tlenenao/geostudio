### Task 5: `chart` — "compare periods" mode for line/area

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts`
- Modify: `shell/src/builder/widgets/chartOption.test.ts`
- Modify: `shell/src/builder/widgets/chart.tsx`
- Modify (full rewrite): `shell/src/builder/widgets/chart.test.tsx`

**Interfaces:**
- Consumes: `bucketFor`, `referenceWindow`, `windowedStatisticsSource`, `type ReferenceMode`, `type BucketGranularity` (Task 3, `../../lib/comparisonWindow`).
- Produces: `buildCompareOption(props: ChartProps, current: ComparePoint[], reference: ComparePoint[], bucket: BucketGranularity): EChartsOption` and `type ComparePoint = { bucket: string; value: number }`, exported from `chartOption.ts` alongside the existing `buildOption`.

**Design note (not in the spec verbatim, filling a gap):** compare mode needs a measure (agg + field) to aggregate over time buckets, but `chart.tsx` has no `agg` prop today. Rather than adding a redundant one, this reuses the existing `valueField` prop (currently only consumed by pie/gauge) as the measure field: `agg = valueField ? "sum" : "count"` — mirrors `indicator.tsx`'s own `agg`/`field` convention exactly and keeps the new-props surface to just `compareEnabled`/`comparePeriod`, as the spec states.

- [ ] **Step 1: Write the failing `chartOption.test.ts` additions**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
import { buildCompareOption } from "./chartOption";

test("buildCompareOption renders two aligned series on a relative offset axis", () => {
  const current = [{ bucket: "2026-01-01 00:00:00", value: 10 }, { bucket: "2026-01-02 00:00:00", value: 12 }];
  const reference = [{ bucket: "2025-01-01 00:00:00", value: 8 }, { bucket: "2025-01-02 00:00:00", value: 9 }];
  const opt = buildCompareOption({ chartType: "line" }, current, reference, "day");
  expect(series(opt)).toHaveLength(2);
  expect(series(opt).map((s) => s.name)).toEqual(["Période courante", "Référence"]);
  expect(series(opt)[0].data).toEqual([10, 12]);
  expect(series(opt)[1].data).toEqual([8, 9]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Jour 1", "Jour 2"]);
  expect(series(opt)[1].lineStyle?.type).toBe("dashed");
});

test("buildCompareOption labels the offset axis by week/month depending on bucket", () => {
  const weekOpt = buildCompareOption({ chartType: "line" }, [{ bucket: "w", value: 1 }], [], "week");
  expect((weekOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Semaine 1"]);
  const monthOpt = buildCompareOption({ chartType: "area" }, [{ bucket: "m", value: 1 }], [], "month");
  expect((monthOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Mois 1"]);
});

test("buildCompareOption applies the yAxisUnit/yAxisFormat formatter like buildOption", () => {
  const opt = buildCompareOption({ chartType: "line", yAxisUnit: "kg" }, [{ bucket: "d", value: 1 }], [], "day");
  const formatter = (opt as { yAxis?: { axisLabel?: { formatter?: (v: unknown) => string } } }).yAxis?.axisLabel?.formatter;
  expect(formatter?.(5)).toBe("5 kg");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "buildCompareOption"`
Expected: FAIL — `buildCompareOption` is not exported from `./chartOption`.

- [ ] **Step 3: Implement `buildCompareOption` in `shell/src/builder/widgets/chartOption.ts`**

Add near the bottom of the file, before `finalize` (which it reuses), and add the import at the top:

```ts
import type { BucketGranularity } from "../../lib/comparisonWindow";
```

```ts
export type ComparePoint = { bucket: string; value: number };

function offsetLabel(bucket: BucketGranularity, index: number): string {
  const unit = bucket === "day" ? "Jour" : bucket === "week" ? "Semaine" : "Mois";
  return `${unit} ${index + 1}`;
}

// Compare-periods mode (SP-14e §5): two line series on a relative offset
// axis (index-based, not calendar dates) so the current window and its
// reference period overlay regardless of their absolute dates. Independent
// of buildOption — when compare mode is off, buildOption is untouched.
export function buildCompareOption(
  props: ChartProps, current: ComparePoint[], reference: ComparePoint[], bucket: BucketGranularity,
): EChartsOption {
  const length = Math.max(current.length, reference.length);
  const categories = Array.from({ length }, (_, i) => offsetLabel(bucket, i));
  const fmt = valueFormatter(props);
  const yAxis: Record<string, unknown> = { type: props.yAxisType ?? "value" };
  if (fmt) yAxis.axisLabel = { formatter: fmt };

  const built: Record<string, unknown> = {
    tooltip: { trigger: "axis" },
    legend: { show: props.legend ?? true },
    xAxis: { type: "category", data: categories },
    yAxis,
    series: [
      { type: "line", name: "Période courante", data: current.map((p) => p.value) },
      { type: "line", name: "Référence", data: reference.map((p) => p.value), lineStyle: { type: "dashed" }, itemStyle: { opacity: 0.6 } },
    ],
  };
  if (props.title) built.title = { text: props.title };
  return finalize(props, built);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS (all tests in the file, including the 3 new ones)

- [ ] **Step 5: Write the failing `chart.test.tsx` (full rewrite)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { ActionBus } from "../ActionBus";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { ExplorerProvider } from "../ExplorerContext";

vi.mock("../EChart", () => ({
  EChart: ({ option, onClick }: { option: { series?: unknown }; onClick?: (params: { name?: string }) => void }) => {
    const s = option.series;
    const n = Array.isArray(s) ? s.length : s ? 1 : 0;
    return (
      <div data-testid="echart" data-series={n} onClick={() => onClick?.({ name: "Nord" })} />
    );
  },
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });
const wide = state({ records: [
  { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
  { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 7 } },
] });

function renderChart(
  props: Record<string, unknown>, ctx: Partial<WidgetContext>,
  client: Partial<ItemClient> = {}, timeRange: { from: string; to: string } | null = null,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const fullClient = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn(), ...client } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={fullClient}>
        <AnalyticsContextProvider interactions="auto" initialState={{ timeRange, extent: null, crossFilter: {} }}>
          <Chart props={props} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client: fullClient };
}

test("renders an ECharts panel with one series per column", async () => {
  renderChart({ chartType: "bar", categoryField: "region" }, { data: wide });
  const el = await screen.findByTestId("echart");
  expect(el).toHaveAttribute("data-series", "2");
});

test("shows loading, error and empty states", () => {
  const { rerender } = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ItemClientProvider client={{ queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient}>
        {(() => { const Chart = getWidget("chart")!.Component; return <Chart props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />; })()}
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  const Chart = getWidget("chart")!.Component;
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Chart props={{}} ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/erreur/i)).toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Chart props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("PropsPanel edits the chart type and exposes the advanced JSON escape hatch", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Option ECharts avancée (JSON)")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Type de graphique"), "line");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ chartType: "line" }));
});

test("PropsPanel shows the compare-periods toggle only for line/area chart types", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.queryByLabelText("Comparer les périodes")).not.toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "line" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Comparer les périodes")).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Comparer les périodes"));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ compareEnabled: true }));
});

test("loading and empty states use the theme muted token", () => {
  renderChart({}, { data: state({ loading: true }) });
  expect(screen.getByText(/chargement/i)).toHaveClass("text-[var(--gs-color-muted)]");
});

test("declares the categorySelected event", () => {
  expect(getWidget("chart")!.events).toEqual(["categorySelected"]);
});

test("clicking a category always emits categorySelected on the bus", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "chart1", event: "categorySelected", to: "sink", action: "log" }]);
  renderChart({ categoryField: "region", chartType: "bar" }, { data: wide, bus, widgetId: "chart1" });
  await userEvent.click(await screen.findByTestId("echart"));
  expect(handler).toHaveBeenCalledWith({ region: "Nord" });
});

test("sets the cross-filter when interactions is auto and the source is dataset-bound", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart props={{ categoryField: "region", chartType: "bar", dataSourceId: "src-1" }}
            ctx={{ mode: "runtime", data: { ...wide, datasetId: "dataset-1" } } as WidgetContext} />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("does not set a cross-filter when the source has no datasetId (manual wiring only)", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide } as WidgetContext} />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});

test("shows an explorer menu when the widget is bound to a dataset and interactions are auto", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <ExplorerProvider enabled>
          <Chart
            props={{ chartType: "bar", categoryField: "region", dataSourceId: "src1" }}
            ctx={{ mode: "runtime", data: { ...wide, datasetId: "ds1" } } as WidgetContext}
          />
        </ExplorerProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("compareEnabled has no visible effect without an active time range (falls back to the single-series chart)", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const { client } = renderChart(
    { chartType: "line", categoryField: "region", compareEnabled: true },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig },
  );
  const el = await screen.findByTestId("echart");
  expect(el).toHaveAttribute("data-series", "2"); // normal per-column series, unaffected
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("compareEnabled builds a 2-series compare option once timeRange + timeField are both active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  // Content-aware, not call-order-aware — same reasoning as the indicator's
  // delta test: currentQuery/referenceQuery are independent useQuery calls,
  // so key the response off the request's date__gte instead of call order.
  const queryDataSource = vi.fn().mockImplementation((source: { query: Record<string, unknown> }) => {
    if (source.query.date__gte === "2026-01-01") {
      return Promise.resolve([
        { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 5 } },
        { id: "2026-01-02 00:00:00", properties: { date: "2026-01-02 00:00:00", value: 7 } },
      ]);
    }
    return Promise.resolve([{ id: "2025-12-31 00:00:00", properties: { date: "2025-12-31 00:00:00", value: 3 } }]);
  });
  renderChart(
    { chartType: "line", categoryField: "region", compareEnabled: true, comparePeriod: "previous" },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig, queryDataSource },
    { from: "2026-01-01", to: "2026-01-02" },
  );
  const el = await screen.findByTestId("echart");
  await waitFor(() => expect(el).toHaveAttribute("data-series", "2"));
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx`
Expected: FAIL — no `PropsPanel` toggle for compare, and existing Component tests likely also fail because `chart.tsx` doesn't yet call `useItemClient`/`useQuery` at all (the previous file rendered fine without providers; this rewritten test suite exercises the not-yet-implemented gating), plus the two new compare-mode tests fail outright.

- [ ] **Step 7: Implement compare mode in `shell/src/builder/widgets/chart.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useAnalyticsContext, useSetCrossFilter } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import { buildOption, buildCompareOption, type ChartProps, type ComparePoint } from "./chartOption";
import { ExplorerMenu } from "./ExplorerMenu";
import type { DataRecord, DatasetConfig } from "../../api/types";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

const CHART_TYPES: [string, string][] = [
  ["bar", "Barres"], ["line", "Lignes"], ["area", "Aires"], ["scatter", "Nuage de points"],
  ["pie", "Camembert"], ["doughnut", "Anneau"], ["radar", "Radar"], ["heatmap", "Carte de chaleur"],
  ["gauge", "Jauge"], ["boxplot", "Boîte à moustaches"],
];
const AXIS_TYPES: [string, string][] = [
  ["category", "Catégorie"], ["value", "Valeur"], ["time", "Temps"], ["log", "Logarithmique"],
];

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function toComparePoints(records: DataRecord[] | undefined, timeField: string): ComparePoint[] {
  return (records ?? []).map((r) => ({ bucket: String(r.properties[timeField] ?? ""), value: Number(r.properties.value ?? 0) }));
}

export function registerChartWidget(): void {
  registerWidget({
    type: "chart",
    label: "Graphique",
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous",
    },
    defaultSize: { w: 6, h: 4 },
    events: ["categorySelected"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      const chartType = String(props.chartType ?? "bar");
      const showCompare = chartType === "line" || chartType === "area";
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })} />
          <label className={labelCls}>Type de graphique
            <select aria-label="Type de graphique" className={inputCls}
              value={chartType} onChange={(e) => set({ chartType: e.target.value })}>
              {CHART_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Champ catégorie / X
            <input aria-label="Champ catégorie" className={inputCls}
              value={String(props.categoryField ?? "")} onChange={(e) => set({ categoryField: e.target.value })} />
          </label>
          <label className={labelCls}>Champ valeur (camembert / jauge / comparaison)
            <input aria-label="Champ valeur" className={inputCls}
              value={String(props.valueField ?? "")} onChange={(e) => set({ valueField: e.target.value })} />
          </label>
          {showCompare && (
            <>
              <label className="flex items-center gap-2">
                <input type="checkbox" aria-label="Comparer les périodes"
                  checked={Boolean(props.compareEnabled)} onChange={(e) => set({ compareEnabled: e.target.checked })} />
                Comparer les périodes
              </label>
              <label className={labelCls}>Période de référence
                <select aria-label="Période de référence" className={inputCls}
                  value={String(props.comparePeriod ?? "previous")} onChange={(e) => set({ comparePeriod: e.target.value })}>
                  <option value="previous">Période précédente</option>
                  <option value="sameLastYear">Même période l'an dernier</option>
                </select>
              </label>
            </>
          )}
          <label className={labelCls}>Type d'axe X
            <select aria-label="Type d'axe X" className={inputCls}
              value={String(props.xAxisType ?? "category")} onChange={(e) => set({ xAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Type d'axe Y
            <select aria-label="Type d'axe Y" className={inputCls}
              value={String(props.yAxisType ?? "value")} onChange={(e) => set({ yAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Unité de l'axe Y
            <input aria-label="Unité de l'axe Y" className={inputCls}
              value={String(props.yAxisUnit ?? "")} onChange={(e) => set({ yAxisUnit: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du graphique" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Empiler les séries"
              checked={Boolean(props.stack)} onChange={(e) => set({ stack: e.target.checked })} />
            Empiler les séries
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Afficher la légende"
              checked={props.legend !== false} onChange={(e) => set({ legend: e.target.checked })} />
            Afficher la légende
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Activer le zoom"
              checked={Boolean(props.zoom)} onChange={(e) => set({ zoom: e.target.checked })} />
            Activer le zoom
          </label>
          <label className={labelCls}>Option ECharts avancée (JSON)
            <textarea aria-label="Option ECharts avancée (JSON)"
              className="rounded-md border border-slate-300 p-2 font-mono text-xs" rows={4}
              placeholder='{"color":["#f00"]}'
              value={String(props.advancedOption ?? "")} onChange={(e) => set({ advancedOption: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const setCrossFilter = useSetCrossFilter();
      const analyticsCtx = useAnalyticsContext();
      const client = useItemClient();
      const data = ctx.data;
      const datasetId = data?.datasetId;
      const chartType = String(props.chartType ?? "bar");
      const originSourceId = String(props.dataSourceId ?? "");
      const compareRequested = Boolean(props.compareEnabled) && (chartType === "line" || chartType === "area");
      const comparePeriod = (props.comparePeriod as ReferenceMode | undefined) ?? "previous";
      const valueField = String(props.valueField ?? "");
      const agg = valueField ? "sum" : "count";

      const datasetQuery = useQuery({
        queryKey: ["dataset", datasetId],
        queryFn: () => client.getDatasetConfig(datasetId as string),
        enabled: Boolean(compareRequested && datasetId),
      });
      const dataset = datasetQuery.data;
      const timeRange = analyticsCtx.timeRange;
      const compareActive = compareRequested && Boolean(dataset?.timeField) && Boolean(timeRange);
      const bucket = compareActive && timeRange ? bucketFor(timeRange) : "day";
      const referenceRange = compareActive && timeRange ? referenceWindow(timeRange, comparePeriod) : null;

      const currentQuery = useQuery({
        queryKey: ["chart-compare-current", datasetId, timeRange, bucket, agg, valueField],
        queryFn: () => client.queryDataSource(
          windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          }),
        ),
        enabled: Boolean(compareActive),
      });
      const referenceQuery = useQuery({
        queryKey: ["chart-compare-reference", datasetId, referenceRange, bucket, agg, valueField],
        queryFn: () => client.queryDataSource(
          windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange as { from: string; to: string }, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          }),
        ),
        enabled: Boolean(compareActive && referenceRange),
      });

      if (compareActive) {
        if (currentQuery.isLoading || referenceQuery.isLoading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
        if (currentQuery.isError || referenceQuery.isError) return <p className="text-xs text-red-600">Erreur de données</p>;
        const timeField = (dataset as DatasetConfig).timeField as string;
        const option = buildCompareOption(
          props as unknown as ChartProps, toComparePoints(currentQuery.data, timeField), toComparePoints(referenceQuery.data, timeField), bucket,
        );
        return (
          <div className="relative h-full">
            <ExplorerMenu datasetId={datasetId} dataSourceId={originSourceId} />
            <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
              <EChart option={option} />
            </Suspense>
          </div>
        );
      }

      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      const categoryField = String(props.categoryField ?? "");
      function handleClick(params: { name?: string }) {
        if (!categoryField) return;
        const value = params.name != null ? String(params.name) : "";
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [categoryField]: value });
        if (data?.datasetId) setCrossFilter(data.datasetId, categoryField, value, originSourceId);
      }
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={originSourceId} />
          <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
            <EChart option={option} onClick={handleClick} />
          </Suspense>
        </div>
      );
    },
  });
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/chartOption.test.ts`
Expected: PASS (all tests)

- [ ] **Step 9: Run the full shell unit suite for non-regression**

Run: `cd shell && npm run test`
Expected: PASS — all files green, in particular `AppRenderer.test.tsx` and anything else rendering `chart`/`indicator` widgets.

- [ ] **Step 10: Typecheck**

Run: `cd shell && npm run build`
Expected: PASS — `tsc --noEmit` clean, then `vite build` succeeds.

- [ ] **Step 11: Commit**

```bash
git add shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chart gets a compare-periods mode for line/area (2 aligned series on a relative axis)"
```

---

