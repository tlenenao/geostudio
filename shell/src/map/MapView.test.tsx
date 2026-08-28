// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      {
        id: "communes",
        title: "Communes",
        visible: true,
        kind: "vector",
        tilesUrl: "https://martin/communes/{z}/{x}/{y}",
        sourceLayer: "communes",
        geometryKind: "polygon",
      },
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
      {
        id: "ras",
        title: "R",
        visible: true,
        kind: "raster",
        tilesUrl: "https://titiler/{z}/{x}/{y}.png",
        opacity: 0.5,
      },
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

test('renders a circle layer for a feature layer with renderAs "circle"', () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "pts",
        title: "Points",
        visible: true,
        kind: "feature",
        url: "https://fs/pts",
        renderAs: "circle",
        paint: { "circle-color": "#111" },
      },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("pts")).toMatchObject({
    type: "circle",
    source: "pts",
    paint: { "circle-color": "#111" },
  });
});

test('renders a line layer for a feature layer with renderAs "line"', () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "lns",
        title: "Lignes",
        visible: true,
        kind: "feature",
        url: "https://fs/lns",
        renderAs: "line",
      },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("lns")).toMatchObject({ type: "line", source: "lns" });
});

test("defaults a feature layer to fill when renderAs is not set", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "poly", title: "Polygones", visible: true, kind: "feature", url: "https://fs/poly" },
    ],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("poly")).toMatchObject({ type: "fill", source: "poly" });
});

test("a layer with symbology renders paint compiled from its frozen domain, ignoring any stale raw paint", () => {
  const layer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "feature",
    url: "u",
    paint: { "fill-color": "#000000" }, // stale/irrelevant once symbology is present
    symbology: {
      color: {
        field: "pop",
        mode: "numeric",
        palette: "sequential-blue",
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: "2026-08-23T00:00:00Z",
      },
    },
  };
  const cfg: MapConfig = { ...config, layers: [layer] };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("l1")).toMatchObject({
    type: "fill",
    source: "l1",
    paint: {
      "fill-color": ["interpolate", ["linear"], ["get", "pop"], 0, "#dbeafe", 100, "#1e3a8a"],
    },
  });
});

test("reports view changes on moveend", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({
    center: [2.35, 48.85],
    zoom: 5,
    bbox: [0, 0, 0, 0],
    pitch: 0,
    bearing: 0,
  });
});

test("onViewChange includes the current bbox from the map bounds", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].bounds = [
    [1, 2],
    [3, 4],
  ];
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({
    center: [2.35, 48.85],
    zoom: 5,
    bbox: [1, 2, 3, 4],
    pitch: 0,
    bearing: 0,
  });
});

test("onViewChange reports the map's current pitch and bearing", () => {
  const onViewChange = vi.fn();
  const cfg: MapConfig = {
    ...config,
    view: { center: [2.35, 48.85], zoom: 5, pitch: 40, bearing: 200 },
  };
  render(<MapView config={cfg} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith(expect.objectContaining({ pitch: 40, bearing: 200 }));
});

test("renders a legend of visible layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "a",
        title: "Communes",
        visible: true,
        kind: "vector",
        tilesUrl: "u",
        sourceLayer: "c",
      },
    ],
  };
  render(<MapView config={cfg} />);
  // MapLegend renders the title
  expect(document.body.textContent).toContain("Communes");
});

