### Task 4: `indicator` — delta vs reference, sparkline, CEL threshold pastille

**Files:**
- Modify: `shell/src/builder/widgets/indicator.tsx`
- Modify (full rewrite): `shell/src/builder/widgets/indicator.test.tsx`

**Interfaces:**
- Consumes: `windowedStatisticsSource`, `referenceWindow`, `bucketFor`, `type ReferenceMode` (Task 3, `../../lib/comparisonWindow`); `useAnalyticsContext` (`../AnalyticsContext`); `useItemClient` (`../../api/ItemClientProvider`); `evaluateExpression` (`../expr`); `EChart` (`../EChart`, lazy).
- Produces: no new exports besides the widget registration — this is a leaf widget.

**Design note (not in the spec verbatim, filling a gap):** the enriched path fetches the dataset's `DatasetConfig` itself via `useQuery(["dataset", datasetId], () => client.getDatasetConfig(datasetId))` — the same query key `DataContext`/`ExplorerDrawer` already use, so when this indicator's own `dataSourceId` is dataset-bound, React Query dedups the fetch against the one `DataContext` already made for the widget's flat value; no *extra* network round-trip in the common case. This dataset lookup is a prerequisite (we need `dataset.timeField` to know if the enriched path is even eligible) and is **not** one of the "up to 3 additional requests" the spec's risk table counts — those are the value/reference/sparkline `statistics` queries, each independently gated.

- [ ] **Step 1: Write the failing tests (full rewrite of `indicator.test.tsx`)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ExplorerProvider } from "../ExplorerContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider } from "../AnalyticsContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

vi.mock("../EChart", () => ({
  EChart: ({ option }: { option: { series?: unknown } }) => {
    const s = option.series;
    const first = Array.isArray(s) ? s[0] : s;
    const data = (first as { data?: unknown[] } | undefined)?.data ?? [];
    return <div data-testid="kpi-sparkline" data-points={data.length} />;
  },
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

function renderIndicator(
  props: Record<string, unknown>, ctx: Partial<WidgetContext>,
  client: Partial<ItemClient> = {}, timeRange: { from: string; to: string } | null = null,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const fullClient = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn(), ...client } as unknown as ItemClient;
  const Ind = getWidget("indicator")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={fullClient}>
        <AnalyticsContextProvider interactions="auto" initialState={{ timeRange, extent: null, crossFilter: {} }}>
          <Ind props={props} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client: fullClient };
}

test("indicator counts records by default (unchanged, no new props)", () => {
  const { client } = renderIndicator(
    { dataSourceId: "d", label: "Total", agg: "count" },
    { data: state({ records: [{ id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } }] }) },
  );
  expect(screen.getByText("Total")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(client.getDatasetConfig).not.toHaveBeenCalled();
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("indicator sums a field when agg=sum (unchanged, no new props)", () => {
  renderIndicator(
    { dataSourceId: "d", agg: "sum", field: "pop" },
    { data: state({ records: [{ id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } }] }) },
  );
  expect(screen.getByText("40")).toBeInTheDocument();
});

test("indicator uses the theme text/muted tokens", () => {
  renderIndicator({ label: "Total" }, { data: state({ records: [{ id: 1, properties: {} }] }) });
  expect(screen.getByText("1")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByText("Total")).toHaveClass("text-[var(--gs-color-muted)]");
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Ind = getWidget("indicator")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <ExplorerProvider enabled>
          <Ind props={{ dataSourceId: "src1", label: "Total" }}
            ctx={{ mode: "runtime", data: state({ datasetId: "ds1", records: [{ id: 1, properties: { pop: 10 } }] }) } as WidgetContext} />
        </ExplorerProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("does not show a delta badge without an active time range even if referencePeriod is set", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const { client } = renderIndicator(
    { dataSourceId: "src-1", label: "Total", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [{ id: 1, properties: {} }] }) },
    { getDatasetConfig },
  );
  expect(screen.getByText("1")).toBeInTheDocument();
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
  expect(screen.queryByText(/vs période/)).not.toBeInTheDocument();
});

test("does not show a delta badge when the dataset has no timeField, even with an active time range", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: null, reactsToExtent: false });
  const { client } = renderIndicator(
    { dataSourceId: "src-1", label: "Total", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [{ id: 1, properties: {} }] }) },
    { getDatasetConfig }, { from: "2026-01-01", to: "2026-01-31" },
  );
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
  expect(screen.queryByText(/vs période/)).not.toBeInTheDocument();
});

