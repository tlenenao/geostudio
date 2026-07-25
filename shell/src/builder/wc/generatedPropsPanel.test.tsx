// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { expect, test, vi } from "vitest";
import { makeGeneratedPropsPanel } from "./generatedPropsPanel";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { WcWidgetManifest } from "./manifest";
import type { DataSource, ItemClient } from "../../api/types";

// DataSourceSelect (used when a manifest prop is of type "dataSource") reads
// the item client via useItems, even when its query is disabled — so any
// render exercising it needs an ItemClientProvider in scope.
function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={{} as unknown as ItemClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

// Panel is a plain controlled component: like the real PropsPanel usage in
// the builder, onChange must feed back into props for typed input to work
// (otherwise React's controlled-value reset fights every keystroke).
function renderControlled(
  Panel: ReturnType<typeof makeGeneratedPropsPanel>,
  initial: Record<string, unknown>,
  onChange: (props: Record<string, unknown>) => void,
) {
  function Wrapper() {
    const [props, setProps] = useState(initial);
    return (
      <Panel
        props={props}
        onChange={(p) => {
          setProps(p);
          onChange(p);
        }}
      />
    );
  }
  return render(<Wrapper />);
}

const manifest: WcWidgetManifest = {
  type: "test.panel",
  tag: "test-panel-widget",
  label: "Test panneau",
  props: [
    { name: "initial", type: "number", label: "Valeur initiale", default: 0 },
    { name: "title", type: "string", label: "Titre", default: "" },
    { name: "loud", type: "boolean", label: "Bruyant", default: false },
  ],
  defaultSize: { w: 2, h: 2 },
};

test("renders one field per manifest prop, typed accordingly", () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ initial: 3, title: "X", loud: true }} onChange={() => {}} />);
  expect(screen.getByLabelText("Valeur initiale")).toHaveAttribute("type", "number");
  expect(screen.getByLabelText("Valeur initiale")).toHaveValue(3);
  expect(screen.getByLabelText("Titre")).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("Titre")).toHaveValue("X");
  expect(screen.getByLabelText("Bruyant")).toHaveAttribute("type", "checkbox");
  expect(screen.getByLabelText("Bruyant")).toBeChecked();
});

test("editing a number field calls onChange with a coerced number", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  renderControlled(Panel, { initial: 3, title: "", loud: false }, onChange);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "7");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 7, title: "", loud: false });
});

test("editing a boolean field calls onChange with a boolean", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  renderControlled(Panel, { initial: 3, title: "", loud: false }, onChange);
  await userEvent.click(screen.getByLabelText("Bruyant"));
  expect(onChange).toHaveBeenLastCalledWith({ initial: 3, title: "", loud: true });
});

const DS: DataSource[] = [
  { id: "ds-a", type: "features", service: "core", layer: "incidents", query: {} },
  { id: "ds-b", type: "features", service: "core", layer: "villes", query: {} },
];

const manifestWithDataSource: WcWidgetManifest = {
  type: "test.panel-ds",
  tag: "test-panel-ds-widget",
  label: "Test panneau DS",
  props: [{ name: "source", type: "dataSource", label: "Source de données", default: "" }],
  permissions: { collections: ["incidents"] },
  defaultSize: { w: 2, h: 2 },
};

test("a dataSource prop renders a DataSourceSelect filtered by permissions.collections", () => {
  const Panel = makeGeneratedPropsPanel(manifestWithDataSource);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />, { wrapper });
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  const optionLabels = Array.from(select.options).map((o) => o.textContent);
  expect(optionLabels).toEqual(["Aucune", "incidents"]);
});

test("permissions.collections: \"all\" proposes every data source", () => {
  const manifest: WcWidgetManifest = { ...manifestWithDataSource, permissions: { collections: "all" } };
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />, { wrapper });
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Aucune", "incidents", "villes"]);
});

test("no permissions declared proposes every data source (backward compatible)", () => {
  const manifest: WcWidgetManifest = { ...manifestWithDataSource, permissions: undefined };
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={() => {}} />, { wrapper });
  const select = screen.getByLabelText("Source de données") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Aucune", "incidents", "villes"]);
});

test("selecting a data source calls onChange with its id", async () => {
  const Panel = makeGeneratedPropsPanel(manifestWithDataSource);
  const onChange = vi.fn();
  render(<Panel props={{ source: "" }} dataSources={DS} onChange={onChange} />, { wrapper });
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds-a");
  expect(onChange).toHaveBeenCalledWith({ source: "ds-a" });
});
