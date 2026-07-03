import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange }: {
        config: { layers: { url?: string }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9 })}>
          layers:{config.layers.length} url:{config.layers[0]?.url ?? ""}
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

test("map declares extentChanged event and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toContain("extentChanged");
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
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9 });
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