test("shows a delta badge computed from the server value/reference when referencePeriod + timeRange + timeField are all active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  // Content-aware, not call-order-aware: valueQuery and referenceQuery are
  // two independent useQuery calls in the same render — TanStack Query does
  // not guarantee which one's queryFn actually fires first, so the mock
  // must key its response off the request itself (window.from via
  // date__gte), not off invocation order.
  const queryDataSource = vi.fn().mockImplementation((source: { query: Record<string, unknown> }) => {
    if (source.query.date__gte === "2026-01-01") return Promise.resolve([{ id: "Total", properties: { value: 120 } }]);
    return Promise.resolve([{ id: "Total", properties: { value: 100 } }]);
  });
  renderIndicator(
    { dataSourceId: "src-1", label: "Total", agg: "count", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [] }) },
    { getDatasetConfig, queryDataSource }, { from: "2026-01-01", to: "2026-01-31" },
  );
  expect(await screen.findByText("120")).toBeInTheDocument();
  expect(await screen.findByText(/\+20 % vs période précédente/)).toBeInTheDocument();
});

test("shows a sparkline mini-chart when sparkline is true and time context is active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 3 } },
    { id: "2026-01-02 00:00:00", properties: { date: "2026-01-02 00:00:00", value: 5 } },
  ]);
  renderIndicator(
    { dataSourceId: "src-1", label: "Total", sparkline: true },
    { data: state({ datasetId: "ds-1", records: [] }) },
    { getDatasetConfig, queryDataSource }, { from: "2026-01-01", to: "2026-01-02" },
  );
  const sparkline = await screen.findByTestId("kpi-sparkline");
  expect(sparkline).toHaveAttribute("data-points", "2");
});

test("shows a critical pastille when criticalWhen evaluates truthy against the displayed value", async () => {
  renderIndicator(
    { label: "Total", agg: "count", criticalWhen: "record.value > 1" },
    { variables: {}, user: { name: "u" }, data: state({ records: [{ id: 1, properties: {} }, { id: 2, properties: {} }] }) },
  );
  expect(await screen.findByLabelText("Seuil critique atteint")).toBeInTheDocument();
});

test("shows a warning pastille when only warningWhen evaluates truthy", async () => {
  renderIndicator(
    { label: "Total", agg: "count", warningWhen: "record.value > 1", criticalWhen: "record.value > 100" },
    { data: state({ records: [{ id: 1, properties: {} }, { id: 2, properties: {} }] }) },
  );
  expect(await screen.findByLabelText("Seuil d'alerte atteint")).toBeInTheDocument();
  expect(screen.queryByLabelText("Seuil critique atteint")).not.toBeInTheDocument();
});

