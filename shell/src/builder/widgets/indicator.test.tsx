// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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

test("two indicator widgets on the same dataset and metric do not collide on cache when a cross-filter singles one of them out", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const queryDataSource = vi.fn().mockImplementation((source: { query: Record<string, unknown> }) =>
    Promise.resolve([{ id: "Total", properties: { value: source.query.region ? 5 : 20 } }]),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource, getDatasetConfig } as unknown as ItemClient;
  const Ind = getWidget("indicator")!.Component;
  const widgetData = state({ datasetId: "ds-1", records: [] });

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider
          interactions="auto"
          initialState={{
            timeRange: { from: "2026-01-01", to: "2026-01-31" },
            extent: null,
            crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-A" } },
          }}
        >
          <div data-testid="widget-a">
            <Ind props={{ dataSourceId: "src-A", label: "A", agg: "count", referencePeriod: "previous" }}
              ctx={{ mode: "runtime", data: widgetData } as WidgetContext} />
          </div>
          <div data-testid="widget-b">
            <Ind props={{ dataSourceId: "src-B", label: "B", agg: "count", referencePeriod: "previous" }}
              ctx={{ mode: "runtime", data: widgetData } as WidgetContext} />
          </div>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // src-A originated the cross-filter, so derivePatch excludes it for A's own
  // queries (region unfiltered → 20); src-B did not originate it, so B's
  // queries carry region=Nord (→ 5). Before the cache-key fix, both widgets'
  // "kpi-value" queries shared the same key (datasetId/window/agg/field only)
  // and would race to the same cache entry — this proves they're isolated.
  expect(await within(screen.getByTestId("widget-a")).findByText("20")).toBeInTheDocument();
  expect(await within(screen.getByTestId("widget-b")).findByText("5")).toBeInTheDocument();
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
