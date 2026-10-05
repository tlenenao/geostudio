// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { DataProvider, useDataStates } from "../DataContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { ReactElement } from "react";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient, DataSource } from "../../api/types";
import { ExplorerProvider } from "../ExplorerContext";
import { enableMockAuth } from "../../auth/useAuth";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

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

test.each(["list", "table"])(
  "%s dont la source est introuvable affiche un état explicite, pas le chargement (P10.09)",
  (type) => {
    const Widget = getWidget(type)!.Component;
    renderWithItemClient(
      <Widget props={{ dataSourceId: "supprimee" }} ctx={{ mode: "runtime" } as WidgetContext} />,
    );
    expect(screen.getByText("Source de données introuvable")).toBeInTheDocument();
    expect(screen.queryByText("Chargement…")).not.toBeInTheDocument();
  },
);

test("list renders a record per row using the title field", () => {
  const List = getWidget("list")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({
      records: [
        { id: 1, properties: { nom: "Parc A" } },
        { id: 2, properties: { nom: "Parc B" } },
      ],
    }),
  } as WidgetContext;
  render(<List props={{ dataSourceId: "d", titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toBeInTheDocument();
  expect(screen.getByText("Parc B")).toBeInTheDocument();
});

test("list shows loading and empty states", () => {
  const List = getWidget("list")!.Component;
  const { rerender } = render(
    <List props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />,
  );
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  rerender(<List props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("table renders headers from columns and a cell per column", () => {
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "A", ville: "X" } }] }),
  } as WidgetContext;
  renderWithItemClient(
    <Table props={{ dataSourceId: "d", columns: ["nom", "ville"] }} ctx={ctx} />,
  );
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
    mode: "runtime",
    bus,
    widgetId: "list1",
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
  const queryDataSource = vi
    .fn()
    .mockResolvedValueOnce([
      { id: 1, properties: { nom: "A" } },
      { id: 2, properties: { nom: "B" } },
    ])
    .mockResolvedValueOnce([{ id: 1, properties: { nom: "A" } }]);
  const client = {
    queryDataSource,
    featuresUrl: vi.fn().mockReturnValue("u"),
  } as unknown as ItemClient;
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "flt", event: "changed", to: "list1", action: "setFilter" }]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sources: DataSource[] = [
    { id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} },
  ];
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
        <DataProvider sources={sources}>
          <Bound />
        </DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText("A")).toBeInTheDocument());
  await act(async () => {
    bus.emit("flt", "changed", { nom: "A" });
  });
  await waitFor(() =>
    expect(queryDataSource).toHaveBeenLastCalledWith(
      expect.objectContaining({ query: { nom: "A" } }),
    ),
  );
});

test("table sorts rows when a column header is clicked", async () => {
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({
      records: [
        { id: 1, properties: { nom: "B" } },
        { id: 2, properties: { nom: "A" } },
        { id: 3, properties: { nom: "C" } },
      ],
    }),
  } as WidgetContext;
  renderWithItemClient(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  const header = screen.getByRole("columnheader", { name: /nom/ });
  await userEvent.click(header);
  let cells = screen.getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("A"); // ascending
  expect(header).toHaveAttribute("aria-sort", "ascending");
  await userEvent.click(header);
  cells = screen.getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("C"); // descending
  expect(header).toHaveAttribute("aria-sort", "descending");
});

test("table paginates with a configured page size", async () => {
  const Table = getWidget("table")!.Component;
  const records = [1, 2, 3].map((n) => ({ id: n, properties: { nom: `N${n}` } }));
  const ctx = { mode: "runtime", data: state({ records }) } as WidgetContext;
  renderWithItemClient(
    <Table props={{ dataSourceId: "d", columns: ["nom"], pageSize: 2 }} ctx={ctx} />,
  );
  expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 data rows
  expect(screen.queryByText("N3")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByRole("cell", { name: "N3" })).toBeInTheDocument();
});