test("shows no pastille when threshold expressions are absent", () => {
  renderIndicator({ label: "Total", agg: "count" }, { data: state({ records: [{ id: 1, properties: {} }] }) });
  expect(screen.queryByLabelText("Seuil critique atteint")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Seuil d'alerte atteint")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx`
Expected: FAIL — `indicator.tsx` doesn't accept/use `referencePeriod`/`sparkline`/`criticalWhen`/`warningWhen`, and rendering without `QueryClientProvider`/`ItemClientProvider` in the old file would previously have worked, but the new tests import providers expecting the component to actually call `useQuery`/`useItemClient` — currently a no-op, so delta/sparkline/pastille assertions fail.

- [ ] **Step 3: Implement `shell/src/builder/widgets/indicator.tsx` (full rewrite)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { ExplorerMenu } from "./ExplorerMenu";
import { useAnalyticsContext } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { evaluateExpression } from "../expr";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import type { DatasetConfig } from "../../api/types";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

type KpiComparison = {
  active: boolean;
  loading: boolean;
  value: number | null;
  delta: number | null;
  deltaPct: number | null;
  sparklinePoints: { bucket: string; value: number }[];
};

// Shared mechanic (Task 3, spec §3): fetches the dataset config (needed to
// know `timeField`), then — only once referencePeriod/sparkline is actually
// requested AND ctx.timeRange + dataset.timeField are both active — issues
// up to 3 independent `statistics` queries (current value, reference value,
// bucketed sparkline series). Each `useQuery` call is unconditional (Rules
// of Hooks); `enabled` gates the network request, not the hook call.
function useKpiComparison(
  datasetId: string | undefined,
  originSourceId: string,
  referencePeriod: ReferenceMode | undefined,
  sparklineEnabled: boolean,
  agg: string,
  field: string,
): KpiComparison {
  const client = useItemClient();
  const analyticsCtx = useAnalyticsContext();
  const wantsComparison = Boolean(referencePeriod || sparklineEnabled);

  const datasetQuery = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => client.getDatasetConfig(datasetId as string),
    enabled: Boolean(wantsComparison && datasetId),
  });
  const dataset = datasetQuery.data;
  const timeRange = analyticsCtx.timeRange;
  const active = wantsComparison && Boolean(dataset?.timeField) && Boolean(timeRange);

  const valueQuery = useQuery({
    queryKey: ["kpi-value", datasetId, timeRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod),
  });

  const referenceRange = active && referencePeriod ? referenceWindow(timeRange as { from: string; to: string }, referencePeriod) : null;
  const referenceQuery = useQuery({
    queryKey: ["kpi-reference", datasetId, referenceRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod && referenceRange),
  });

  const bucket = active && timeRange ? bucketFor(timeRange) : "day";
  const sparklineQuery = useQuery({
    queryKey: ["kpi-sparkline", datasetId, timeRange, bucket, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, {
        groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: field || undefined,
      }),
    ),
    enabled: Boolean(active && sparklineEnabled),
  });

  const value = referencePeriod && valueQuery.data ? Number(valueQuery.data[0]?.properties.value ?? 0) : null;
  const reference = referencePeriod && referenceQuery.data ? Number(referenceQuery.data[0]?.properties.value ?? 0) : null;
  const delta = value !== null && reference !== null ? value - reference : null;
  const deltaPct = delta !== null && reference !== null && reference !== 0 ? delta / reference : null;
  const sparklinePoints = sparklineEnabled && dataset?.timeField && sparklineQuery.data
    ? sparklineQuery.data.map((r) => ({ bucket: String(r.properties[dataset.timeField as string] ?? ""), value: Number(r.properties.value ?? 0) }))
    : [];

  const loading = active && (
    (Boolean(referencePeriod) && (valueQuery.isLoading || referenceQuery.isLoading)) ||
    (sparklineEnabled && sparklineQuery.isLoading)
  );

  return { active, loading, value, delta, deltaPct, sparklinePoints };
}

function deltaLabel(delta: number, deltaPct: number | null, mode: ReferenceMode): string {
  const refLabel = mode === "previous" ? "période précédente" : "même période l'an dernier";
  const sign = delta >= 0 ? "+" : "";
  const magnitude = deltaPct !== null ? `${sign}${Math.round(deltaPct * 100)} %` : `${sign}${delta}`;
  return `${magnitude} vs ${refLabel}`;
}

function thresholdLevel(
  criticalWhen: string, warningWhen: string,
  exprCtx: { vars: Record<string, unknown>; user: { name: string }; record: Record<string, unknown> },
): "critical" | "warning" | null {
  if (criticalWhen && evaluateExpression(criticalWhen, exprCtx)) return "critical";
  if (warningWhen && evaluateExpression(warningWhen, exprCtx)) return "warning";
  return null;
}

