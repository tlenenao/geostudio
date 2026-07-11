import { render, screen } from "@testing-library/react";
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
  props: Record<string, unknown>,
  onChange = vi.fn(),
  clientOverrides: Partial<ItemClient> = {},
) {
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = getWidget("form")!.PropsPanel;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Panel props={props} dataSources={dataSources} onChange={onChange} />
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