test("hideLegend suppresses the built-in MapLegend", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "a",
        title: "Communes",
        visible: true,
        kind: "vector",
        tilesUrl: "u",
        sourceLayer: "c",
      },
    ],
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
      {
        id: "hex",
        title: "Hex",
        visible: true,
        kind: "deck",
        deckType: "hexbin",
        dataUrl: "https://fs/a",
      },
      {
        id: "col",
        title: "Col",
        visible: true,
        kind: "deck",
        deckType: "column",
        dataUrl: "https://fs/b",
      },
      {
        id: "off",
        title: "Off",
        visible: false,
        kind: "deck",
        deckType: "heatmap",
        dataUrl: "https://fs/c",
      },
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
    layers: [
      {
        id: "d1",
        title: "D1",
        visible: true,
        kind: "deck",
        deckType: "heatmap",
        dataUrl: "https://fs/1",
      },
    ],
  };
  const { rerender } = render(<MapView config={first} />);
  const overlay = overlayInstances[0];
  expect(overlay.props.layers.map((l) => l.props.id)).toEqual(["d1"]);

  const second: MapConfig = {
    ...config,
    layers: [
      {
        id: "d2",
        title: "D2",
        visible: true,
        kind: "deck",
        deckType: "column",
        dataUrl: "https://fs/2",
      },
    ],
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
    features: [
      { id: 7, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
    ],
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
  mapInstances[0].fireOnLayer("click", "a", {
    features: [{ properties: { nom: "Parc A" }, geometry: null }],
  });
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
  const cfg: MapConfig = {
    ...config,
    view: { center: [2.35, 48.85], zoom: 5, pitch: 30, bearing: 120 },
  };
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
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
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
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: false,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
  };
  render(<MapView config={cfg} />);
  expect(overlayInstances[0].props.layers).toHaveLength(0);
});

test("skips tiles3d layers in the MapLibre-native layer path", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("bldg")).toBeUndefined();
});

test("shows a tiles3d layer's title in the legend", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
  };
  render(<MapView config={cfg} />);
  expect(document.body.textContent).toContain("Bâtiments");
});

test("enables terrain on load when config.terrain is present", () => {
  const cfg: MapConfig = {
    ...config,
    terrain: {
      tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
      encoding: "terrarium",
      exaggeration: 1.5,
    },
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: {
      type: "raster-dem",
      tiles: ["https://example.test/dem/{z}/{x}/{y}.png"],
      encoding: "terrarium",
    },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1.5 });
});

test("defaults terrain exaggeration to 1 when not specified", () => {
  const cfg: MapConfig = {
    ...config,
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" },
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].terrain).toEqual({ source: "__terrain__", exaggeration: 1 });
});

test("removes terrain when config.terrain is cleared", () => {
  const withTerrain: MapConfig = {
    ...config,
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" },
  };
  const { rerender } = render(<MapView config={withTerrain} />);
  expect(mapInstances[0].terrain).not.toBeNull();
  rerender(<MapView config={{ ...config, terrain: null }} />);
  expect(mapInstances[0].terrain).toBeNull();
  expect(mapInstances[0].getSource("__terrain__")).toBeUndefined();
});

test("does not build a terrain source while the DEM URL is still blank", () => {
  // TerrainPanel emits { tilesUrl: "" } the instant the box is ticked.
  const cfg: MapConfig = {
    ...config,
    terrain: { tilesUrl: "   ", encoding: "terrarium", exaggeration: 1 },
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getSource("__terrain__")).toBeUndefined();
  expect(mapInstances[0].terrain).toBeNull();
});

test("picks up a terrain tilesUrl typed after the terrain was enabled, without a remount", () => {
  // Regression: the reactive [config.terrain] effect used to be gated on
  // map.isStyleLoaded(), which the blank-URL source's failing tile requests
  // kept false — so the real URL never reached MapLibre.
  const blank: MapConfig = {
    ...config,
    terrain: { tilesUrl: "", encoding: "terrarium", exaggeration: 1 },
  };
  const { rerender } = render(<MapView config={blank} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toBeUndefined();
  // Whatever else the map has in flight at this moment must not swallow the
  // author's edit.
  map.styleSettled = false;

  const typed: MapConfig = {
    ...config,
    terrain: {
      tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
      encoding: "terrarium",
      exaggeration: 1,
    },
  };
  rerender(<MapView config={typed} />);
  expect(mapInstances).toHaveLength(1); // same map instance: no remount
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { type: "raster-dem", tiles: ["https://example.test/dem/{z}/{x}/{y}.png"] },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1 });

  const changed: MapConfig = {
    ...config,
    terrain: {
      tilesUrl: "https://example.test/other/{z}/{x}/{y}.png",
      encoding: "terrarium",
      exaggeration: 2,
    },
  };
  rerender(<MapView config={changed} />);
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { tiles: ["https://example.test/other/{z}/{x}/{y}.png"] },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 2 });
});

