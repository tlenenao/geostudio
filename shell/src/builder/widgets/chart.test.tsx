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