test("table annonce la troncature quand le total réel dépasse les lignes reçues (P29.05)", () => {
  const Table = getWidget("table")!.Component;
  const records = [1, 2].map((n) => ({ id: n, properties: { nom: `N${n}` } }));
  const ctx = { mode: "runtime", data: state({ records, total: 500000 }) } as WidgetContext;
  renderWithItemClient(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  expect(screen.getByRole("status")).toHaveTextContent("Lignes affichées : 2 sur 500000");
});

test("table cell of a plain field is formatted per its collection schema type (fr-FR)", async () => {
  // D35 (Vague C, SP-C6) : une colonne de champ simple liée à une
  // collection dont le schéma déclare `type: "number"` doit passer par
  // `formatFieldValue` (fr-FR), pas `String(value)` brut — seul le vrai
  // chemin (résolution du schéma via `useCollectionSchema`, jusqu'au rendu
  // de la cellule) prouve le câblage, pas un test unitaire de
  // `formatFieldValue` seul.
  const Table = getWidget("table")!.Component;
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue({
      collection: "parcs",
      pk: "id",
      geometry: null,
      fields: [{ name: "population", type: "number", required: false }],
    }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ctx = {
    mode: "runtime",
    data: state({
      collectionId: "parcs",
      records: [{ id: 1, properties: { population: 1234.5 } }],
    }),
  } as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Table props={{ dataSourceId: "d", columns: ["population"] }} ctx={ctx} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("cell", { name: new Intl.NumberFormat("fr-FR").format(1234.5) }),
  ).toBeInTheDocument();
});

test("list item uses the theme border/surface/text tokens", () => {
  const List = getWidget("list")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  render(<List props={{ titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toHaveClass(
    "border-[var(--gs-color-border)]",
    "text-[var(--gs-color-text)]",
    "hover:bg-[var(--gs-color-surface)]",
  );
});

test("table uses the shared DataTable's semantic theme tokens", () => {
  // Depuis la migration sur DataTable (Tâche 24, SP-B11e), le thème n'est
  // plus porté par des classes littérales `var(--gs-color-*)` posées ici,
  // mais par les tokens déjà sémantiques du composant partagé
  // (`ui/kit/Table.tsx` : "text-ink", "border-rule-2") — plus de couleur
  // Tailwind brute, mais un vocabulaire de tokens différent.
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "A" } }] }),
  } as WidgetContext;
  renderWithItemClient(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  expect(screen.getByRole("table")).toHaveClass("text-ink");
  expect(screen.getAllByRole("row")[1]).toHaveClass("border-rule-2");
});

test("table emits itemSelected with the clicked row", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "flyTo", handler);
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    bus,
    widgetId: "table1",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  renderWithItemClient(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  await userEvent.click(screen.getByRole("cell", { name: "Parc A" }));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" } });
});

test("table renders a calculated column evaluated per row against record and vars", () => {
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    variables: { seuil: "haute" },
    data: state({
      records: [
        { id: 1, properties: { nom: "A", gravite: "haute" } },
        { id: 2, properties: { nom: "B", gravite: "faible" } },
      ],
    }),
  } as WidgetContext;
  renderWithItemClient(
    <Table
      props={{
        dataSourceId: "d",
        columns: ["nom", { label: "Urgent", expr: "record.gravite == vars.seuil" }],
      }}
      ctx={ctx}
    />,
  );
  expect(screen.getByRole("columnheader", { name: "Urgent" })).toBeInTheDocument();
  const cells = screen.getAllByRole("cell");
  expect(cells[1]).toHaveTextContent("true"); // ligne 1 : gravite == seuil
  expect(cells[3]).toHaveTextContent("false"); // ligne 2 : gravite != seuil
});

test("a calculated column header has no sort button and stays unsortable", async () => {
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ records: [{ id: 1, properties: { nom: "A" } }] }),
  } as WidgetContext;
  renderWithItemClient(
    <Table props={{ dataSourceId: "d", columns: [{ label: "Calc", expr: "1 + 1" }] }} ctx={ctx} />,
  );
  expect(screen.queryByRole("button", { name: /Calc/ })).not.toBeInTheDocument();
  const header = screen.getByRole("columnheader", { name: "Calc" });
  expect(header).toHaveAttribute("aria-sort", "none");
  // DataTable appelle onSortChange uniformément pour tout en-tête cliqué ;
  // toggleSort ignore les clés hors sortableKeys (colonnes calculées) —
  // vérifier que le clic ne bascule pas aria-sort, pas seulement l'absence
  // de bouton.
  await userEvent.click(header);
  expect(header).toHaveAttribute("aria-sort", "none");
});

test("table row selection is keyboard operable (Enter) after the DataTable migration", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "flyTo", handler);
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    bus,
    widgetId: "table1",
    data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  renderWithItemClient(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  const row = screen.getAllByRole("row")[1];
  row.focus();
  fireEvent.keyDown(row, { key: "Enter" });
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" } });
});

