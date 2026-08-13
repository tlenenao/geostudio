// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { Tiles3DLoader } from "@loaders.gl/3d-tiles";
import type { DataRecord, MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

const HIGHLIGHT_ID = "__highlight__";
const TERRAIN_SOURCE_ID = "__terrain__";

export type MapViewHandle = {
  flyTo: (opts: { center: [number, number]; zoom?: number; pitch?: number; bearing?: number }) => void;
  highlight: (geometry: unknown | null) => void;
};

function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  onFeatureClick: (record: DataRecord) => void,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    const prevHandler = clickHandlers.get(id);
    if (prevHandler) {
      map.off("click", id, prevHandler);
      clickHandlers.delete(id);
    }
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck" || layer.kind === "tiles3d") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({
          id: layer.id,
          type: "fill",
          source: layer.id,
          "source-layer": layer.sourceLayer,
          paint: layer.paint ?? {},
        });
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({ id: layer.id, type: "circle", source: layer.id, paint: layer.paint ?? {} });
            break;
          case "line":
            map.addLayer({ id: layer.id, type: "line", source: layer.id, paint: layer.paint ?? {} });
            break;
          default:
            map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
            break;
        }
        const handler = (e: maplibregl.MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f || f.id == null) return;
          onFeatureClick({ id: f.id as string | number, properties: f.properties ?? {}, geometry: f.geometry });
        };
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map. Roll back any
      // half-added source/layer so it can't orphan or clash on the next apply.
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
}

type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;
type Tiles3DMapLayer = Extract<MapConfig["layers"][number], { kind: "tiles3d" }>;

function buildDeckLayer(layer: DeckLayer) {
  // Canonical fields last so user props can't shadow the id Deck.gl uses for
  // layer reconciliation, nor the data source.
  const props = { ...(layer.props ?? {}), id: layer.id, data: layer.dataUrl };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
    default:
      // Exhaustiveness guard: a new deckType turns into a compile error here.
      return layer.deckType satisfies never;
  }
}

function buildTiles3DLayer(layer: Tiles3DMapLayer) {
  return new Tile3DLayer({ id: layer.id, data: layer.url, loader: Tiles3DLoader });
}

function applyDeckLayers(overlay: MapboxOverlay, layers: MapConfig["layers"]) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  const tiles3dLayers = layers
    .filter((l): l is Tiles3DMapLayer => l.visible && l.kind === "tiles3d")
    .map(buildTiles3DLayer);
  overlay.setProps({ layers: [...deckLayers, ...tiles3dLayers] });
}

// Full teardown-then-rebuild on every apply, mirroring applyLayers' pattern
// for the MapLibre-native layer array — simpler than diffing, and the only
// way to pick up a changed tilesUrl (MapLibre raster-dem sources are
// immutable once created).
function applyTerrain(map: maplibregl.Map, terrain: MapConfig["terrain"] | null | undefined) {
  map.setTerrain(null);
  if (map.getSource(TERRAIN_SOURCE_ID)) map.removeSource(TERRAIN_SOURCE_ID);
  if (!terrain) return;
  map.addSource(TERRAIN_SOURCE_ID, {
    type: "raster-dem",
    tiles: [terrain.tilesUrl],
    tileSize: 256,
    encoding: terrain.encoding,
  });
  map.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: terrain.exaggeration ?? 1 });
}

export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number]; pitch: number; bearing: number }) => void;
    onFeatureClick?: (record: DataRecord) => void;
    // Fired once the map has settled after its first load (MapLibre "idle":
    // no pending tiles/style/sprite loads) — the real "ready to capture"
    // signal for exportRender mode (SP-17a Task 10), as opposed to a fixed
    // delay.
    onReady?: () => void;
    // Suppresses the built-in interactive legend. Used by exportRender mode
    // (MapEditorPage), which renders its own legend overlay driven by
    // `printLayout.showLegend` — without this, that toggle couldn't ever
    // hide the legend from a capture (this MapLegend would still render
    // underneath it, and both would duplicate when showLegend is true).
    hideLegend?: boolean;
  }
>(function MapView({ config, onViewChange, onFeatureClick, onReady, hideLegend }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(new Map());
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const onReadyRef = useRef(onReady);
  const layersRef = useRef(config.layers);
  const terrainRef = useRef(config.terrain);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
  useEffect(() => {
    terrainRef.current = config.terrain;
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
    });
    mapRef.current = map;
    const overlay = new MapboxOverlay({ layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      map.addSource(HIGHLIGHT_ID, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: HIGHLIGHT_ID, type: "line", source: HIGHLIGHT_ID, paint: { "line-color": "#ef4444", "line-width": 3 } });
      applyLayers(map, layersRef.current, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
      applyDeckLayers(overlay, layersRef.current);
      applyTerrain(map, terrainRef.current);
      map.once("idle", () => onReadyRef.current?.());
    });
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      cb({ center: [c.lng, c.lat], zoom: map.getZoom(), bbox: bounds, pitch: map.getPitch(), bearing: map.getBearing() });
    });
    return () => {
      map.removeControl(overlay);
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !map.isStyleLoaded() || !overlay) return;
    applyLayers(map, config.layers, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
    applyDeckLayers(overlay, config.layers);
  }, [config.layers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    applyTerrain(map, config.terrain);
  }, [config.terrain]);

  useImperativeHandle(ref, () => ({
    flyTo: (opts) => {
      mapRef.current?.flyTo(opts);
    },
    highlight: (geometry) => {
      const src = mapRef.current?.getSource(HIGHLIGHT_ID) as { setData?: (d: unknown) => void } | undefined;
      src?.setData?.(
        geometry
          ? { type: "Feature", geometry, properties: {} }
          : { type: "FeatureCollection", features: [] },
      );
    },
  }), []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      {!hideLegend && <MapLegend layers={config.layers} />}
    </div>
  );
});
