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
  EChart: ({
    option,
    onClick,
  }: {
    option: { series?: unknown };
    onClick?: (params: { name?: string }) => void;
  }) => {
    const s = option.series;
    const n = Array.isArray(s) ? s.length : s ? 1 : 0;
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- doublure de test pour EChart (vi.mock), jamais rendue à un utilisateur réel ; le composant réel gère ses propres clics via echarts.
    return <div data-testid="echart" data-series={n} onClick={() => onClick?.({ name: "Nord" })} />;
  },
}));

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({
  loading: false,
  error: false,
  records: [],
  ...over,
});
const wide = state({
  records: [
    { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
    { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 7 } },
  ],
});

function renderChart(
  props: Record<string, unknown>,
  ctx: Partial<WidgetContext>,
  client: Partial<ItemClient> = {},
  timeRange: { from: string; to: string } | null = null,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const fullClient = {
    queryDataSource: vi.fn(),
    getDatasetConfig: vi.fn(),
    ...client,
  } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={fullClient}>
        <AnalyticsContextProvider
          interactions="auto"
          initialState={{ timeRange, extent: null, crossFilter: {} }}
        >
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
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ItemClientProvider
        client={{ queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient}
      >
        {(() => {
          const Chart = getWidget("chart")!.Component;
          return (
            <Chart
              props={{}}
              ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext}
            />
          );
        })()}
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
        <Chart
          props={{}}
          ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext}
        />
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
  bus.configure([
    { id: "m", from: "chart1", event: "categorySelected", to: "sink", action: "log" },
  ]);
  renderChart(
    { categoryField: "region", chartType: "bar" },
    { data: wide, bus, widgetId: "chart1" },
  );
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
          <Chart
            props={{ categoryField: "region", chartType: "bar", dataSourceId: "src-1" }}
            ctx={{ mode: "runtime", data: { ...wide, datasetId: "dataset-1" } } as WidgetContext}
          />
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
          <Chart
            props={{ categoryField: "region", chartType: "bar" }}
            ctx={{ mode: "runtime", data: wide } as WidgetContext}
          />
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
  const getDatasetConfig = vi.fn().mockResolvedValue({
    source: "collection",
    collectionId: "events",
    columns: {},
    timeField: "date",
    reactsToExtent: false,
  });
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
  const getDatasetConfig = vi.fn().mockResolvedValue({
    source: "collection",
    collectionId: "events",
    columns: {},
    timeField: "date",
    reactsToExtent: false,
  });
  // Content-aware, not call-order-aware — same reasoning as the indicator's
  // delta test: currentQuery/referenceQuery are independent useQuery calls,
  // so key the response off the request's date__gte instead of call order.
  const queryDataSource = vi
    .fn()
    .mockImplementation((source: { query: Record<string, unknown> }) => {
      if (source.query.date__gte === "2026-01-01") {
        return Promise.resolve([
          { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 5 } },
          { id: "2026-01-02 00:00:00", properties: { date: "2026-01-02 00:00:00", value: 7 } },
        ]);
      }
      return Promise.resolve([
        { id: "2025-12-31 00:00:00", properties: { date: "2025-12-31 00:00:00", value: 3 } },
      ]);
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

test("two chart widgets in compare mode on the same dataset and metric do not collide on cache when a cross-filter singles one of them out", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({
    source: "collection",
    collectionId: "events",
    columns: {},
    timeField: "date",
    reactsToExtent: false,
  });
  // Content-aware, not call-order-aware — same reasoning as the "builds a
  // 2-series compare option" test above: key the response off date__gte.
  const queryDataSource = vi
    .fn()
    .mockImplementation((source: { query: Record<string, unknown> }) => {
      if (source.query.date__gte === "2026-01-01") {
        return Promise.resolve([
          { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 5 } },
        ]);
      }
      return Promise.resolve([
        { id: "2025-12-31 00:00:00", properties: { date: "2025-12-31 00:00:00", value: 3 } },
      ]);
    });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource, getDatasetConfig } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  const widgetData = { ...wide, datasetId: "ds-1" };
  const compareProps = {
    chartType: "line",
    categoryField: "region",
    compareEnabled: true,
    comparePeriod: "previous",
  };

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider
          interactions="auto"
          initialState={{
            timeRange: { from: "2026-01-01", to: "2026-01-02" },
            extent: null,
            crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-A" } },
          }}
        >
          <Chart
            props={{ ...compareProps, dataSourceId: "src-A" }}
            ctx={{ mode: "runtime", data: widgetData } as WidgetContext}
          />
          <Chart
            props={{ ...compareProps, dataSourceId: "src-B" }}
            ctx={{ mode: "runtime", data: widgetData } as WidgetContext}
          />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => {
    const currentCalls = queryDataSource.mock.calls
      .map(([source]) => source as { query: Record<string, unknown> })
      .filter((source) => source.query.date__gte === "2026-01-01");
    // src-A originated the cross-filter so derivePatch excludes it from its own
    // currentQuery (region undefined); src-B did not, so its currentQuery carries
    // region=Nord. Under the old cache key ([label, datasetId, timeRange, bucket,
    // agg, valueField], no source id / resolved query) both widgets' currentQuery
    // calls would be identical and TanStack Query would only invoke queryFn once
    // for the shared entry — so at most one of these two conditions could ever hold.
    expect(currentCalls.some((source) => source.query.region === "Nord")).toBe(true);
    expect(currentCalls.some((source) => source.query.region === undefined)).toBe(true);
  });
});

test("PropsPanel offers the 5 new chart types", () => {
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={vi.fn()} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const select = screen.getByLabelText("Type de graphique") as HTMLSelectElement;
  const values = Array.from(select.options).map((o) => o.value);
  expect(values).toEqual(
    expect.arrayContaining(["sankey", "treemap", "sunburst", "funnel", "histogram"]),
  );
});

test("PropsPanel shows source/target encodings for sankey, hides categoryField/valueField", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "sankey" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Champ source")).toBeInTheDocument();
  expect(screen.getByLabelText("Champ cible")).toBeInTheDocument();
  expect(screen.queryByLabelText("Champ catégorie")).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Champ source"), "o");
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ encodings: { source: "o" } }),
  );
});

test("PropsPanel lets the author add up to 3 hierarchy levels for treemap/sunburst", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel
          props={{ chartType: "treemap", encodings: { levels: ["region"] } }}
          dataSources={[]}
          onChange={onChange}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Niveau 1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "+ Niveau" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ encodings: { levels: ["region", ""] } }),
  );
});

test("handleClick uses resolveClickFilter — treemap click cross-filters on the deepest level", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  const treeRecords = state({
    records: [{ id: "1", properties: { region: "Nord", value: 1 } }],
    datasetId: "ds-1",
  });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart
            props={{
              chartType: "treemap",
              encodings: { levels: ["region"] },
              dataSourceId: "src-1",
            }}
            ctx={{ mode: "runtime", data: treeRecords } as WidgetContext}
          />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  // The shared EChart mock (top of file) fires onClick({ name: "Nord" }) — no
  // treePathInfo, so resolveClickFilter falls back to depth 0 → levels[0].
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});
