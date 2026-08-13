// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { createRef } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapConfig, MapLayer } from "../api/types";
import { mapInstances } from "../test/MockMaplibreMap";
import { overlayInstances } from "../test/MockDeckgl";
import type { MapViewHandle } from "./MapView";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});
vi.mock("@deck.gl/aggregation-layers", async () => {
  const { HeatmapLayer, HexagonLayer } = await import("../test/MockDeckgl");
  return { HeatmapLayer, HexagonLayer };
});
vi.mock("@deck.gl/layers", async () => {
  const { ColumnLayer } = await import("../test/MockDeckgl");
  return { ColumnLayer };
});
vi.mock("@deck.gl/geo-layers", async () => {
  const { Tile3DLayer } = await import("../test/MockDeckgl");
  return { Tile3DLayer };
});
vi.mock("@loaders.gl/3d-tiles", async () => {
  const { Tiles3DLoader } = await import("../test/MockLoadersGl");
  return { Tiles3DLoader };
});

const { MapView } = await import("./MapView");

beforeEach(() => {
  mapInstances.length = 0;
  overlayInstances.length = 0;
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

test("adds a vector source and fill layer for a vector layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "communes", title: "Communes", visible: true, kind: "vector",
        tilesUrl: "https://martin/communes/{z}/{x}/{y}", sourceLayer: "communes" },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("communes")).toMatchObject({
    spec: { type: "vector", tiles: ["https://martin/communes/{z}/{x}/{y}"] },
  });
  expect(map.getLayer("communes")).toMatchObject({
    type: "fill",
    source: "communes",
    "source-layer": "communes",
  });
});

test("skips non-visible and deck layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "hidden", title: "H", visible: false, kind: "raster", tilesUrl: "u" },
      { id: "deck1", title: "D", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "d" },
      { id: "ras", title: "R", visible: true, kind: "raster", tilesUrl: "https://titiler/{z}/{x}/{y}.png", opacity: 0.5 },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("hidden")).toBeUndefined();
  expect(map.getLayer("deck1")).toBeUndefined();
  expect(map.getLayer("ras")).toMatchObject({ type: "raster", paint: { "raster-opacity": 0.5 } });
});

test("re-applies layers when config.layers changes", () => {
  const first: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  const { rerender } = render(<MapView config={first} />);
  const map = mapInstances[0];
  expect(map.getLayer("a")).toBeDefined();

  const second: MapConfig = {
    ...config,
    layers: [{ id: "b", title: "B", visible: true, kind: "feature", url: "https://fs/b" }],
  };
  rerender(<MapView config={second} />);
  expect(map.getLayer("a")).toBeUndefined();
  expect(map.getLayer("b")).toMatchObject({ type: "fill", source: "b" });
  expect(map.getSource("b")).toMatchObject({ spec: { type: "geojson", data: "https://fs/b" } });
});

test("re-applies layers even while the style has tiles in flight", () => {
  // Same hazard as the terrain effect: the gate must be "the style finished
  // its initial load", not "nothing is loading right now".
  const first: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  const { rerender } = render(<MapView config={first} />);
  const map = mapInstances[0];
  map.styleSettled = false;
  const second: MapConfig = {
    ...config,
    layers: [{ id: "b", title: "B", visible: true, kind: "feature", url: "https://fs/b" }],
  };
  rerender(<MapView config={second} />);
  expect(map.getLayer("a")).toBeUndefined();
  expect(map.getLayer("b")).toBeDefined();
});

test("renders a circle layer for a feature layer with renderAs \"circle\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "pts", title: "Points", visible: true, kind: "feature", url: "https://fs/pts", renderAs: "circle", paint: { "circle-color": "#111" } }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("pts")).toMatchObject({ type: "circle", source: "pts", paint: { "circle-color": "#111" } });
});

test("renders a line layer for a feature layer with renderAs \"line\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "lns", title: "Lignes", visible: true, kind: "feature", url: "https://fs/lns", renderAs: "line" }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("lns")).toMatchObject({ type: "line", source: "lns" });
});

test("defaults a feature layer to fill when renderAs is not set", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "poly", title: "Polygones", visible: true, kind: "feature", url: "https://fs/poly" }],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("poly")).toMatchObject({ type: "fill", source: "poly" });
});

test("reports view changes on moveend", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5, bbox: [0, 0, 0, 0], pitch: 0, bearing: 0 });
});

test("onViewChange includes the current bbox from the map bounds", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].bounds = [[1, 2], [3, 4]];
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5, bbox: [1, 2, 3, 4], pitch: 0, bearing: 0 });
});

