import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { MapConfig } from "../api/types";

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

export function MapView({
  config,
  onViewChange: _onViewChange,
}: {
  config: MapConfig;
  onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
    });
    mapRef.current = map;
    map.on("load", () => applyLayers(map, config.layers, appliedRef.current));
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.loaded()) return;
    applyLayers(map, config.layers, appliedRef.current);
  }, [config.layers]);

  return <div ref={containerRef} className="h-full w-full" data-testid="map-container" />;
}