function sparklineOption(points: { bucket: string; value: number }[]): EChartsOption {
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: "category", show: false, data: points.map((p) => p.bucket) },
    yAxis: { type: "value", show: false },
    series: [{ type: "line", data: points.map((p) => p.value), showSymbol: false, lineStyle: { width: 1.5 } }],
  } as EChartsOption;
}

export function registerIndicatorWidget(): void {
  registerWidget({
    type: "indicator",
    label: "Indicateur",
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé de l'indicateur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Agrégation
          <select aria-label="Agrégation" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.agg ?? "count")} onChange={(e) => onChange({ ...props, agg: e.target.value })}>
            <option value="count">Nombre</option>
            <option value="sum">Somme</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">Champ (pour la somme)
          <input aria-label="Champ agrégé" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Comparer à
          <select aria-label="Comparer à" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.referencePeriod ?? "")}
            onChange={(e) => onChange({ ...props, referencePeriod: e.target.value || undefined })}>
            <option value="">Aucune</option>
            <option value="previous">Période précédente</option>
            <option value="sameLastYear">Même période l'an dernier</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label="Afficher un sparkline"
            checked={Boolean(props.sparkline)} onChange={(e) => onChange({ ...props, sparkline: e.target.checked })} />
          Afficher un sparkline
        </label>
        <label className="flex flex-col gap-1">Seuil critique (CEL)
          <input aria-label="Seuil critique (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.criticalWhen ?? "")} onChange={(e) => onChange({ ...props, criticalWhen: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Seuil d'alerte (CEL)
          <input aria-label="Seuil d'alerte (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.warningWhen ?? "")} onChange={(e) => onChange({ ...props, warningWhen: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      const agg = String(props.agg ?? "count");
      const field = String(props.field ?? "");
      const referencePeriod = (props.referencePeriod as ReferenceMode | undefined) || undefined;
      const sparklineEnabled = Boolean(props.sparkline);
      const criticalWhen = String(props.criticalWhen ?? "");
      const warningWhen = String(props.warningWhen ?? "");

      const comparison = useKpiComparison(
        data?.datasetId, String(props.dataSourceId ?? ""), referencePeriod, sparklineEnabled, agg, field,
      );

      if (!data || data.loading || comparison.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;

      const flatValue =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      const value = comparison.active && referencePeriod && comparison.value !== null ? comparison.value : flatValue;

      const badge = comparison.active && referencePeriod && comparison.delta !== null
        ? deltaLabel(comparison.delta, comparison.deltaPct, referencePeriod)
        : null;

      const level = criticalWhen || warningWhen
        ? thresholdLevel(criticalWhen, warningWhen, {
            vars: ctx.variables ?? {}, user: ctx.user ?? { name: "" },
            record: { value, delta: comparison.delta, deltaPct: comparison.deltaPct },
          })
        : null;

      return (
        <div className="relative flex h-full flex-col items-center justify-center gap-1">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <div className="flex items-center gap-1">
            <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
            {level && (
              <span
                aria-label={level === "critical" ? "Seuil critique atteint" : "Seuil d'alerte atteint"}
                className={`h-2.5 w-2.5 rounded-full ${level === "critical" ? "bg-red-600" : "bg-orange-500"}`}
              />
            )}
          </div>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
          {badge && <span className="text-xs text-[var(--gs-color-muted)]">{badge}</span>}
          {sparklineEnabled && comparison.active && comparison.sparklinePoints.length > 0 && (
            <div className="h-8 w-full">
              <Suspense fallback={null}>
                <EChart option={sparklineOption(comparison.sparklinePoints)} />
              </Suspense>
            </div>
          )}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full shell unit suite for non-regression**

Run: `cd shell && npm run test`
Expected: PASS — all 61+ files green (in particular anything importing/rendering `indicator`, e.g. `AppRenderer.test.tsx`).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx
git commit -m "feat(shell): indicator gets delta vs reference period, sparkline, CEL threshold pastille"
```

---

