// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DEFAULT_BASEMAP } from "../../map/basemaps";

const SOURCE_ID = "pipeline-preview";

function collectCoordinates(geometry: GeoJSON.Geometry): [number, number][] {
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates as [number, number]];
    case "MultiPoint":
    case "LineString":
      return geometry.coordinates as [number, number][];
    case "MultiLineString":
    case "Polygon":
      return (geometry.coordinates as [number, number][][]).flat();
    case "MultiPolygon":
      return (geometry.coordinates as [number, number][][][]).flat(2);
    case "GeometryCollection":
      return geometry.geometries.flatMap(collectCoordinates);
    default:
      return [];
  }
}

function computeBounds(features: GeoJSON.Feature[]): [[number, number], [number, number]] | null {
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  for (const f of features) {
    if (!f.geometry) continue;
    for (const [lng, lat] of collectCoordinates(f.geometry)) {
      minLng = Math.min(minLng, lng);
      maxLng = Math.max(maxLng, lng);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }
  }
  return minLng === Infinity ? null : [[minLng, minLat], [maxLng, maxLat]];
}

// Aperçu cartographique d'une étape de pipeline (SP-15g §5.3) — alternative à
// PipelinePreviewPanel's table, construite entièrement côté client à partir
// des lignes déjà décodées en GeoJSON par POST /pipelines/{id}/preview
// (ST_AsGeoJSON côté runtime, aucun appel réseau supplémentaire ici).
export function PipelinePreviewMap({ rows }: { rows: Record<string, unknown>[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const features: GeoJSON.Feature[] = rows
      .filter((r) => r.geometry != null)
      .map((r) => ({ type: "Feature", properties: {}, geometry: r.geometry as GeoJSON.Geometry }));
    const featureCollection: GeoJSON.FeatureCollection = { type: "FeatureCollection", features };

    const map = new maplibregl.Map({
      container: containerRef.current, style: DEFAULT_BASEMAP.style, center: [0, 0], zoom: 1,
    });
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: featureCollection });
      map.addLayer({
        id: `${SOURCE_ID}-fill`, type: "fill", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.4 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`, type: "line", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#2563eb", "line-width": 2 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`, type: "circle", source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": "#2563eb", "circle-radius": 5 },
      });
      const bounds = computeBounds(features);
      if (bounds) map.fitBounds(bounds, { padding: 20, maxZoom: 16 });
    });
    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} data-testid="pipeline-preview-map" style={{ height: 300 }} />;
}
