import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";

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
