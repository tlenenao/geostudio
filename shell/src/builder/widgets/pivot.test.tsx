// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState =>
  ({ loading: false, error: false, records: [], ...over });

// Small fixture for behavioural tests (config message, cross-filter, explorer
// menu). Deliberately 2 columns, not 1: with a single column a row's total
// would equal its only cell (same rendered text, e.g. both "10") and the
// "never cross-filters from a data cell" test below needs to click a cell
// whose text is unambiguous.
const small = state({
  datasetId: "ds-1",
  records: [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 10 } },
    { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 6 } },
    { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 3 } },
  ],
});

// Fixture with globally-distinct numbers, for rendering assertions where every
// cell/total/grand-total must resolve to a unique element via getByRole.
const distinct = state({
  datasetId: "ds-1",
  records: [
    { id: "1", properties: { region: "Nord", quarter: "Q1", sum_amount: 100 } },
    { id: "2", properties: { region: "Nord", quarter: "Q2", sum_amount: 23 } },
    { id: "3", properties: { region: "Sud", quarter: "Q1", sum_amount: 7 } },
    { id: "4", properties: { region: "Sud", quarter: "Q2", sum_amount: 41 } },
  ],
});

test("registers with a 6x4 default size", () => {
  expect(getWidget("pivot")!.defaultSize).toEqual({ w: 6, h: 4 });
});

test("PropsPanel edits the rows and columns encodings", async () => {
  // DataSourceSelect (rendered by every widget's PropsPanel) calls
  // useItemClient() internally — it throws without an ItemClientProvider
  // ancestor, and useItems (react-query) needs a QueryClientProvider too.
  // Same wrapping as chart.test.tsx's "PropsPanel edits..." test.
  const onChange = vi.fn();
  const Panel = getWidget("pivot")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{}} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByLabelText("Champ lignes"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { rows: "r" } }));
  await userEvent.type(screen.getByLabelText("Champ colonnes"), "c");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { columns: "c" } }));
});

test("shows loading, error and empty states", () => {
  const Pivot = getWidget("pivot")!.Component;
  const { rerender } = render(<Pivot props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<Pivot props={{}} ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext} />);
  expect(screen.getByText(/erreur/i)).toBeInTheDocument();
  rerender(<Pivot props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("shows a configuration message when rows/columns encodings are not set", () => {
  const Pivot = getWidget("pivot")!.Component;
  render(<Pivot props={{}} ctx={{ mode: "runtime", data: small } as WidgetContext} />);
  expect(screen.getByText(/configurez les champs lignes et colonnes/i)).toBeInTheDocument();
});

test("renders row/column headers, cells and totals", () => {
  const Pivot = getWidget("pivot")!.Component;
  render(<Pivot props={{ encodings: { rows: "region", columns: "quarter" } }} ctx={{ mode: "runtime", data: distinct } as WidgetContext} />);
  expect(screen.getByRole("button", { name: "Nord" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Q1" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "100" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "23" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "123" })).toBeInTheDocument(); // row total Nord (100+23)
  expect(screen.getByRole("cell", { name: "107" })).toBeInTheDocument(); // col total Q1 (100+7)
  expect(screen.getByRole("cell", { name: "171" })).toBeInTheDocument(); // grand total
});

test("clicking a row header cross-filters on the rows field", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nord" }));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("clicking a column header cross-filters on the columns field", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["ds-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Q1" }));
  expect(await screen.findByText("cf:quarter=Q1")).toBeInTheDocument();
});

test("never cross-filters from a data cell or the Total row/column", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const Pivot = getWidget("pivot")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
      <Probe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByRole("cell", { name: "10" }));
  // Both the Total column header and the Total row header render the text
  // "Total" — two matches on purpose, click both to prove neither filters.
  for (const totalCell of screen.getAllByText("Total")) {
    await userEvent.click(totalCell);
  }
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Pivot = getWidget("pivot")!.Component;
  render(
    <ExplorerProvider enabled>
      <Pivot props={{ encodings: { rows: "region", columns: "quarter" }, dataSourceId: "src-1" }} ctx={{ mode: "runtime", data: small } as WidgetContext} />
    </ExplorerProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