test("applies terrain and a tiles3d layer together without interfering", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
    terrain: {
      tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
      encoding: "terrarium",
      exaggeration: 1.5,
    },
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
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
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
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
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
      {
        id: "off",
        title: "Off",
        visible: false,
        kind: "tiles3d",
        url: "https://example.test/off.json",
      },
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
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://core.test/tileset3d/item-1/tileset.json",
      },
    ],
  };
  render(
    <MapView
      config={cfg}
      getAuthToken={() => "secret-token"}
      getCoreUrl={() => "https://core.test"}
    />,
  );
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toEqual({
    fetch: { headers: { Authorization: "Bearer secret-token" } },
  });
});

test("does not attach a bearer token to an external tiles3d layer even when getAuthToken is provided", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://example.test/tileset.json",
      },
    ],
  };
  render(
    <MapView
      config={cfg}
      getAuthToken={() => "secret-token"}
      getCoreUrl={() => "https://core.test"}
    />,
  );
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("does not attach a bearer token when the URL merely contains /tileset3d/ on a different origin", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://attacker.test/x/tileset3d/y/tileset.json",
      },
    ],
  };
  render(
    <MapView
      config={cfg}
      getAuthToken={() => "secret-token"}
      getCoreUrl={() => "https://core.test"}
    />,
  );
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("does not attach a header for a hosted tileset when getAuthToken is absent", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "bldg",
        title: "Bâtiments",
        visible: true,
        kind: "tiles3d",
        url: "https://core.test/tileset3d/item-1/tileset.json",
      },
    ],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("transformRequest attaches a bearer token to a hosted (/terrain3d/) terrain tile request", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  const cfg: MapConfig = {
    ...config,
    terrain: {
      tilesUrl: "https://core.test/terrain3d/item-1/tiles/{z}/{x}/{y}.png",
      encoding: "terrarium",
    },
  };
  render(<MapView config={cfg} getAuthToken={getAuthToken} getCoreUrl={getCoreUrl} />);
  const transformRequest = mapInstances[0].opts.transformRequest!;
  const result = transformRequest("https://core.test/terrain3d/item-1/tiles/5/10/12.png", "Tile");
  expect(result).toEqual({
    url: "https://core.test/terrain3d/item-1/tiles/5/10/12.png",
    headers: { Authorization: "Bearer secret-token" },
  });
});

test("transformRequest does not attach a bearer token to an external terrain URL", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  const cfg: MapConfig = {
    ...config,
    terrain: { tilesUrl: "https://terrain.example/{z}/{x}/{y}.png", encoding: "terrarium" },
  };
  render(<MapView config={cfg} getAuthToken={getAuthToken} getCoreUrl={getCoreUrl} />);
  const transformRequest = mapInstances[0].opts.transformRequest!;
  const result = transformRequest("https://terrain.example/5/10/12.png", "Tile");
  expect(result).toEqual({ url: "https://terrain.example/5/10/12.png" });
});

test("transformRequest does not leak the token when the URL merely contains /terrain3d/ on a different origin", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  const cfg: MapConfig = {
    ...config,
    terrain: {
      tilesUrl: "https://attacker.test/x/terrain3d/y/tiles/{z}/{x}/{y}.png",
      encoding: "terrarium",
    },
  };
  render(<MapView config={cfg} getAuthToken={getAuthToken} getCoreUrl={getCoreUrl} />);
  const transformRequest = mapInstances[0].opts.transformRequest!;
  const result = transformRequest("https://attacker.test/x/terrain3d/y/tiles/5/10/12.png", "Tile");
  expect(result).toEqual({ url: "https://attacker.test/x/terrain3d/y/tiles/5/10/12.png" });
});

const tiled = (extra: Partial<Extract<MapLayer, { kind: "vector" }>> = {}) => ({
  ...config,
  layers: [
    {
      id: "communes",
      title: "Communes",
      visible: true,
      kind: "vector" as const,
      tilesUrl: "http://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
      sourceLayer: "communes",
      collectionId: "communes",
      ...extra,
    },
  ],
});

