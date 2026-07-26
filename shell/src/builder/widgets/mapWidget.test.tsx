// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange, onFeatureClick }: {
        config: { layers: { url?: string }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void;
        onFeatureClick?: (record: { id: string | number; properties: Record<string, unknown>; geometry?: unknown }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}>
          layers:{config.layers.length} url:{config.layers[0]?.url ?? ""}
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

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(<Map props={{ dataSourceId: "d" }} ctx={ctx} />);
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:1");
  expect(view).toHaveTextContent("url:https://fs/parcs/items.json");
});

test("map widget renders an empty map when no source is bound", async () => {
  const Map = getWidget("map")!.Component;
  render(<Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />);
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
  render(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />);
  await userEvent.click(await screen.findByTestId("mapview"));
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] });
});

test("map flyTo action flies to a selected record's point", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Map = getWidget("map")!.Component;
  render(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />);
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
  render(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />);
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } });
});

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
      <ExtentProbe />
    </AnalyticsContextProvider>,
  );
  // Resolve the lazy-loaded MapView's Suspense under real timers first, then
  // switch to fake timers for the debounce. userEvent + fake timers hangs in
  // this environment (see AnalyticsContext.test.tsx); fireEvent + act() is the
  // RTL-sanctioned way to combine a click with fake timers here.
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
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText("cf:id=1")).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: { loading: false, error: false, records: [], datasetId: "ds1", url: "https://core/collections/geo/items" } } as unknown as WidgetContext;
  render(<ExplorerProvider enabled><Map props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>);
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});
