// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient, MapConfig, Theme } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();
let lastConfig: MapConfig | null = null;

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      {
        config,
        onViewChange,
        onFeatureClick,
        loadCustomIcon,
        themeColors,
        interactiveTools,
      }: {
        config: MapConfig;
        onViewChange?: (v: {
          center: [number, number];
          zoom: number;
          bbox: [number, number, number, number];
        }) => void;
        onFeatureClick?: (record: {
          id: string | number;
          properties: Record<string, unknown>;
          geometry?: unknown;
        }) => void;
        loadCustomIcon?: (iconId: string) => Promise<Blob>;
        themeColors?: unknown;
        interactiveTools?: boolean;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      lastConfig = config;
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      const layer = config.layers[0];

      const url = layer && "url" in layer ? ((layer as any).url ?? "") : "";

      const renderAs = layer && "renderAs" in layer ? ((layer as any).renderAs ?? "") : "";

      const paint = layer && "paint" in layer ? JSON.stringify((layer as any).paint ?? {}) : "{}";
      const symbology =
        layer && "symbology" in layer ? JSON.stringify((layer as any).symbology ?? null) : "null";
      return (
        <div
          data-testid="mapview"
          onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}
        >
          layers:{config.layers.length} url:{url} renderAs:{renderAs} paint:{paint} symbology:
          {symbology} themeColors:{JSON.stringify(themeColors ?? null)} tools:
          {String(!!interactiveTools)} loader:{typeof loadCustomIcon}
          <button
            type="button"
            data-testid="feature"
            onClick={() =>
              onFeatureClick?.({
                id: 1,
                properties: { nom: "Parc A" },
                geometry: { type: "Point", coordinates: [5, 6] },
              })
            }
          >
            feature
          </button>
        </div>
      );
    },
  ),
}));

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
  flyToSpy.mockClear();
  highlightSpy.mockClear();
  lastConfig = null;
});
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({
  loading: false,
  error: false,
  records: [],
  ...over,
});

// Every Component test needs QueryClientProvider + ItemClientProvider —
// the widget calls useItemClient() to get getAuthToken/getCoreUrl for
// MapView, and PropsPanel's MapSymbologyEditor/DataSourceSelect need the
// same providers. Component itself no longer performs any live domain
// query: paint/legend are derived from the frozen `props.symbology` at
// render time (Task 11) — a bare vi.fn() default for queryDataSource is
// safe everywhere it isn't explicitly asserted against.
function withClient(
  children: React.ReactNode,
  queryDataSource: ReturnType<typeof vi.fn> = vi.fn(),
) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function renderPropsPanel({
  props,
  onChange,
  dataSources = [],
  theme,
}: {
  props: Record<string, unknown>;
  onChange: (props: Record<string, unknown>) => void;

  dataSources?: any[];
  theme?: Theme;
}) {
  const Panel = getWidget("map")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={props} dataSources={dataSources} onChange={onChange} theme={theme} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

function renderWidget({
  props,
  ctx = {},
}: {
  props: Record<string, unknown>;
  ctx?: Partial<WidgetContext>;
}) {
  const Map = getWidget("map")!.Component;
  const defaultData = {
    loading: false,
    error: false,
    records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
    url: "https://core/collections/test/items",
  };
  const defaultCtx: WidgetContext = {
    mode: "runtime",
    data: { ...defaultData, ...ctx?.data },
    ...ctx,
  } as WidgetContext;
  render(withClient(<Map props={props} ctx={defaultCtx} />));
}

function lastMapConfig(): MapConfig {
  if (!lastConfig) throw new Error("No MapConfig captured yet");
  return lastConfig;
}

test("registers with a 6x6 default size", () => {
  expect(getWidget("map")!.defaultSize).toEqual({ w: 6, h: 6 });
});

test("PropsPanel mounts MapSymbologyEditor with theme from props", () => {
  const onChange = vi.fn();
  renderPropsPanel({
    props: { dataSourceId: "ds1" },
    onChange,
    theme: { colors: { primary: "#2563eb" } },
  });
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("choosing Jenks from the widget's PropsPanel surfaces an error instead of hanging", async () => {
  const onChange = vi.fn();
  renderPropsPanel({
    props: {
      dataSourceId: "ds1",
      symbology: {
        color: {
          field: "pop",
          mode: "numeric",
          classification: { method: "jenks", classes: 5 },
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      },
    },
    onChange,
  });
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Jenks sur le widget carte nécessite un collectionId résolu — non câblé",
  );
  // The button re-enables afterwards (busy reset in MapSymbologyEditor's
  // `finally`) instead of hanging forever on "Calcul…".
  expect(screen.getByRole("button", { name: "Recalculer les classes" })).not.toBeDisabled();
});

// I5 de la revue finale SP-25 : Jenks ne peut jamais fonctionner sur cet
// hôte (sampleField y lève systématiquement, cf. le test ci-dessus) —
// l'option ne doit donc pas être offerte du tout dans le select, même
// précédent que "theme-primary" (conditionnel sur themeColors).
test("Jenks option is absent from the widget's PropsPanel classification select", () => {
  renderPropsPanel({
    props: {
      dataSourceId: "ds1",
      symbology: {
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      },
    },
    onChange: vi.fn(),
  });
  const select = screen.getByLabelText("Méthode de classification") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "jenks")).toBe(false);
});

// I5 de la revue finale SP-25 : `runStatistics` hardcodait `layer: ""` et ne
// résolvait qu'à travers `datasetId` — une source "features" branchée
// directement sur une collection (pas de datasetId, cas valide et
// sélectionnable, cf. DataSourceSelect qui filtre sur `type === "features"`)
// postait alors vers `/collections//aggregate`. Le repli doit utiliser
// `dataSource.layer`, qui porte l'id de collection dans ce cas.
test("recompute works for a plain collection-backed source (no datasetId), via dataSource.layer", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const onChange = vi.fn();
  const Panel = getWidget("map")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{ queryDataSource } as unknown as ItemClient}>
        <Panel
          props={{
            dataSourceId: "src1",
            symbology: {
              color: {
                field: "pop",
                mode: "numeric",
                classification: { method: "equalInterval", classes: 4 },
                palette: "sequential-blue",
                domain: { kind: "numeric", min: 0, max: 0 },
                computedAt: "",
              },
            },
          }}
          dataSources={[
            { id: "src1", type: "features", service: "core", layer: "communes", query: {} },
          ]}
          onChange={onChange}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(queryDataSource).toHaveBeenCalledWith(
    expect.objectContaining({ layer: "communes", datasetId: undefined }),
  );
  await vi.waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        symbology: expect.objectContaining({
          color: expect.objectContaining({
            domain: { kind: "numeric-classed", breaks: [0, 25, 50, 75, 100] },
          }),
        }),
      }),
    ),
  );
});

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = {
    mode: "runtime",
    data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }),
  } as WidgetContext;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:1");
  expect(view).toHaveTextContent("url:https://fs/parcs/items.json");
});

