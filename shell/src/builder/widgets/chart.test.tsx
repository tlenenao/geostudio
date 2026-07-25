// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { ActionBus } from "../ActionBus";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

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

test("renders an ECharts panel with one series per column", async () => {
  const Chart = getWidget("chart")!.Component;
  render(<Chart props={{ chartType: "bar", categoryField: "region" }} ctx={{ mode: "runtime", data: wide } as WidgetContext} />);
  const el = await screen.findByTestId("echart");
  expect(el).toHaveAttribute("data-series", "2");
});

test("shows loading, error and empty states", () => {
  const Chart = getWidget("chart")!.Component;
  const { rerender } = render(<Chart props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<Chart props={{}} ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext} />);
  expect(screen.getByText(/erreur/i)).toBeInTheDocument();
  rerender(<Chart props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
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

test("loading and empty states use the theme muted token", () => {
  const Chart = getWidget("chart")!.Component;
  const { rerender } = render(<Chart props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toHaveClass("text-[var(--gs-color-muted)]");
  rerender(<Chart props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toHaveClass("text-[var(--gs-color-muted)]");
});

test("declares the categorySelected event", () => {
  expect(getWidget("chart")!.events).toEqual(["categorySelected"]);
});

test("clicking a category always emits categorySelected on the bus", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "chart1", event: "categorySelected", to: "sink", action: "log" }]);
  const Chart = getWidget("chart")!.Component;
  render(<Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide, bus, widgetId: "chart1" } as WidgetContext} />);
  await userEvent.click(await screen.findByTestId("echart"));
  expect(handler).toHaveBeenCalledWith({ region: "Nord" });
});

test("sets the cross-filter when interactions is auto and the source is dataset-bound", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Chart = getWidget("chart")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Chart props={{ categoryField: "region", chartType: "bar", dataSourceId: "src-1" }}
        ctx={{ mode: "runtime", data: { ...wide, datasetId: "dataset-1" } } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("does not set a cross-filter when the source has no datasetId (manual wiring only)", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const Chart = getWidget("chart")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});