function renderWithItemClient(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = {} as unknown as ItemClient;
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>{ui}</ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("table PropsPanel adds a calculated column without disturbing existing plain columns", async () => {
  const Table = getWidget("table")!;
  const onChange = vi.fn();
  const { container } = renderWithItemClient(
    <Table.PropsPanel props={{ columns: ["nom"] }} onChange={onChange} dataSources={[]} />,
  );
  expectTokenizedClasses(container);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une colonne calculée" }));
  expect(onChange).toHaveBeenCalledWith({
    columns: ["nom", { label: "Nouvelle colonne", expr: "" }],
  });
});

test("SP-B12c : le panneau de propriétés de la liste n'a pas de couleur Tailwind codée en dur", () => {
  const List = getWidget("list")!;
  const { container } = renderWithItemClient(
    <List.PropsPanel
      props={{ dataSourceId: "", titleField: "" }}
      onChange={vi.fn()}
      dataSources={[]}
    />,
  );
  expectTokenizedClasses(container);
});

test("SP-B12c : le panneau de propriétés de la table avec une colonne calculée n'a pas de couleur Tailwind codée en dur", () => {
  const Table = getWidget("table")!;
  const { container } = renderWithItemClient(
    <Table.PropsPanel
      props={{ columns: ["nom", { label: "Calc", expr: "1 + 1" }] }}
      onChange={vi.fn()}
      dataSources={[]}
    />,
  );
  expectTokenizedClasses(container);
});

function CrossFilterProbe({ datasetId }: { datasetId: string }) {
  const ctx = useAnalyticsContext();
  const entry = ctx.crossFilter[datasetId];
  return (
    <p>
      cf:
      {entry
        ? `${entry.field}=${entry.value};geom=${JSON.stringify(entry.geometry ?? null)}`
        : "none"}
    </p>
  );
}

test("table row click sets the cross-filter by pkColumn when dataset-bound and interactions is auto", async () => {
  const Table = getWidget("table")!.Component;
  const data = {
    loading: false,
    error: false,
    records: [{ id: 1, properties: { nom: "Parc A" } }],
    datasetId: "dataset-1",
    pkColumn: "id",
  };
  renderWithItemClient(
    <AnalyticsContextProvider interactions="auto">
      <Table props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A").closest("tr")!);
  expect(await screen.findByText("cf:id=1;geom=null")).toBeInTheDocument();
});

test("table row click forwards the record's geometry to the cross-filter entry when present", async () => {
  const Table = getWidget("table")!.Component;
  const data = {
    loading: false,
    error: false,
    records: [
      { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } },
    ],
    datasetId: "dataset-1",
    pkColumn: "id",
  };
  renderWithItemClient(
    <AnalyticsContextProvider interactions="auto">
      <Table props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A").closest("tr")!);
  expect(
    await screen.findByText('cf:id=1;geom={"type":"Point","coordinates":[5,6]}'),
  ).toBeInTheDocument();
});

test("list item click does not set a cross-filter when the source isn't dataset-bound", async () => {
  const List = getWidget("list")!.Component;
  const data = {
    loading: false,
    error: false,
    records: [{ id: 1, properties: { nom: "Parc A" } }],
  };
  render(
    <AnalyticsContextProvider interactions="auto">
      <List
        props={{ dataSourceId: "src-1", titleField: "nom" }}
        ctx={{ mode: "runtime", data } as WidgetContext}
      />
      <CrossFilterProbe datasetId="dataset-1" />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(screen.getByText("Parc A"));
  expect(await screen.findByText("cf:none")).toBeInTheDocument();
});

test("table PropsPanel edits a calculated column's label and expression", async () => {
  const Table = getWidget("table")!;
  const onChange = vi.fn();
  const props = { columns: ["nom", { label: "Nouvelle colonne", expr: "" }] };
  const { rerender } = renderWithItemClient(
    <Table.PropsPanel props={props} onChange={onChange} dataSources={[]} />,
  );
  await userEvent.type(screen.getByLabelText(/Libellé de la colonne calculée/), "!");
  const afterLabel = onChange.mock.calls.at(-1)![0];
  rerender(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Table.PropsPanel props={afterLabel} onChange={onChange} dataSources={[]} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByLabelText(/Expression de la colonne calculée/), "1");
  const afterExpr = onChange.mock.calls.at(-1)![0];
  expect(afterExpr.columns[0]).toBe("nom"); // colonne texte inchangée
  expect(afterExpr.columns[1].expr).toBe("1");
});

test("list shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const List = getWidget("list")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ datasetId: "ds1", records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  render(
    <ExplorerProvider enabled>
      <List props={{ dataSourceId: "src1" }} ctx={ctx} />
    </ExplorerProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("table shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Table = getWidget("table")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ datasetId: "ds1", records: [{ id: 1, properties: { nom: "Parc A" } }] }),
  } as WidgetContext;
  renderWithItemClient(
    <ExplorerProvider enabled>
      <Table props={{ dataSourceId: "src1", columns: ["nom"] }} ctx={ctx} />
    </ExplorerProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("table PropsPanel offers the CEL generator on a calculated column (REV-183)", async () => {
  enableMockAuth();
  const copilotTurn = vi.fn().mockResolvedValue({
    reply: "",
    clientOps: [{ op: "applyCelDraft", args: { expression: "record.pop * 2" } }],
  });
  const Table = getWidget("table")!;
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <Table.PropsPanel
          props={{ columns: ["pop", { label: "Double", expr: "" }] }}
          onChange={onChange}
          dataSources={[]}
          generateItemId="9"
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByText("Générer"));
  await userEvent.type(screen.getByLabelText("Décrire l'expression"), "double de pop");
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
  await screen.findByText("record.pop * 2");
  expect(copilotTurn.mock.calls[0][1].surface).toBe("computed_column");
  expect(copilotTurn.mock.calls[0][1].currentConfig.availableFields).toContain("record.pop");
  expect(onChange).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Appliquer" }));
  expect(onChange.mock.calls.at(-1)![0].columns[1].expr).toBe("record.pop * 2");
});

test("table PropsPanel has no generator without generateItemId", () => {
  const Table = getWidget("table")!;
  renderWithItemClient(
    <Table.PropsPanel
      props={{ columns: [{ label: "x", expr: "" }] }}
      onChange={vi.fn()}
      dataSources={[]}
    />,
  );
  expect(screen.queryByText("Générer")).toBeNull();
});
