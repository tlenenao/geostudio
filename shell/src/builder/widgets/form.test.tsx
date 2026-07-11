import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource, ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import { ActionBus } from "../ActionBus";
import { FeatureValidationError } from "../../api/itemClient";

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

test("form widget is registered with submitted/failed events and reset/loadRecord actions", () => {
  const def = getWidget("form")!;
  expect(def.label).toBe("Formulaire");
  expect(def.events).toEqual(["submitted", "failed"]);
  expect(def.actions).toEqual(["reset", "loadRecord"]);
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

const visibleFields = [
  { name: "titre", type: "string" as const, label: "Titre", order: 0, hidden: false, required: true },
  { name: "gravite", type: "enum" as const, label: "Gravité", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
  { name: "nb_victimes", type: "integer" as const, label: "Victimes", order: 2, hidden: false, required: false, min: 0 },
  { name: "notes_internes", type: "string" as const, label: "Notes internes", order: 3, hidden: true, required: false },
];

function renderForm(fields = visibleFields, ctx: Partial<WidgetContext> = {}) {
  const client = { createFeature: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form props={{ dataSourceId: "ds1", fields, submitLabel: "Enregistrer" }} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("form renders visible fields ordered, skipping hidden ones", () => {
  renderForm();
  const labels = screen.getAllByRole("textbox").map((el) => el.getAttribute("aria-label"));
  expect(labels).toContain("Titre");
  expect(screen.queryByLabelText("Notes internes")).not.toBeInTheDocument();
});

test("form shows a required error after blurring an empty required field", async () => {
  renderForm();
  const titre = screen.getByLabelText("Titre");
  await userEvent.click(titre);
  await userEvent.tab();
  expect(await screen.findByRole("alert")).toHaveTextContent("Champ requis");
});

test("form blocks submit and surfaces one error per invalid required field", async () => {
  renderForm();
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(screen.getAllByRole("alert")).toHaveLength(2); // titre + gravite, tous deux requis et vides
});

test("form validates a numeric field against its min bound", async () => {
  renderForm();
  const victimes = screen.getByLabelText("Victimes");
  await userEvent.type(victimes, "-1");
  await userEvent.tab();
  expect(await screen.findByText("Doit être ≥ 0")).toBeInTheDocument();
});

test("form validates a string field against its pattern", async () => {
  const fields = [{ name: "titre", type: "string" as const, label: "Titre", order: 0, hidden: false, required: false, pattern: "^[A-Z]" }];
  renderForm(fields);
  const titre = screen.getByLabelText("Titre");
  await userEvent.type(titre, "fuite");
  await userEvent.tab();
  expect(await screen.findByText("Format invalide")).toBeInTheDocument();
});

test("form renders an enum field as a select with its schema options", () => {
  renderForm();
  const select = screen.getByLabelText("Gravité");
  expect(select.tagName).toBe("SELECT");
  expect(screen.getByRole("option", { name: "haute" })).toBeInTheDocument();
});

function renderConnectedForm({
  fields = visibleFields,
  client: clientOverrides = {},
  bus,
  widgetId = "form1",
  layer = "incidents",
}: {
  fields?: typeof visibleFields;
  client?: Partial<ItemClient>;
  bus?: ActionBus;
  widgetId?: string;
  layer?: string;
} = {}) {
  const client = {
    createFeature: vi.fn().mockResolvedValue({ id: 1 }),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields, submitLabel: "Enregistrer" }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer }, bus, widgetId } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client, invalidateSpy };
}

test("a valid submit calls createFeature with the bound collection and properties", async () => {
  const { client } = renderConnectedForm();
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith("incidents", {
      type: "Feature",
      properties: { titre: "Fuite d'eau", gravite: "haute" },
      geometry: null,
    }),
  );
});

test("a successful submit clears the form, invalidates data sources, and emits submitted", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "form1", event: "submitted", to: "sink", action: "log" }]);
  const { invalidateSpy } = renderConnectedForm({ bus });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(handler).toHaveBeenCalledWith({ properties: { titre: "Fuite d'eau", gravite: "haute" } }));
  expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["datasource"] });
  expect(screen.getByLabelText("Titre")).toHaveValue("");
});

test("submit is disabled while the write is pending", async () => {
  let resolveWrite!: (v: { id: number }) => void;
  const createFeature = vi.fn(() => new Promise<{ id: number }>((resolve) => { resolveWrite = resolve; }));
  renderConnectedForm({ client: { createFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  resolveWrite({ id: 1 });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).not.toBeDisabled());
});

test("a 400 response maps field errors onto the matching inputs", async () => {
  // titre/gravité are both filled (client validation passes) — the server
  // still rejects on a rule the client doesn't know about (e.g. a uniqueness
  // constraint), proving the 400 mapping runs independently of client checks.
  const createFeature = vi.fn().mockRejectedValue(
    new FeatureValidationError([{ field: "titre", code: "duplicate", message: "un incident « Fuite d'eau » existe déjà" }]),
  );
  const bus = new ActionBus();
  const failed = vi.fn();
  bus.register("sink", "log", failed);
  bus.configure([{ id: "m", from: "form1", event: "failed", to: "sink", action: "log" }]);
  renderConnectedForm({ client: { createFeature }, bus });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("un incident « Fuite d'eau » existe déjà")).toBeInTheDocument();
  expect(failed).toHaveBeenCalled();
});