test("onViewChange reports the map's current pitch and bearing", () => {
  const onViewChange = vi.fn();
  const cfg: MapConfig = { ...config, view: { center: [2.35, 48.85], zoom: 5, pitch: 40, bearing: 200 } };
  render(<MapView config={cfg} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith(expect.objectContaining({ pitch: 40, bearing: 200 }));
});

test("renders a legend of visible layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "Communes", visible: true, kind: "vector", tilesUrl: "u", sourceLayer: "c" }],
  };
  render(<MapView config={cfg} />);
  // MapLegend renders the title
  expect(document.body.textContent).toContain("Communes");
});

test("hideLegend suppresses the built-in MapLegend", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "Communes", visible: true, kind: "vector", tilesUrl: "u", sourceLayer: "c" }],
  };
  render(<MapView config={cfg} hideLegend />);
  expect(document.body.textContent).not.toContain("Communes");
});

test("mounts a Deck.gl overlay and adds a HeatmapLayer for a heatmap deck layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "heat",
        title: "Heat",
        visible: true,
        kind: "deck",
        deckType: "heatmap",
        dataUrl: "https://fs/points",
        props: { radiusPixels: 30 },
      },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.controls).toContain(overlayInstances[0]);
  expect(overlayInstances).toHaveLength(1);
  const layers = overlayInstances[0].props.layers;
  expect(layers).toHaveLength(1);
  expect(layers[0].deckType).toBe("HeatmapLayer");
  expect(layers[0].props).toMatchObject({
    id: "heat",
    data: "https://fs/points",
    radiusPixels: 30,
  });
});

test("maps hexbin to HexagonLayer and column to ColumnLayer, excluding hidden deck layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "hex", title: "Hex", visible: true, kind: "deck", deckType: "hexbin", dataUrl: "https://fs/a" },
      { id: "col", title: "Col", visible: true, kind: "deck", deckType: "column", dataUrl: "https://fs/b" },
      { id: "off", title: "Off", visible: false, kind: "deck", deckType: "heatmap", dataUrl: "https://fs/c" },
    ],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers.map((l) => l.deckType)).toEqual(["HexagonLayer", "ColumnLayer"]);
  expect(layers.map((l) => l.props.id)).toEqual(["hex", "col"]);
});

test("isolates a failing layer and still renders the others", () => {
  const good1: MapLayer = { id: "ok1", title: "OK1", visible: true, kind: "feature", url: "u1" };
  const bad: MapLayer = { id: "bad", title: "BAD", visible: true, kind: "feature", url: "u2" };
  const good2: MapLayer = { id: "ok2", title: "OK2", visible: true, kind: "feature", url: "u3" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good1] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("bad");
  rerender(<MapView config={{ ...config, layers: [good1, bad, good2] }} />);
  expect(map.getLayer("ok1")).toBeDefined();
  expect(map.getLayer("ok2")).toBeDefined();
  expect(map.getLayer("bad")).toBeUndefined();
});

test("re-applies deck layers when config.layers changes", () => {
  const first: MapConfig = {
    ...config,
    layers: [{ id: "d1", title: "D1", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "https://fs/1" }],
  };
  const { rerender } = render(<MapView config={first} />);
  const overlay = overlayInstances[0];
  expect(overlay.props.layers.map((l) => l.props.id)).toEqual(["d1"]);

  const second: MapConfig = {
    ...config,
    layers: [{ id: "d2", title: "D2", visible: true, kind: "deck", deckType: "column", dataUrl: "https://fs/2" }],
  };
  rerender(<MapView config={second} />);
  expect(overlay.props.layers.map((l) => l.props.id)).toEqual(["d2"]);
  expect(overlay.props.layers[0].deckType).toBe("ColumnLayer");
});

test("exposes an imperative flyTo that drives the map", () => {
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  ref.current!.flyTo({ center: [5, 6], zoom: 12 });
  expect(mapInstances[0].flyToArgs).toContainEqual({ center: [5, 6], zoom: 12 });
});

test("highlight sets the highlight source data and clears it on null", () => {
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  const map = mapInstances[0];
  ref.current!.highlight({ type: "Point", coordinates: [1, 2] });
  expect(map.getSource("__highlight__")).toMatchObject({
    spec: { data: { type: "Feature", geometry: { type: "Point", coordinates: [1, 2] } } },
  });
  ref.current!.highlight(null);
  expect(map.getSource("__highlight__")).toMatchObject({
    spec: { data: { type: "FeatureCollection", features: [] } },
  });
});

