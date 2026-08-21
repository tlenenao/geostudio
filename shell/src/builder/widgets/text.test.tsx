// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

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

test("text renders verbatim when unbound", () => {
  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Bonjour {{nom}}" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Bonjour {{nom}}")).toBeInTheDocument();
});

test("text interpolates tokens from the bound source's first record", () => {
  const Text = getWidget("text")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "Nantes", pop: 320000 } }] }),
  } as WidgetContext;
  render(<Text props={{ dataSourceId: "d", text: "{{nom}} : {{pop}} hab." }} ctx={ctx} />);
  expect(screen.getByText("Nantes : 320000 hab.")).toBeInTheDocument();
});

test("text leaves unknown tokens empty and offers a source binding", () => {
  const Text = getWidget("text")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "X" } }] }),
  } as WidgetContext;
  render(<Text props={{ dataSourceId: "d", text: "a{{absent}}b" }} ctx={ctx} />);
  expect(screen.getByText("ab")).toBeInTheDocument();

  const Panel = getWidget("text")!.PropsPanel;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ text: "" }} dataSources={[]} onChange={() => {}} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Source de données")).toBeInTheDocument();
});

test("text uses the text color theme token", () => {
  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Salut" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Salut")).toHaveClass("text-[var(--gs-color-text)]");
});

test("text resolves {{var:nom}} directly from ctx.variables, independent of a bound source", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text
      props={{ text: "Valeur : {{var:message}}" }}
      ctx={{ mode: "runtime", variables: { message: "salut" } } as WidgetContext}
    />,
  );
  expect(screen.getByText("Valeur : salut")).toBeInTheDocument();
});

test("text stringifies a number variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text
      props={{ text: "Total : {{var:count}}" }}
      ctx={{ mode: "runtime", variables: { count: 42 } } as WidgetContext}
    />,
  );
  expect(screen.getByText("Total : 42")).toBeInTheDocument();
});

test("text stringifies a bool variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text
      props={{ text: "Actif : {{var:gate}}" }}
      ctx={{ mode: "runtime", variables: { gate: true } } as WidgetContext}
    />,
  );
  expect(screen.getByText("Actif : true")).toBeInTheDocument();
});

test("text JSON-stringifies a record variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text
      props={{ text: "Sélection : {{var:selected}}" }}
      ctx={{ mode: "runtime", variables: { selected: { nom: "A" } } } as WidgetContext}
    />,
  );
  expect(screen.getByText('Sélection : {"nom":"A"}')).toBeInTheDocument();
});
