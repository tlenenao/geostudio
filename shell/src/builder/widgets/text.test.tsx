import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

test("text renders verbatim when unbound", () => {
  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Bonjour {{nom}}" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Bonjour {{nom}}")).toBeInTheDocument();
});

test("text interpolates tokens from the bound source's first record", () => {
  const Text = getWidget("text")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [
    { id: 1, properties: { nom: "Nantes", pop: 320000 } },
  ] }) } as WidgetContext;
  render(<Text props={{ dataSourceId: "d", text: "{{nom}} : {{pop}} hab." }} ctx={ctx} />);
  expect(screen.getByText("Nantes : 320000 hab.")).toBeInTheDocument();
});

test("text leaves unknown tokens empty and offers a source binding", () => {
  const Text = getWidget("text")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "X" } }] }) } as WidgetContext;
  render(<Text props={{ dataSourceId: "d", text: "a{{absent}}b" }} ctx={ctx} />);
  expect(screen.getByText("ab")).toBeInTheDocument();

  const Panel = getWidget("text")!.PropsPanel;
  render(<Panel props={{ text: "" }} dataSources={[]} onChange={() => {}} />);
  expect(screen.getByLabelText("Source de données")).toBeInTheDocument();
});

test("text uses the text color theme token", () => {
  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Salut" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Salut")).toHaveClass("text-[var(--gs-color-text)]");
});