test("a tiled point collection is rendered as circles, not as a fill", () => {
  render(<MapView config={tiled({ geometryKind: "point" })} />);
  expect(mapInstances[0].getLayer("communes")).toMatchObject({ type: "circle" });
});

test("a tiled line collection is rendered as lines", () => {
  render(<MapView config={tiled({ geometryKind: "line" })} />);
  expect(mapInstances[0].getLayer("communes")).toMatchObject({ type: "line" });
});

// I1 de la revue finale SP-24 : `geometryKind` absent (géométrie inconnue ou
// mixte côté PostGIS, ex. Point + MultiPoint dans la même colonne) posait un
// unique layer "fill" — une couche de points ou de lignes ne rendait alors
// RIEN, silencieusement. La couche pose désormais trois sous-couches
// typées, chacune filtrée par type de géométrie réel de l'entité.
test("a tiled layer without geometryKind renders three typed sub-layers, not a single fill", () => {
  render(<MapView config={tiled()} />);
  const map = mapInstances[0];
  expect(map.getLayer("communes")).toBeUndefined();
  expect(map.getLayer("communes__point")).toMatchObject({
    type: "circle",
    source: "communes",
    "source-layer": "communes",
    filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
  });
  expect(map.getLayer("communes__line")).toMatchObject({
    type: "line",
    filter: ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false],
  });
  expect(map.getLayer("communes__polygon")).toMatchObject({
    type: "fill",
    filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
  });
});

