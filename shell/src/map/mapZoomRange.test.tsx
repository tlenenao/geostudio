// SPDX-License-Identifier: Apache-2.0
// AUD-051 : plage d'échelle (minZoom/maxZoom) par couche, sous-couches comprises.
import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapConfig } from "../api/types";
import { mapInstances } from "../test/MockMaplibreMap";

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

const base: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.35, 48.85], zoom: 5 },
  layers: [],
};

function layerRange(id: string) {
  return mapInstances[0].getLayer(id) as { minzoom?: number; maxzoom?: number } | undefined;
}

test("minZoom/maxZoom sont posés sur la couche et ses sous-couches", () => {
  render(
    <MapView
      config={{
        ...base,
        layers: [
          {
            id: "communes",
            title: "Communes",
            visible: true,
            kind: "vector",
            tilesUrl: "https://core/tiles/{z}/{x}/{y}.mvt",
            sourceLayer: "communes",
            minZoom: 6,
            maxZoom: 12,
          },
        ],
      }}
    />,
  );
  const ids = mapInstances[0].layers.map((l) => l.id).filter((id) => id.startsWith("communes"));
  expect(ids.length).toBeGreaterThan(1); // géométrie inconnue : trois sous-couches
  for (const id of ids) expect(layerRange(id)).toMatchObject({ minzoom: 6, maxzoom: 12 });
});

test("sans plage, aucune borne n'est imposée", () => {
  render(
    <MapView
      config={{
        ...base,
        layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
      }}
    />,
  );
  expect(layerRange("a")?.minzoom).toBeUndefined();
});
