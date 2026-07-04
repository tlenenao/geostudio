import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

test("indicator counts records by default", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } },
  ] }) } as WidgetContext;
  render(<Ind props={{ dataSourceId: "d", label: "Total", agg: "count" }} ctx={ctx} />);
  expect(screen.getByText("Total")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});

test("indicator sums a field when agg=sum", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } },
  ] }) } as WidgetContext;
  render(<Ind props={{ dataSourceId: "d", agg: "sum", field: "pop" }} ctx={ctx} />);
  expect(screen.getByText("40")).toBeInTheDocument();
});

test("indicator uses the theme text/muted tokens", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(<Ind props={{ label: "Total" }} ctx={ctx} />);
  expect(screen.getByText("1")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByText("Total")).toHaveClass("text-[var(--gs-color-muted)]");
});