test("a mixed-geometry layer's paint is split by prefix across its sub-layers", () => {
  render(
    <MapView
      config={tiled({
        paint: { "circle-color": "red", "line-color": "blue", "fill-color": "green", stray: "x" },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.getLayer("communes__point")).toMatchObject({ paint: { "circle-color": "red" } });
  expect(map.getLayer("communes__line")).toMatchObject({ paint: { "line-color": "blue" } });
  expect(map.getLayer("communes__polygon")).toMatchObject({ paint: { "fill-color": "green" } });
});

test("clicking any mixed-geometry sub-layer reports the same feature, keyed by the layer's own id", () => {
  const onFeatureClick = vi.fn();
  render(<MapView config={tiled()} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "communes__point", {
    features: [{ id: 7, properties: { nom: "Tulle" }, geometry: { type: "Point" } }],
    lngLat: { lng: 1, lat: 2 },
  });
  expect(onFeatureClick).toHaveBeenCalledWith(
    expect.objectContaining({ id: 7, properties: { nom: "Tulle" } }),
  );
});

test("clicking a mixed-geometry sub-layer opens the popup declared on the layer, not on the sub-layer", () => {
  render(<MapView config={tiled({ popup: { titleField: "nom" } })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes__polygon", clickPayload));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText("Tulle")).toBeInTheDocument();
});

// I4 de la revue finale SP-25 : `effectivePaint` calculait un seul paint
// pour "polygon" puis le filtrait par préfixe — les sous-couches
// point/ligne d'une géométrie mixte/inconnue recevaient donc un paint vide
// (non stylé) au lieu de leur propre expression compilée pour LEUR
// géométrie réelle.
test("a mixed-geometry symbologized layer compiles distinct paint per sub-layer geometry, not just polygon", () => {
  render(
    <MapView
      config={tiled({
        symbology: {
          color: {
            field: "categorie",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A", "B"] },
            computedAt: "2026-08-23T00:00:00Z",
          },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  const expectedMatch = ["match", ["get", "categorie"], "A", "#2563eb", "B", "#dc2626", "#2563eb"];
  expect(map.getLayer("communes__point")).toMatchObject({
    paint: { "circle-color": expectedMatch },
  });
  expect(map.getLayer("communes__line")).toMatchObject({
    paint: { "line-color": expectedMatch },
  });
  expect(map.getLayer("communes__polygon")).toMatchObject({
    paint: { "fill-color": expectedMatch },
  });
});

test("removing a mixed-geometry layer detaches all three sub-layer click handlers", () => {
  const { rerender } = render(<MapView config={tiled()} />);
  rerender(<MapView config={config} />);
  const map = mapInstances[0];
  expect(map.layerHandlers["click:communes__point"] ?? []).toHaveLength(0);
  expect(map.layerHandlers["click:communes__line"] ?? []).toHaveLength(0);
  expect(map.layerHandlers["click:communes__polygon"] ?? []).toHaveLength(0);
  expect(map.getLayer("communes__point")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
});

test("a failing mixed-geometry sub-layer rolls back its siblings instead of orphaning the source", () => {
  const good: MapLayer = { id: "ok", title: "OK", visible: true, kind: "feature", url: "u1" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("communes__line");
  rerender(<MapView config={{ ...config, layers: [good, ...tiled().layers] }} />);
  expect(map.getLayer("communes__point")).toBeUndefined();
  expect(map.getLayer("communes__polygon")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
  expect(map.getLayer("ok")).toBeDefined();
});

test("clicking a tiled feature reports it, like a geojson one", () => {
  const onFeatureClick = vi.fn();
  render(<MapView config={tiled({ geometryKind: "polygon" })} onFeatureClick={onFeatureClick} />);
  mapInstances[0].fireOnLayer("click", "communes", {
    features: [{ id: 7, properties: { nom: "Tulle" }, geometry: { type: "Point" } }],
    lngLat: { lng: 1, lat: 2 },
  });
  expect(onFeatureClick).toHaveBeenCalledWith(
    expect.objectContaining({ id: 7, properties: { nom: "Tulle" } }),
  );
});

test("a tiled feature with a text primary key falls back to the pk property", () => {
  // ST_AsMVT ne pose un feature id que sur une PK entière (core/app/features/
  // tiles.py) : sans repli, une collection à PK texte serait inerte.
  const onFeatureClick = vi.fn();
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", pkColumn: "code" })}
      onFeatureClick={onFeatureClick}
    />,
  );
  mapInstances[0].fireOnLayer("click", "communes", {
    features: [{ id: null, properties: { code: "19272", nom: "Tulle" } }],
    lngLat: { lng: 1, lat: 2 },
  });
  expect(onFeatureClick).toHaveBeenCalledWith(expect.objectContaining({ id: "19272" }));
});

test("the click handler of a removed tiled layer is detached", () => {
  const { rerender } = render(<MapView config={tiled({ geometryKind: "polygon" })} />);
  rerender(<MapView config={config} />);
  expect(mapInstances[0].layerHandlers["click:communes"] ?? []).toHaveLength(0);
});

test("core collection tile requests carry the session bearer token", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "http://core.test"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("http://core.test/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "http://core.test/collections/communes/tiles/1/2/3.mvt",
    headers: { Authorization: "Bearer tok" },
  });
});

test("an external url that merely looks like ours gets no token", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "http://core.test"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("https://attacker.test/collections/x/tiles/1/2/3.mvt")).toEqual({
    url: "https://attacker.test/collections/x/tiles/1/2/3.mvt",
  });
});

// C1 de la revue finale SP-24 : docker-compose.prod.yml pose
// VITE_CORE_URL="https://hôte/api" — une vraie URL de tuile en production est
// donc "/api/collections/…", jamais "/collections/…" tout court. Sans le
// chemin de base dans la comparaison, le jeton ne s'attachait jamais en prod.
test("a tile url under the core API's base path carries the session bearer token", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        tilesUrl: "https://hote.test/api/collections/communes/tiles/{z}/{x}/{y}.mvt",
      })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "https://hote.test/api"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  expect(t("https://hote.test/api/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "https://hote.test/api/collections/communes/tiles/1/2/3.mvt",
    headers: { Authorization: "Bearer tok" },
  });
});

test("a same-origin url outside the core API's base path gets no token", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon" })}
      getAuthToken={() => "tok"}
      getCoreUrl={() => "https://hote.test/api"}
    />,
  );
  const t = mapInstances[0].opts.transformRequest!;
  // Même origine que le cœur, mais hors du chemin de base "/api" — un autre
  // service sur le même hôte, pas la route tuiles authentifiée.
  expect(t("https://hote.test/collections/communes/tiles/1/2/3.mvt")).toEqual({
    url: "https://hote.test/collections/communes/tiles/1/2/3.mvt",
  });
});

const clickPayload = {
  features: [{ id: 7, properties: { nom: "Tulle", population: 14000 } }],
  lngLat: { lng: 12, lat: 34 },
};

// `fireOnLayer` invoque le handler de clic hors du système d'événements React
// (c'est un appel JS direct sur le mock, pas un dispatch DOM) : le setState
// qu'il déclenche doit être enveloppé dans `act` pour être flush avant
// l'assertion, sans quoi React 18 le bufferise en dehors du test.
test("clicking a feature of a layer with a popup opens it", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText("Tulle")).toBeInTheDocument();
  expect(screen.getByText("population")).toBeInTheDocument();
});

test("the popup is positioned at the projected click point", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  const popup = screen.getByRole("dialog");
  expect(popup.style.left).toBe("12px");
  expect(popup.style.top).toBe("34px");
});

