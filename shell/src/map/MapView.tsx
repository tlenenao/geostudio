import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import type { MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck") continue;
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
      map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
    }
    applied.add(layer.id);
  }
}

type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;

function buildDeckLayer(layer: DeckLayer) {
  const props = { id: layer.id, data: layer.dataUrl, ...(layer.props ?? {}) };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
  }
}

function applyDeckLayers(overlay: MapboxOverlay, layers: MapConfig["layers"]) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  overlay.setProps({ layers: deckLayers });
}

export function MapView({
  config,
  onViewChange,
}: {
  config: MapConfig;
  onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const layersRef = useRef(config.layers);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    layersRef.current = config.layers;
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
    });
    mapRef.current = map;
    const overlay = new MapboxOverlay({ layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      applyLayers(map, layersRef.current, appliedRef.current);
      applyDeckLayers(overlay, layersRef.current);
    });
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      cb({ center: [c.lng, c.lat], zoom: map.getZoom() });
    });
    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.loaded()) return;
    applyLayers(map, config.layers, appliedRef.current);
  }, [config.layers]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      <MapLegend layers={config.layers} />
    </div>
  );
}