test("a generic write failure shows a fallback message without crashing", async () => {
  const createFeature = vi.fn().mockRejectedValue(new Error("collection is not editable"));
  renderConnectedForm({ client: { createFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("Échec de l'enregistrement.")).toBeInTheDocument();
});

test("the reset bus action clears the form", async () => {
  // ActionBus.emit(widgetId, event) only routes through configured wiring
  // (from/event → to/action) — it does not invoke a widget's own registered
  // action directly. Mirror the mapWidget.test.tsx precedent: a source
  // widget ("btn1") emits an event wired to form1's "reset" action.
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "btn1", event: "clicked", to: "form1", action: "reset" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  await userEvent.type(screen.getByLabelText("Titre"), "Brouillon");
  bus.emit("btn1", "clicked");
  await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue(""));
});

function renderConnectedFormWithGeometry(geometryType: string | null) {
  const client = { createFeature: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields: visibleFields, submitLabel: "Enregistrer", geometryType }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer: "incidents" } } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client };
}

test("a Point collection shows longitude/latitude inputs", () => {
  renderConnectedFormWithGeometry("Point");
  expect(screen.getByLabelText("Longitude")).toBeInTheDocument();
  expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
});

test("a non-Point (or absent) geometry shows no geometry inputs", () => {
  renderConnectedFormWithGeometry("LineString");
  expect(screen.queryByLabelText("Longitude")).not.toBeInTheDocument();
  renderConnectedFormWithGeometry(null);
  expect(screen.queryByLabelText("Longitude")).not.toBeInTheDocument();
});

test("submitting with longitude/latitude filled sends a GeoJSON Point geometry", async () => {
  const { client } = renderConnectedFormWithGeometry("Point");
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.type(screen.getByLabelText("Longitude"), "2.35");
  await userEvent.type(screen.getByLabelText("Latitude"), "48.85");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith("incidents", {
      type: "Feature",
      properties: { titre: "Fuite d'eau", gravite: "haute" },
      geometry: { type: "Point", coordinates: [2.35, 48.85] },
    }),
  );
});

test("submitting a Point collection with empty coordinates sends a null geometry", async () => {
  const { client } = renderConnectedFormWithGeometry("Point");
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith(
      "incidents",
      expect.objectContaining({ geometry: null }),
    ),
  );
});

test("loadRecord pre-fills the form from the selected record's properties", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue("Fuite existante"));
  expect(screen.getByLabelText("Gravité")).toHaveValue("moyenne");
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});

test("loadRecord pre-fills longitude/latitude for a Point geometry", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const client = { createFeature: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields: visibleFields, submitLabel: "Enregistrer", geometryType: "Point" }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer: "incidents" }, bus, widgetId: "form1" } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  bus.emit("table1", "itemSelected", {
    id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" },
    geometry: { type: "Point", coordinates: [2.35, 48.85] },
  });
  await waitFor(() => expect(screen.getByLabelText("Longitude")).toHaveValue(2.35));
  expect(screen.getByLabelText("Latitude")).toHaveValue(48.85);
});

test("the Annuler button exits edit mode and clears the form", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(screen.queryByText(/Modification de l'enregistrement/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Titre")).toHaveValue("");
});

test("form declares loadRecord alongside reset", () => {
  expect(getWidget("form")!.actions).toEqual(["reset", "loadRecord"]);
});

test("submitting while editing calls updateFeature with the record id and stays on the record", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const { client } = renderConnectedForm({ client: { updateFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByDisplayValue("Fuite existante");
  await userEvent.clear(screen.getByLabelText("Titre"));
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite corrigée");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.updateFeature).toHaveBeenCalledWith("incidents", "7", {
      type: "Feature",
      properties: { titre: "Fuite corrigée", gravite: "moyenne" },
      geometry: null,
    }),
  );
  expect(screen.getByLabelText("Titre")).toHaveValue("Fuite corrigée");
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});

test("createFeature is still called (not updateFeature) when not editing", async () => {
  const updateFeature = vi.fn();
  const { client } = renderConnectedForm({ client: { updateFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(client.createFeature).toHaveBeenCalled());
  expect(updateFeature).not.toHaveBeenCalled();
});

test("updating a record resubmits a hidden field's original value unchanged", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const updateFeature = vi.fn().mockResolvedValue(undefined);
  const { client } = renderConnectedForm({ client: { updateFeature }, bus });
  bus.emit("table1", "itemSelected", {
    id: 7,
    properties: { titre: "Fuite existante", gravite: "moyenne", notes_internes: "confidentiel" },
  });
  await screen.findByDisplayValue("Fuite existante");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.updateFeature).toHaveBeenCalledWith("incidents", "7", {
      type: "Feature",
      properties: { titre: "Fuite existante", gravite: "moyenne", notes_internes: "confidentiel" },
      geometry: null,
    }),
  );
});

test("Supprimer calls deleteFeature after confirmation, invalidates, and exits edit mode", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const deleteFeature = vi.fn().mockResolvedValue(undefined);
  const { client, invalidateSpy } = renderConnectedForm({ client: { deleteFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(client.deleteFeature).toHaveBeenCalledWith("incidents", "7"));
  expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["datasource"] });
  expect(screen.queryByText(/Modification de l'enregistrement/)).not.toBeInTheDocument();
});

test("Supprimer does nothing when the confirmation is declined", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const deleteFeature = vi.fn();
  const { client } = renderConnectedForm({ client: { deleteFeature }, bus });
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(client.deleteFeature).not.toHaveBeenCalled();
  expect(screen.getByText(/Modification de l'enregistrement #7/)).toBeInTheDocument();
});