test("no popup opens for a layer that does not declare one", () => {
  render(<MapView config={tiled({ geometryKind: "polygon" })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the click stays additive: onFeatureClick still fires with a popup configured", () => {
  const onFeatureClick = vi.fn();
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })}
      onFeatureClick={onFeatureClick}
    />,
  );
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  expect(onFeatureClick).toHaveBeenCalledOnce();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("the popup closes on its close button", async () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the popup follows the map when it moves", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  const map = mapInstances[0];
  act(() => map.fireOnLayer("click", "communes", clickPayload));
  map.project = (ll: { lng: number; lat: number }) => ({ x: ll.lng + 100, y: ll.lat + 100 });
  act(() => map.fire("move"));
  expect(screen.getByRole("dialog").style.left).toBe("112px");
});

test("the popup closes when the layer that opened it disappears from the config", () => {
  const { rerender } = render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  rerender(<MapView config={config} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the popup closes when its layer keeps its id but loses its popup config", () => {
  // Le popup ne doit pas seulement figer son affichage : `resolvePopupContent`
  // se réévalue à chaque rendu, donc un `popup` retiré de la config sans
  // fermer le popup ferait retomber sur la branche "pas de config → tout
  // afficher", exposant un champ que l'auteur avait explicitement exclu.
  const { rerender } = render(
    <MapView config={tiled({ geometryKind: "polygon", popup: { fields: [{ name: "nom" }] } })} />,
  );
  act(() =>
    mapInstances[0].fireOnLayer("click", "communes", {
      features: [{ id: 7, properties: { nom: "Tulle", secret: "ne-pas-afficher" } }],
      lngLat: { lng: 12, lat: 34 },
    }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
  rerender(<MapView config={tiled({ geometryKind: "polygon" })} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("a template popup renders its sanitized html", () => {
  render(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { template: "**${record.nom}**" } })}
    />,
  );
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  expect(screen.getByText("Tulle").tagName).toBe("STRONG");
});

test("clicking a second feature replaces the popup instead of stacking it", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })} />);
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  act(() =>
    mapInstances[0].fireOnLayer("click", "communes", {
      features: [{ id: 8, properties: { nom: "Brive", population: 47000 } }],
      lngLat: { lng: 20, lat: 40 },
    }),
  );
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(screen.getByText("Brive")).toBeInTheDocument();
  expect(screen.queryByText("Tulle")).not.toBeInTheDocument();
});

test("the move listener that reprojects the popup is detached when the popup closes", async () => {
  render(<MapView config={tiled({ geometryKind: "polygon", popup: {} })} />);
  const map = mapInstances[0];
  act(() => map.fireOnLayer("click", "communes", clickPayload));
  expect(map.handlers.move ?? []).toHaveLength(1);
  act(() => map.fire("move"));
  screen.getByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(map.handlers.move ?? []).toHaveLength(0);
});

