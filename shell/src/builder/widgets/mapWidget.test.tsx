// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange, onFeatureClick }: {
        config: { layers: { url?: string; renderAs?: string; paint?: Record<string, unknown> }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void;
        onFeatureClick?: (record: { id: string | number; properties: Record<string, unknown>; geometry?: unknown }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      const layer = config.layers[0];
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}>
          layers:{config.layers.length} url:{layer?.url ?? ""} renderAs:{layer?.renderAs ?? ""} paint:{JSON.stringify(layer?.paint ?? {})}
          <button
            type="button"
            data-testid="feature"
            onClick={() => onFeatureClick?.({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } })}
          >
            feature
          </button>
        </div>
      );
    },
  ),
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); flyToSpy.mockClear(); highlightSpy.mockClear(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

// Every Component test now needs QueryClientProvider + ItemClientProvider —
// the widget calls useItemClient()/useQuery() unconditionally to fetch a
// color/size domain, same as sliderFilter.tsx/selectFilter.tsx already do.
// Pre-existing tests never configure `encodings`, so those two domain
// queries stay `enabled: false` and `queryDataSource` is never actually
// invoked for them — a bare vi.fn() default is safe.
function withClient(children: React.ReactNode, queryDataSource: ReturnType<typeof vi.fn> = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("registers with a 6x6 default size", () => {
  expect(getWidget("map")!.defaultSize).toEqual({ w: 6, h: 6 });
});

test("PropsPanel edits the color and size encodings", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("map")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{}} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  // Single characters only: props never gets fed back between keystrokes in
  // this test (same convention as pivot.test.tsx's PropsPanel test), so each
  // assertion reflects setEncodings() merging against the still-empty base
  // `props={{}}`, not an accumulated string.
  await userEvent.type(screen.getByLabelText("Champ couleur"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "r", mode: "categorical" } } }));
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "", mode: "numeric" } } }));
  await userEvent.type(screen.getByLabelText("Champ taille"), "m");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { size: { field: "m" } } }));
});

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }) } as WidgetContext;
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
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("mapview"));
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] });
});

test("map flyTo action flies to a selected record's point", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await screen.findByTestId("mapview");
  bus.emit("list1", "itemSelected", { id: 1, properties: {}, geometry: { type: "Point", coordinates: [5, 6] } });
  expect(flyToSpy).toHaveBeenCalledWith({ center: [5, 6], zoom: 12 });
});

test("map emits itemSelected when a feature is clicked", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "itemSelected", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } });
});

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
      <ExtentProbe />
    </AnalyticsContextProvider>,
  ));
  const view = await screen.findByTestId("mapview");
  vi.useFakeTimers();
  try {
    fireEvent.click(view);
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.getByText("extent:10,20,30,40")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value};geom=${JSON.stringify(entry.geometry ?? null)}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  ));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText('cf:id=1;geom={"type":"Point","coordinates":[5,6]}')).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: { loading: false, error: false, records: [], datasetId: "ds1", url: "https://core/collections/geo/items" } } as unknown as WidgetContext;
  render(withClient(<ExplorerProvider enabled><Map props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>));
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("colors features by a categorical field once the domain query resolves", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { groupBy?: string } }) => {
    if (source.query?.groupBy === "region") {
      return [{ id: "Nord", properties: { value: 2 } }, { id: "Sud", properties: { value: 1 } }];
    }
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  await waitFor(() => expect(view.textContent).toContain('"fill-color"'));
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("#2563eb");
  expect(view.textContent).toContain("#dc2626");
});

test("colors and sizes point features by numeric fields once both domain queries resolve", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { measures?: { field: string }[] } }) => {
    const field = source.query?.measures?.[0]?.field;
    if (field === "valeur") return [{ id: "s", properties: { min: 0, max: 100 } }];
    if (field === "montant") return [{ id: "s", properties: { min: 5, max: 25 } }];
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/points/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "valeur", mode: "numeric" }, size: { field: "montant" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  // Both domain queries (color, size) resolve independently — wait for both
  // paint keys inside the same waitFor so a flush of just one doesn't pass
  // the assertion prematurely.
  await waitFor(() => {
    expect(view.textContent).toContain('"circle-radius"');
    expect(view.textContent).toContain('"circle-color"');
  });
  expect(view.textContent).toContain("renderAs:circle");
});

test("shows no symbology legend when no encoding is configured", () => {
  const ctx = { mode: "runtime", data: state({ url: "https://fs/communes/items.json" }) } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  expect(screen.queryByText("Nord")).not.toBeInTheDocument();
});

test("shows a categorical symbology legend once the color domain resolves", async () => {
  const queryDataSource = vi.fn(async () => [{ id: "Nord", properties: { value: 1 } }, { id: "Sud", properties: { value: 1 } }]);
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  expect(await screen.findByText("Nord")).toBeInTheDocument();
  expect(screen.getByText("Sud")).toBeInTheDocument();
});