test("emits a feature click via onFeatureClick", () => {
  const onFeatureClick = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  render(<MapView config={cfg} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "a", {
    features: [{ id: 7, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } }],
  });
  expect(onFeatureClick).toHaveBeenCalledWith({
    id: 7,
    properties: { nom: "Parc A" },
    geometry: { type: "Point", coordinates: [1, 2] },
  });
});

test("does nothing when a click event carries no features", () => {
  const onFeatureClick = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  render(<MapView config={cfg} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "a", { features: [] });
  expect(onFeatureClick).not.toHaveBeenCalled();
});

test("ignores a clicked feature with no id", () => {
  const onFeatureClick = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  render(<MapView config={cfg} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "a", { features: [{ properties: { nom: "Parc A" }, geometry: null }] });
  expect(onFeatureClick).not.toHaveBeenCalled();
});

test("calls onReady once the map fires 'idle'", () => {
  const onReady = vi.fn();
  render(<MapView config={config} onReady={onReady} />);
  const map = mapInstances[0];
  map.fire("idle");
  expect(onReady).toHaveBeenCalledTimes(1);
});

test("does not call onReady before 'idle' fires", () => {
  const onReady = vi.fn();
  render(<MapView config={config} onReady={onReady} />);
  expect(onReady).not.toHaveBeenCalled();
});

test("only calls onReady once even if 'idle' fires again (map.once semantics)", () => {
  const onReady = vi.fn();
  render(<MapView config={config} onReady={onReady} />);
  const map = mapInstances[0];
  map.fire("idle");
  map.fire("idle");
  expect(onReady).toHaveBeenCalledTimes(1);
});

test("detaches the old layer's click handler when config.layers replaces it", () => {
  const onFeatureClick = vi.fn();
  const first: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  const { rerender } = render(<MapView config={first} onFeatureClick={onFeatureClick} />);
  const map = mapInstances[0];
  const second: MapConfig = {
    ...config,
    layers: [{ id: "b", title: "B", visible: true, kind: "feature", url: "https://fs/b" }],
  };
  rerender(<MapView config={second} onFeatureClick={onFeatureClick} />);
  map.fireOnLayer("click", "a", { features: [{ id: 1, properties: {}, geometry: null }] });
  expect(onFeatureClick).not.toHaveBeenCalled();
  map.fireOnLayer("click", "b", { features: [{ id: 2, properties: {}, geometry: null }] });
  expect(onFeatureClick).toHaveBeenCalledWith({ id: 2, properties: {}, geometry: null });
});

test("initializes the map with pitch and bearing from the view", () => {
  const cfg: MapConfig = { ...config, view: { center: [2.35, 48.85], zoom: 5, pitch: 30, bearing: 120 } };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].opts.pitch).toBe(30);
  expect(mapInstances[0].opts.bearing).toBe(120);
});

test("defaults pitch and bearing to 0 when absent from the view", () => {
  render(<MapView config={config} />);
  expect(mapInstances[0].opts.pitch).toBe(0);
  expect(mapInstances[0].opts.bearing).toBe(0);
});

test("mounts a Tile3DLayer for a visible tiles3d layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers).toHaveLength(1);
  expect(layers[0].deckType).toBe("Tile3DLayer");
  expect(layers[0].props).toMatchObject({ id: "bldg", data: "https://example.test/tileset.json" });
});

test("excludes a hidden tiles3d layer from the overlay", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: false, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(overlayInstances[0].props.layers).toHaveLength(0);
});

test("skips tiles3d layers in the MapLibre-native layer path", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("bldg")).toBeUndefined();
});

test("shows a tiles3d layer's title in the legend", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(document.body.textContent).toContain("Bâtiments");
});

test("enables terrain on load when config.terrain is present", () => {
  const cfg: MapConfig = {
    ...config,
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1.5 },
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { type: "raster-dem", tiles: ["https://example.test/dem/{z}/{x}/{y}.png"], encoding: "terrarium" },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1.5 });
});

test("defaults terrain exaggeration to 1 when not specified", () => {
  const cfg: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" } };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].terrain).toEqual({ source: "__terrain__", exaggeration: 1 });
});

test("removes terrain when config.terrain is cleared", () => {
  const withTerrain: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" } };
  const { rerender } = render(<MapView config={withTerrain} />);
  expect(mapInstances[0].terrain).not.toBeNull();
  rerender(<MapView config={{ ...config, terrain: null }} />);
  expect(mapInstances[0].terrain).toBeNull();
  expect(mapInstances[0].getSource("__terrain__")).toBeUndefined();
});