test("the popup survives a config change that keeps the layer but changes something else", () => {
  const { rerender } = render(
    <MapView config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })} />,
  );
  act(() => mapInstances[0].fireOnLayer("click", "communes", clickPayload));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  rerender(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" }, title: "Communes 2" })}
    />,
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

// I5 de la revue finale SP-24 : avant `layersKey`, chaque frappe dans
// PopupEditor produisait un nouveau tableau `config.layers` (même contenu
// pertinent) qui détruisait puis recréait TOUTES les sources/couches
// MapLibre — scintillement, re-requêtes de tuiles, refetch GeoJSON complet
// pour une couche `feature`. `popup` n'affecte que le rendu React d'un clic
// déjà survenu, jamais ce que MapLibre doit dessiner.
test("editing only a layer's popup config does not tear down and rebuild its MapLibre source/layer", () => {
  const { rerender } = render(
    <MapView config={tiled({ geometryKind: "polygon", popup: { titleField: "nom" } })} />,
  );
  const map = mapInstances[0];
  const addSource = vi.spyOn(map, "addSource");
  const addLayer = vi.spyOn(map, "addLayer");
  const removeSource = vi.spyOn(map, "removeSource");
  rerender(
    <MapView
      config={tiled({ geometryKind: "polygon", popup: { titleField: "nom", template: "**x**" } })}
    />,
  );
  expect(addSource).not.toHaveBeenCalled();
  expect(addLayer).not.toHaveBeenCalled();
  expect(removeSource).not.toHaveBeenCalled();
});

test("editing a layer's geometry-relevant property does still rebuild its MapLibre source/layer", () => {
  const { rerender } = render(<MapView config={tiled({ geometryKind: "point" })} />);
  const map = mapInstances[0];
  const addSource = vi.spyOn(map, "addSource");
  rerender(<MapView config={tiled({ geometryKind: "polygon" })} />);
  expect(addSource).toHaveBeenCalledTimes(1);
});

test("le mock MapLibre transporte un payload d'événement et enregistre les images", () => {
  render(<MapView config={config} />);
  const map = mapInstances[0];
  const seen: unknown[] = [];
  map.on("error", (e?: unknown) => seen.push(e));
  map.fire("error", { error: { message: "boom" } });
  expect(seen).toEqual([{ error: { message: "boom" } }]);

  map.addImage("x", { width: 1 }, { pixelRatio: 1 });
  expect(map.hasImage("x")).toBe(true);
  expect(map.listImages()).toEqual(["x"]);
  expect(map.getStyle().glyphs).toBe("https://glyphs.test/{fontstack}/{range}.pbf");
  expect(map.querySourceFeatures("nope")).toEqual([]);
});

test("a polygon layer with a stroke width adds a second outline line-layer sharing its source", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        symbology: {
          stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "dashed" },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.getLayer("communes")).toMatchObject({
    type: "fill",
    paint: { "fill-outline-color": "#000000" },
  });
  expect(map.getLayer("communes__outline")).toMatchObject({
    type: "line",
    source: "communes",
    "source-layer": "communes",
    paint: { "line-color": "#000000", "line-width": 2, "line-dasharray": [2, 2] },
  });
});

test("the outline sub-layer gets no click handler of its own (one popup per click)", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        popup: { titleField: "nom" },
        symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" } },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.layerHandlers["click:communes"] ?? []).toHaveLength(1);
  expect(map.layerHandlers["click:communes__outline"] ?? []).toHaveLength(0);
});

test("removing a stroked layer removes its outline sub-layer and its source", () => {
  const { rerender } = render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" } },
      })}
    />,
  );
  rerender(<MapView config={config} />);
  const map = mapInstances[0];
  expect(map.getLayer("communes__outline")).toBeUndefined();
  expect(map.getLayer("communes")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
});

