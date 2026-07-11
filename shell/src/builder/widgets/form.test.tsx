import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const schema: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "titre", type: "string", required: true, maxLength: 120 },
    { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
    { name: "nb_victimes", type: "integer", required: false },
  ],
};

const dataSources: DataSource[] = [{ id: "ds1", type: "features", service: "core", layer: "incidents", query: {} }];

function renderPanel(
  initialProps: Record<string, unknown>,
  onChange = vi.fn(),
  clientOverrides: Partial<ItemClient> = {},
) {
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = getWidget("form")!.PropsPanel;

  // Wrapper feeds onChange back into props, like the real builder host does,
  // so controlled inputs (e.g. field label) reflect what was just typed
  // across multiple keystrokes instead of resetting to the initial value.
  function Wrapper() {
    const [props, setProps] = useState(initialProps);
    return (
      <Panel
        props={props}
        dataSources={dataSources}
        onChange={(next) => {
          onChange(next);
          setProps(next);
        }}
      />
    );
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Wrapper />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange, client };
}

test("form widget is registered with submitted/failed events and a reset action", () => {
  const def = getWidget("form")!;
  expect(def.label).toBe("Formulaire");
  expect(def.events).toEqual(["submitted", "failed"]);
  expect(def.actions).toEqual(["reset"]);
  expect(def.defaultProps).toEqual({ dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null });
});

test("props panel offers a button to load fields once the schema resolves", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: [], submitLabel: "Enregistrer", geometryType: null });
  const button = await screen.findByRole("button", { name: "Charger les champs du schéma" });
  await userEvent.click(button);
  expect(onChange).toHaveBeenCalledWith({
    dataSourceId: "ds1",
    submitLabel: "Enregistrer",
    geometryType: "Point",
    fields: [
      { name: "titre", type: "string", label: "titre", order: 0, hidden: false, required: true, maxLength: 120 },
      { name: "gravite", type: "enum", label: "gravite", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
      { name: "nb_victimes", type: "integer", label: "nb_victimes", order: 2, hidden: false, required: false },
    ],
  });
});

test("props panel hides the load button once fields are already loaded", () => {
  renderPanel({
    dataSourceId: "ds1",
    fields: [{ name: "titre", type: "string", label: "Titre", order: 0, hidden: false, required: true }],
    submitLabel: "Enregistrer",
    geometryType: null,
  });
  expect(screen.queryByRole("button", { name: "Charger les champs du schéma" })).not.toBeInTheDocument();
});

test("props panel shows an error when the schema fails to load", async () => {
  renderPanel(
    { dataSourceId: "ds1", fields: [], submitLabel: "Enregistrer", geometryType: null },
    vi.fn(),
    { getCollectionSchema: vi.fn().mockRejectedValue(new Error("nope")) },
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(/schéma introuvable/i);
});

test("props panel shows nothing schema-related when no data source is bound", () => {
  renderPanel({ dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null });
  expect(screen.queryByRole("button", { name: "Charger les champs du schéma" })).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

const loadedFields = [
  { name: "titre", type: "string" as const, label: "titre", order: 0, hidden: false, required: true, maxLength: 120 },
  { name: "gravite", type: "enum" as const, label: "gravite", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
  { name: "nb_victimes", type: "integer" as const, label: "nb_victimes", order: 2, hidden: false, required: false },
];

test("field overrides let you rename a field's label", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  const input = await screen.findByLabelText("Label du champ titre");
  await userEvent.clear(input);
  await userEvent.type(input, "Titre de l'incident");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "titre").label).toBe("Titre de l'incident");
});

test("field overrides toggle hidden and required", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await userEvent.click(await screen.findByLabelText("Masquer nb_victimes"));
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "nb_victimes").hidden).toBe(true);
});

test("field overrides set min/max on a numeric field", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await userEvent.type(await screen.findByLabelText("Min nb_victimes"), "0");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "nb_victimes").min).toBe(0);
});

test("field overrides set a validation pattern on a string field", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  // "[" is a special-key delimiter for userEvent.type; double it to type a literal "[". "]" alone is literal.
  await userEvent.type(await screen.findByLabelText("Motif titre"), "^[[A-Z]");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "titre").pattern).toBe("^[A-Z]");
});

test("field overrides do not offer min/max/pattern for an enum field", async () => {
  renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await screen.findByLabelText("Label du champ gravite");
  expect(screen.queryByLabelText("Min gravite")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Motif gravite")).not.toBeInTheDocument();
});

test("dragging a field row onto another reorders the list and renumbers order", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  const rows = await screen.findAllByRole("listitem");
  const dataTransfer = { setData: vi.fn() };
  fireEvent.dragStart(rows[0], { dataTransfer });
  fireEvent.drop(rows[2], { dataTransfer });
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.map((f: { name: string; order: number }) => [f.name, f.order])).toEqual([
    ["gravite", 0],
    ["nb_victimes", 1],
    ["titre", 2],
  ]);
});