test("map widget renders an empty map when no source is bound", async () => {
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:0");
});

test("map declares extentChanged/itemSelected events and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toEqual(["extentChanged", "itemSelected"]);
  expect(getWidget("map")!.actions).toEqual(expect.arrayContaining(["flyTo", "highlight"]));
});

test("map emits extentChanged when the view moves", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "extentChanged", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />,
    ),
  );
  await userEvent.click(await screen.findByTestId("mapview"));
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] });
});

test("map flyTo action flies to a selected record's point", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />,
    ),
  );
  await screen.findByTestId("mapview");
  bus.emit("list1", "itemSelected", {
    id: 1,
    properties: {},
    geometry: { type: "Point", coordinates: [5, 6] },
  });
  expect(flyToSpy).toHaveBeenCalledWith({ center: [5, 6], zoom: 12 });
});

test("map emits itemSelected when a feature is clicked", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "itemSelected", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />,
    ),
  );
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({
    id: 1,
    properties: { nom: "Parc A" },
    geometry: { type: "Point", coordinates: [5, 6] },
  });
});

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <AnalyticsContextProvider interactions="auto">
        <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
        <ExtentProbe />
      </AnalyticsContextProvider>,
    ),
  );
  const view = await screen.findByTestId("mapview");
  vi.useFakeTimers();
  try {
    fireEvent.click(view);
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(screen.getByText("extent:10,20,30,40")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return (
      <p>
        cf:
        {entry
          ? `${entry.field}=${entry.value};geom=${JSON.stringify(entry.geometry ?? null)}`
          : "none"}
      </p>
    );
  }
  const Map = getWidget("map")!.Component;
  const data = {
    loading: false,
    error: false,
    records: [],
    datasetId: "dataset-1",
    pkColumn: "id",
  };
  render(
    withClient(
      <AnalyticsContextProvider interactions="auto">
        <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
        <CrossFilterProbe />
      </AnalyticsContextProvider>,
    ),
  );
  await userEvent.click(await screen.findByTestId("feature"));
  expect(
    await screen.findByText('cf:id=1;geom={"type":"Point","coordinates":[5,6]}'),
  ).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = {
    mode: "runtime",
    data: {
      loading: false,
      error: false,
      records: [],
      datasetId: "ds1",
      url: "https://core/collections/geo/items",
    },
  } as unknown as WidgetContext;
  render(
    withClient(
      <ExplorerProvider enabled>
        <Map props={{ dataSourceId: "src1" }} ctx={ctx} />
      </ExplorerProvider>,
    ),
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("le widget transmet la symbologie figée à MapView, sans requête de domaine", async () => {
  const queryDataSource = vi.fn();
  const symbology = {
    color: {
      field: "region",
      mode: "categorical",
      palette: "categorical-a",
      domain: { kind: "categorical", values: ["Nord", "Sud"] },
      computedAt: "2026-08-23T10:00:00Z",
    },
  };
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{ dataSourceId: "d", symbology }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/communes/items.json",
              records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
            }),
          } as WidgetContext
        }
      />,
      queryDataSource,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain('"field":"region"');
  expect(view.textContent).toContain('"palette":"categorical-a"');
  // Plus aucun `paint` compilé par le widget : c'est MapView qui compile.
  expect(view.textContent).toContain("paint:{}");
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("un point avec taille et couleur donne renderAs:circle et la symbologie complète", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            color: {
              field: "valeur",
              mode: "numeric",
              palette: "sequential-blue",
              domain: { kind: "numeric", min: 0, max: 100 },
              computedAt: "2026-08-23T10:00:00Z",
            },
            size: {
              field: "montant",
              domain: { min: 5, max: 25 },
              computedAt: "2026-08-23T10:00:00Z",
            },
          },
        }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/points/items.json",
              records: [
                { id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
              ],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:circle");
  expect(view.textContent).toContain('"field":"montant"');
});

