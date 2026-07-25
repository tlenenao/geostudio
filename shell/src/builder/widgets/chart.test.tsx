// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

vi.mock("../EChart", () => ({
  EChart: ({ option }: { option: { series?: unknown } }) => {
    const s = option.series;
    const n = Array.isArray(s) ? s.length : s ? 1 : 0;
    return <div data-testid="echart" data-series={n} />;
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
