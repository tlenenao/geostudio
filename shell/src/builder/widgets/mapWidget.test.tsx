import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";

vi.mock("../../map/MapView", () => ({
  MapView: ({ config }: { config: { layers: { url?: string }[] } }) => (
    <div data-testid="mapview">layers:{config.layers.length} url:{config.layers[0]?.url ?? ""}</div>
  ),
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
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