// La palette de thème n'est plus résolue par le widget mais par MapView :
// ce qui doit être prouvé ici est que ctx.theme.colors LUI PARVIENT. Sans
// cela, une palette theme-primary rendrait silencieusement les mauvaises
// couleurs (le bug que l'ancienne version de ce test attrapait).
//
// À consigner (constat N14, informatif) : le test existant assertait DEUX
// choses — `toContain('"#2563eb"]}')` **et** `not.toContain("#1e3a8a")`,
// c'est-à-dire « la couleur résolue du thème apparaît, ET PAS la valeur par
// défaut de sequential-blue / NUMERIC_COLOR_HIGH ». Cette assertion NÉGATIVE
// est précisément celle qui avait attrapé le bug d'origine, et elle
// disparaît de ce fichier. La propriété de bout en bout reste couverte,
// mais par un AUTRE fichier :
// `MapView.test.tsx` ("themeColors reaches the paint compilation
// (theme-primary resolves)") prouve déjà que `themeColors` atteint la
// compilation réelle du paint. Acceptable, et écrit ici pour qu'une revue ne
// le prenne pas pour une perte silencieuse de couverture.
test("ctx.theme.colors est transmis à MapView pour résoudre theme-primary", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            color: {
              field: "valeur",
              mode: "numeric",
              palette: "theme-primary",
              domain: { kind: "numeric", min: 0, max: 100 },
              computedAt: "2026-08-23T10:00:00Z",
            },
          },
        }}
        ctx={
          {
            mode: "runtime",
            theme: { colors: { primary: "#2563eb" } },
            data: state({
              url: "https://fs/points/items.json",
              records: [
                { id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
              ],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain('themeColors:{"primary":"#2563eb"}');
  expect(view.textContent).toContain('"palette":"theme-primary"');
});

// Non-régression du chemin historique : une couche sans symbologie doit
// arriver chez MapView exactement comme avant (paint vide, renderAs dérivé
// de la géométrie), et MapView la peint par sa branche `layer.paint ?? {}`.
test("sans symbologie, la couche transmise est inchangée", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{ dataSourceId: "d" }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/communes/items.json",
              records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("symbology:null");
  expect(view.textContent).toContain("paint:{}");
});

test("la barre mesure/croquis n'est active qu'en dehors du mode édition", async () => {
  const Map = getWidget("map")!.Component;
  const data = state({
    url: "https://fs/communes/items.json",
    records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
  });
  const { rerender } = render(
    withClient(<Map props={{ dataSourceId: "d" }} ctx={{ mode: "edit", data } as WidgetContext} />),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("tools:false");

  rerender(
    withClient(
      <Map props={{ dataSourceId: "d" }} ctx={{ mode: "runtime", data } as WidgetContext} />,
    ),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("tools:true");
});

test("shows no symbology legend when no encoding is configured", () => {
  const ctx = {
    mode: "runtime",
    data: state({ url: "https://fs/communes/items.json" }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  expect(screen.queryByText("Nord")).not.toBeInTheDocument();
});

test("shows a categorical symbology legend from frozen props.symbology", async () => {
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            color: {
              field: "region",
              mode: "categorical",
              palette: "categorical-a",
              domain: { kind: "categorical", values: ["Nord", "Sud"] },
              computedAt: "2026-08-23T10:00:00Z",
            },
          },
        }}
        ctx={ctx}
      />,
    ),
  );
  expect(await screen.findByText("Nord")).toBeInTheDocument();
  expect(screen.getByText("Sud")).toBeInTheDocument();
});

test("the props panel exposes the shared popup editor", async () => {
  const onChange = vi.fn();
  renderPropsPanel({ props: { dataSourceId: "ds1" }, onChange });
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ popup: {} }));
});

