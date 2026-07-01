import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapConfig } from "../api/types";
import { mapInstances } from "../test/MockMaplibreMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

const { MapView } = await import("./MapView");

beforeEach(() => {
  mapInstances.length = 0;
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.35, 48.85], zoom: 5 },
  layers: [],
};

test("initializes a MapLibre map with the basemap and view", () => {
  render(<MapView config={config} />);
  expect(mapInstances).toHaveLength(1);
  expect(mapInstances[0].opts.style).toBe("https://demotiles.maplibre.org/style.json");
  expect(mapInstances[0].opts.center).toEqual([2.35, 48.85]);
  expect(mapInstances[0].opts.zoom).toBe(5);
});

test("removes the map on unmount", () => {
  const { unmount } = render(<MapView config={config} />);
  const map = mapInstances[0];
  unmount();
  expect(map.removed).toBe(true);
});
