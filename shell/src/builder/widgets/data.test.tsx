import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { DataProvider, useDataStates } from "../DataContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient, DataSource } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState =>
  ({ loading: false, error: false, records: [], ...over });

test("list renders a record per row using the title field", () => {
  const List = getWidget("list")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "Parc A" } }, { id: 2, properties: { nom: "Parc B" } },
  ] }) } as WidgetContext;
  render(<List props={{ dataSourceId: "d", titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toBeInTheDocument();
  expect(screen.getByText("Parc B")).toBeInTheDocument();
});

test("list shows loading and empty states", () => {
  const List = getWidget("list")!.Component;
  const { rerender } = render(<List props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<List props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("table renders headers from columns and a cell per column", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "A", ville: "X" } },
  ] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom", "ville"] }} ctx={ctx} />);
  expect(screen.getByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "X" })).toBeInTheDocument();
});

test("list emits itemSelected with the clicked record", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "flyTo", handler);
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const List = getWidget("list")!.Component;
  const ctx = {
    mode: "runtime", bus, widgetId: "list1",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  render(<List props={{ titleField: "nom" }} ctx={ctx} />);
  await userEvent.click(screen.getByText("Parc A"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" } });
});

test("list and table declare itemSelected event and setFilter action", () => {
  expect(getWidget("list")!.events).toContain("itemSelected");
  expect(getWidget("list")!.actions).toContain("setFilter");
  expect(getWidget("table")!.events).toContain("itemSelected");
  expect(getWidget("table")!.actions).toContain("setFilter");
});

test("list setFilter action filters its bound source", async () => {
  const queryDataSource = vi.fn()
    .mockResolvedValueOnce([{ id: 1, properties: { nom: "A" } }, { id: 2, properties: { nom: "B" } }])
    .mockResolvedValueOnce([{ id: 1, properties: { nom: "A" } }]);
  const client = { queryDataSource, featuresUrl: vi.fn().mockReturnValue("u") } as unknown as ItemClient;
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "flt", event: "changed", to: "list1", action: "setFilter" }]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sources: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} }];
  const List = getWidget("list")!.Component;

  function Bound() {
    const states = useDataStates();
    const s = states["ds1"];
    return (
      <List
        props={{ dataSourceId: "ds1", titleField: "nom" }}
        ctx={{ mode: "runtime", bus, widgetId: "list1", data: s } as WidgetContext}
      />
    );
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={sources}><Bound /></DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText("A")).toBeInTheDocument());
  await act(async () => {
    bus.emit("flt", "changed", { nom: "A" });
  });
  await waitFor(() => expect(queryDataSource).toHaveBeenLastCalledWith(expect.objectContaining({ query: { nom: "A" } })));
});

test("table sorts rows when a column header is clicked", async () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "B" } },
    { id: 2, properties: { nom: "A" } },
    { id: 3, properties: { nom: "C" } },
  ] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  await userEvent.click(screen.getByRole("button", { name: /nom/ }));
  let cells = screen.getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("A"); // ascending
  await userEvent.click(screen.getByRole("button", { name: /nom/ }));
  cells = screen.getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("C"); // descending
});

test("table paginates with a configured page size", async () => {
  const Table = getWidget("table")!.Component;
  const records = [1, 2, 3].map((n) => ({ id: n, properties: { nom: `N${n}` } }));
  const ctx = { mode: "runtime", data: state({ records }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"], pageSize: 2 }} ctx={ctx} />);
  expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
  expect(screen.queryByText("N3")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByRole("cell", { name: "N3" })).toBeInTheDocument();
});

test("list item uses the theme border/surface/text tokens", () => {
  const List = getWidget("list")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }) } as WidgetContext;
  render(<List props={{ titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toHaveClass(
    "border-[var(--gs-color-border)]",
    "text-[var(--gs-color-text)]",
    "hover:bg-[var(--gs-color-surface)]",
  );
});

test("table cells and headers use the theme border/text tokens", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "A" } }] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  expect(screen.getByRole("cell", { name: "A" })).toHaveClass("border-[var(--gs-color-border)]");
  expect(screen.getByRole("table")).toHaveClass("text-[var(--gs-color-text)]");
});

test("table emits itemSelected with the clicked row", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "flyTo", handler);
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime", bus, widgetId: "table1",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  await userEvent.click(screen.getByRole("cell", { name: "Parc A" }));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" } });
});
