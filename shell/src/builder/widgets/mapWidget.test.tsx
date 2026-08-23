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
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      lastConfig = config;
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      const layer = config.layers[0];

      const url = layer && "url" in layer ? ((layer as any).url ?? "") : "";

      const renderAs = layer && "renderAs" in layer ? ((layer as any).renderAs ?? "") : "";

      const paint = layer && "paint" in layer ? JSON.stringify((layer as any).paint ?? {}) : "{}";
      return (
        <div
          data-testid="mapview"
          onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}
        >
          layers:{config.layers.length} url:{url} renderAs:{renderAs} paint:{paint}
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
  onChange: ReturnType<typeof vi.fn>;

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

test("Component renders paint from frozen props.symbology, without querying any domain", async () => {
  const queryDataSource = vi.fn();
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
      queryDataSource,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain('"fill-color"');
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("#2563eb");
  expect(view.textContent).toContain("#dc2626");
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("colors and sizes point features from frozen size/color symbology, without querying any domain", async () => {
  const queryDataSource = vi.fn();
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/points/items.json",
      records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
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
        ctx={ctx}
      />,
      queryDataSource,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain('"circle-radius"');
  expect(view.textContent).toContain('"circle-color"');
  expect(view.textContent).toContain("renderAs:circle");
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("Component resolves the theme-primary palette from ctx.theme at render time", async () => {
  const ctx = {
    mode: "runtime",
    theme: { colors: { primary: "#2563eb" } },
    data: state({
      url: "https://fs/points/items.json",
      records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
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
              field: "valeur",
              mode: "numeric",
              palette: "theme-primary",
              domain: { kind: "numeric", min: 0, max: 100 },
              computedAt: "2026-08-23T10:00:00Z",
            },
          },
        }}
        ctx={ctx}
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  // The interpolate expression's high stop must be the resolved
  // theme-primary color, not one of the hardcoded palette defaults
  // (sequential-blue's "#1e3a8a" or the raw NUMERIC_COLOR_HIGH default) —
  // this is exactly the bug this plan's Task 10 self-review caught: without
  // ctx.theme threaded through symbologyToPaintInputs, this would silently
  // render the wrong colors instead.
  expect(view.textContent).toContain('"#2563eb"]}');
  expect(view.textContent).not.toContain("#1e3a8a");
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