test("does not build a terrain source while the DEM URL is still blank", () => {
  // TerrainPanel emits { tilesUrl: "" } the instant the box is ticked.
  const cfg: MapConfig = { ...config, terrain: { tilesUrl: "   ", encoding: "terrarium", exaggeration: 1 } };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getSource("__terrain__")).toBeUndefined();
  expect(mapInstances[0].terrain).toBeNull();
});

test("picks up a terrain tilesUrl typed after the terrain was enabled, without a remount", () => {
  // Regression: the reactive [config.terrain] effect used to be gated on
  // map.isStyleLoaded(), which the blank-URL source's failing tile requests
  // kept false — so the real URL never reached MapLibre.
  const blank: MapConfig = { ...config, terrain: { tilesUrl: "", encoding: "terrarium", exaggeration: 1 } };
  const { rerender } = render(<MapView config={blank} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toBeUndefined();
  // Whatever else the map has in flight at this moment must not swallow the
  // author's edit.
  map.styleSettled = false;

  const typed: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1 } };
  rerender(<MapView config={typed} />);
  expect(mapInstances).toHaveLength(1); // same map instance: no remount
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { type: "raster-dem", tiles: ["https://example.test/dem/{z}/{x}/{y}.png"] },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1 });

  const changed: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/other/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 2 } };
  rerender(<MapView config={changed} />);
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { tiles: ["https://example.test/other/{z}/{x}/{y}.png"] },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 2 });
});

test("applies terrain and a tiles3d layer together without interfering", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1.5 },
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { type: "raster-dem", tiles: ["https://example.test/dem/{z}/{x}/{y}.png"] },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1.5 });
  const layers = overlayInstances[0].props.layers;
  expect(layers).toHaveLength(1);
  expect(layers[0].deckType).toBe("Tile3DLayer");
  expect(layers[0].props).toMatchObject({ id: "bldg", data: "https://example.test/tileset.json" });
});

test("mounts the Deck.gl overlay in interleaved mode", () => {
  render(<MapView config={config} />);
  expect(overlayInstances[0].constructorProps.interleaved).toBe(true);
});

function fireTilesetLoad(layerIndex = 0) {
  const layer = overlayInstances[0].props.layers[layerIndex];
  (layer.props.onTilesetLoad as () => void)();
}

test("holds onReady until a tiles3d layer's tileset has loaded", () => {
  const onReady = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} onReady={onReady} />);
  mapInstances[0].fire("idle");
  expect(onReady).not.toHaveBeenCalled();
  fireTilesetLoad();
  expect(onReady).toHaveBeenCalledTimes(1);
});

test("does not call onReady on tileset load alone, before the map is idle", () => {
  const onReady = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} onReady={onReady} />);
  fireTilesetLoad();
  expect(onReady).not.toHaveBeenCalled();
  mapInstances[0].fire("idle");
  expect(onReady).toHaveBeenCalledTimes(1);
});

test("waits for every visible tiles3d tileset before onReady", () => {
  const onReady = vi.fn();
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "a", title: "A", visible: true, kind: "tiles3d", url: "https://example.test/a.json" },
      { id: "b", title: "B", visible: true, kind: "tiles3d", url: "https://example.test/b.json" },
      { id: "off", title: "Off", visible: false, kind: "tiles3d", url: "https://example.test/off.json" },
    ],
  };
  render(<MapView config={cfg} onReady={onReady} />);
  mapInstances[0].fire("idle");
  fireTilesetLoad(0);
  expect(onReady).not.toHaveBeenCalled();
  fireTilesetLoad(1);
  expect(onReady).toHaveBeenCalledTimes(1);
});

test("attaches a bearer token to a hosted (/tileset3d/) tiles3d layer's requests", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://core.test/tileset3d/item-1/tileset.json" }],
  };
  render(<MapView config={cfg} getAuthToken={() => "secret-token"} getCoreUrl={() => "https://core.test"} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toEqual({ fetch: { headers: { Authorization: "Bearer secret-token" } } });
});

test("does not attach a bearer token to an external tiles3d layer even when getAuthToken is provided", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} getAuthToken={() => "secret-token"} getCoreUrl={() => "https://core.test"} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("does not attach a bearer token when the URL merely contains /tileset3d/ on a different origin", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://attacker.test/x/tileset3d/y/tileset.json" }],
  };
  render(<MapView config={cfg} getAuthToken={() => "secret-token"} getCoreUrl={() => "https://core.test"} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("does not attach a header for a hosted tileset when getAuthToken is absent", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://core.test/tileset3d/item-1/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});