test("the popup editor accepts a hand-typed field name", async () => {
  // PropsPanel ne reçoit que { props, onChange, dataSources }
  // (builder/registry.ts:33-37) : ni schéma ni enregistrements. La saisie
  // libre est donc le seul chemin ici — le même que les champs « Champ
  // couleur » et « Champ taille » voisins.
  const onChange = vi.fn();
  renderPropsPanel({ props: { dataSourceId: "ds1", popup: {} }, onChange });
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ popup: { fields: [{ name: "nom" }] } }),
  );
});

test("the configured popup reaches the layer the widget builds", async () => {
  renderWidget({ props: { dataSourceId: "ds1", popup: { titleField: "nom" } } });

  await screen.findByTestId("mapview");
  expect((lastMapConfig().layers[0] as any).popup).toEqual({ titleField: "nom" });
});

test("no popup configured means no popup on the layer", async () => {
  renderWidget({ props: { dataSourceId: "ds1" } });

  await screen.findByTestId("mapview");
  expect((lastMapConfig().layers[0] as any).popup).toBeUndefined();
});

test("shows a stroke legend entry from a data-driven stroke color", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            stroke: {
              color: {
                field: "region",
                domain: { kind: "categorical", values: ["Nord"] },
                palette: "categorical-a",
              },
              width: { fixed: 1 },
              style: "solid",
            },
          },
        }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/communes/items.json",
              records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  expect(await screen.findByText("Nord")).toBeInTheDocument();
});

// Fix I2 de la revue finale SP-27 : miroir du test ci-dessus, mais pour un
// contour CLASSÉ (quantile/equalInterval/Jenks) — `legend.stroke` était
// jusqu'ici typé catégoriel-seul, alors que le sélecteur de contour (Task 5)
// et le rendu (buildMapPaint) traitent déjà ce cas.
test("shows a classed stroke legend entry from a data-driven stroke color", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            stroke: {
              color: {
                field: "pop",
                domain: { kind: "numeric-classed", breaks: [0, 10, 20] },
                palette: "sequential-blue",
              },
              width: { fixed: 1 },
              style: "solid",
            },
          },
        }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/communes/items.json",
              records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  expect(await screen.findByText("0.0 – 10.0")).toBeInTheDocument();
  expect(screen.getByText("10.0 – 20.0")).toBeInTheDocument();
});

test("shows an icon legend entry per mapped value", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            icon: {
              field: "categorie",
              domain: { kind: "categorical", values: ["ecole"] },
              mapping: { ecole: { source: "lucide", name: "school" } },
            },
          },
        }}
        ctx={
          {
            mode: "runtime",
            data: state({
              url: "https://fs/poi/items.json",
              records: [
                { id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
              ],
            }),
          } as WidgetContext
        }
      />,
    ),
  );
  expect(await screen.findByText("ecole")).toBeInTheDocument();
});

// Le mock de MapView de ce fichier (lignes 20-75) ne déstructure que
// config/onViewChange/onFeatureClick/loadCustomIcon/ref : cette tâche (Task 12)
// est celle qui ajoute loadCustomIcon au mock et au texte rendu — Task 19 y
// ajoutera symbology/themeColors/tools plus tard, de façon additive sur le
// même return. `client.fetchMapIconBlob` n'a pas besoin d'être défini sur le
// client du test : le composant passe toujours une flèche inline à MapView,
// donc `typeof loadCustomIcon` vaut "function" qu'elle soit jamais appelée
// ou non — ce test ne vérifie que le câblage, pas l'appel.
test("le widget carte fournit le chargeur d'icônes personnalisées à MapView", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{ dataSourceId: "d" }}
        ctx={{ mode: "runtime", data: state() } as WidgetContext}
      />,
    ),
  );
  expect(await screen.findByText(/loader:function/)).toBeInTheDocument();
});

test("map widget carries collectionId/pkColumn from ctx.data onto the feature layer (SP-40)", () => {
  renderWidget({
    props: { dataSourceId: "ds1" },
    ctx: {
      data: state({
        url: "https://core.test/collections/parcs/items.geojson",
        collectionId: "parcs",
        pkColumn: "id",
      }),
    },
  });
  const layer = lastMapConfig().layers[0] as { collectionId?: string; pkColumn?: string };
  expect(layer.collectionId).toBe("parcs");
  expect(layer.pkColumn).toBe("id");
});
