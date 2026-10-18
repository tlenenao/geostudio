// SPDX-License-Identifier: Apache-2.0
// AUD-051 : filtre par couche — compilation et pose sur les sous-couches (hors clusters).
import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapConfig } from "../api/types";
import { mapInstances } from "../test/MockMaplibreMap";
import { compileLayerFilter, applyLayerFilter } from "./layerFilter";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  class ScaleControl {}
  return { Map: MockMap, ScaleControl, setWorkerUrl: () => {} };
});
vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});

const { MapView } = await import("./MapView");

beforeEach(() => {
  mapInstances.length = 0;
});

test("compile eq/in en expression MapLibre, vide -> null", () => {
  expect(compileLayerFilter([])).toBeNull();
  expect(
    compileLayerFilter([
      { field: "pop", op: "gte", value: 100 },
      { field: "type", op: "in", value: ["a", "b"] },
    ]),
  ).toEqual(["all", [">=", ["get", "pop"], 100], ["in", ["get", "type"], ["literal", ["a", "b"]]]]);
});

test("le filtre est posé sur chaque sous-couche de la couche, en ET avec le filtre existant", () => {
  const config: MapConfig = {
    basemap: { style: "https://demotiles.maplibre.org/style.json" },
    view: { center: [2.35, 48.85], zoom: 5 },
    layers: [
      {
        id: "communes",
        title: "Communes",
        visible: true,
        kind: "vector",
        tilesUrl: "https://core/tiles/{z}/{x}/{y}.mvt",
        sourceLayer: "communes",
        filter: [{ field: "pop", op: "gt", value: 5000 }],
      },
    ],
  };
  render(<MapView config={config} />);
  const subs = mapInstances[0].layers.filter((l) => l.id.startsWith("communes"));
  expect(subs.length).toBeGreaterThan(1);
  for (const l of subs) {
    expect(JSON.stringify(mapInstances[0].getFilter(l.id))).toContain('[">",["get","pop"],5000]');
  }
  expect(applyLayerFilter).toBeTypeOf("function");
});