test("a failing outline sub-layer rolls back its parent instead of orphaning the source", () => {
  const good: MapLayer = { id: "ok", title: "OK", visible: true, kind: "feature", url: "u1" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("communes__outline");
  rerender(
    <MapView
      config={{
        ...config,
        layers: [
          good,
          ...tiled({
            geometryKind: "polygon",
            symbology: {
              stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
            },
          }).layers,
        ],
      }}
    />,
  );
  expect(map.getLayer("communes")).toBeUndefined();
  expect(map.getLayer("communes__outline")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
  expect(map.getLayer("ok")).toBeDefined();
});

// Constat 1 (correctif de revue SP-27 Task 3) : le test ci-dessus ne passe
// que par le chemin "geometryKind connu" (site 2), qui pose un contour à
// suffixe simple ("communes__outline"). Le catch d'applyLayers boucle sur
// SUBLAYER_SUFFIXES avec une boucle IMBRIQUÉE spécifiquement pour retirer le
// double suffixe du contour d'une sous-couche de géométrie mixte
// ("communes__polygon__outline") — jamais exercée par le test ci-dessus.
// `tiled()` sans `geometryKind` passe par le chemin de géométrie mixte
// (site 1) : sa sous-couche "polygon" (communes__polygon) porte le contour
// à double suffixe.
test("a failing double-suffixed outline (mixed-geometry polygon sub-layer) rolls back its parent and the source", () => {
  const good: MapLayer = { id: "ok", title: "OK", visible: true, kind: "feature", url: "u1" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("communes__polygon__outline");
  rerender(
    <MapView
      config={{
        ...config,
        layers: [
          good,
          ...tiled({
            symbology: {
              stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
            },
          }).layers,
        ],
      }}
    />,
  );
  expect(map.getLayer("communes__polygon")).toBeUndefined();
  expect(map.getLayer("communes__polygon__outline")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
  expect(map.getLayer("ok")).toBeDefined();
});

// Constat 2 (correctif de revue SP-27 Task 3) : le brief exige qu'un stroke
// sur une géométrie "line" soit un no-op (une ligne a déjà sa propre couleur
// via l'encodage `color` ; un second contour sur une ligne n'a pas de sens
// cartographique). Trois gardes le garantissent par construction
// (buildMapPaint ne pose l'outlinePaint que pour "point"/"polygon", et le
// site d'appel ne pose addOutlineLayer que pour "polygon") mais rien ne le
// prouvait par une assertion directe.
test("a stroke on a line geometry is a no-op: no outline sub-layer, line color stays the color encoding's", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "line",
        symbology: {
          color: {
            field: "categorie",
            mode: "categorical",
            palette: "categorical-a",
            domain: { kind: "categorical", values: ["A", "B"] },
            computedAt: "2026-08-23T00:00:00Z",
          },
          stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.getLayer("communes__outline")).toBeUndefined();
  expect(map.getLayer("communes")).toMatchObject({
    type: "line",
    paint: {
      "line-color": ["match", ["get", "categorie"], "A", "#2563eb", "B", "#dc2626", "#2563eb"],
    },
  });
});

test("a feature layer's opacity reaches its paint", () => {
  const layer: MapLayer = {
    id: "l1",
    title: "Zones",
    visible: true,
    kind: "feature",
    url: "u",
    symbology: { opacity: 40 },
  };
  render(<MapView config={{ ...config, layers: [layer] }} />);
  expect(mapInstances[0].getLayer("l1")).toMatchObject({
    type: "fill",
    paint: { "fill-opacity": 0.4 },
  });
});

test("themeColors reaches the paint compilation (theme-primary resolves)", () => {
  const layer: MapLayer = {
    id: "l1",
    title: "Zones",
    visible: true,
    kind: "feature",
    url: "u",
    symbology: {
      color: {
        field: "valeur",
        mode: "numeric",
        palette: "theme-primary",
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: "2026-08-27T00:00:00Z",
      },
    },
  };
  render(<MapView config={{ ...config, layers: [layer] }} themeColors={{ primary: "#123456" }} />);
  expect(JSON.stringify(mapInstances[0].getLayer("l1"))).toContain("#123456");
});

test("a MapLibre error event is reported instead of vanishing", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<MapView config={config} />);
  mapInstances[0].fire("error", {
    error: { message: "layers[0].paint.icon-image: unknown property" },
  });
  expect(spy).toHaveBeenCalledWith(
    "MapView: MapLibre a signalé une erreur",
    expect.objectContaining({ error: expect.anything() }),
  );
  spy.mockRestore();
});

// Constat N13 : sans filtre, ce listener journalise chaque tuile 404 et
// chaque sprite manquant, donc noie le signal qu'il existe pour produire.
test("an ordinary MapLibre error (a 404 tile) is not reported", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<MapView config={config} />);
  mapInstances[0].fire("error", { error: { message: "AJAXError: Not Found (404)" } });
  expect(spy).not.toHaveBeenCalled();
  spy.mockRestore();
});
