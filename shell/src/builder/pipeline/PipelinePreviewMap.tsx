// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "../../map/maplibreWorkerSetup";
import { DEFAULT_BASEMAP } from "../../map/basemaps";
import { t } from "../../i18n";
import type { MessageKey } from "../../i18n";
import { bboxFromFeatureCollection } from "../../lib/geometryBbox";

const SOURCE_ID = "pipeline-preview";

function presentGeometryKinds(
  rows: Record<string, unknown>[],
): Set<"Point" | "LineString" | "Polygon"> {
  const kinds = new Set<"Point" | "LineString" | "Polygon">();
  for (const r of rows) {
    const type = (r.geometry as GeoJSON.Geometry | null | undefined)?.type;
    if (type === "Point" || type === "MultiPoint") kinds.add("Point");
    else if (type === "LineString" || type === "MultiLineString") kinds.add("LineString");
    else if (type === "Polygon" || type === "MultiPolygon") kinds.add("Polygon");
  }
  return kinds;
}

const LEGEND_ENTRIES: {
  kind: "Point" | "LineString" | "Polygon";
  color: string;
  labelKey: MessageKey;
}[] = [
  { kind: "Polygon", color: "#2563eb", labelKey: "pipelinePreviewMap.legendPolygon" },
  { kind: "LineString", color: "#16a34a", labelKey: "pipelinePreviewMap.legendLine" },
  { kind: "Point", color: "#dc2626", labelKey: "pipelinePreviewMap.legendPoint" },
];

// Aperçu cartographique d'une étape de pipeline (SP-15g §5.3) — alternative à
// PipelinePreviewPanel's table, construite entièrement côté client à partir
// des lignes déjà décodées en GeoJSON par POST /pipelines/{id}/preview
// (ST_AsGeoJSON côté runtime, aucun appel réseau supplémentaire ici).
export function PipelinePreviewMap({
  rows,
  selectedIndex = null,
  onSelectIndex,
}: {
  rows: Record<string, unknown>[];
  selectedIndex?: number | null;
  onSelectIndex?: (index: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const features: GeoJSON.Feature[] = rows
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => r.geometry != null)
      .map(({ r, i }) => ({
        type: "Feature",
        properties: { __rowIndex: i },
        geometry: r.geometry as GeoJSON.Geometry,
      }));
    const featureCollection: GeoJSON.FeatureCollection = { type: "FeatureCollection", features };

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DEFAULT_BASEMAP.style,
      center: [0, 0],
      zoom: 1,
    });
    mapRef.current = map;
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: featureCollection });
      map.addLayer({
        id: `${SOURCE_ID}-fill`,
        type: "fill",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.4 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#16a34a", "line-width": 2 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": "#dc2626", "circle-radius": 5 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-selected`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["get", "__rowIndex"], selectedIndex ?? -1],
        paint: { "line-color": "#facc15", "line-width": 3 },
      });
      const handleClick = (e: maplibregl.MapLayerMouseEvent) => {
        const idx = e.features?.[0]?.properties?.__rowIndex;
        if (typeof idx === "number") onSelectIndex?.(idx);
      };
      map.on("click", `${SOURCE_ID}-fill`, handleClick);
      map.on("click", `${SOURCE_ID}-line`, handleClick);
      map.on("click", `${SOURCE_ID}-circle`, handleClick);
      const bbox = bboxFromFeatureCollection(features);
      if (bbox) {
        map.fitBounds(
          [
            [bbox[0], bbox[1]],
            [bbox[2], bbox[3]],
          ],
          { padding: 20, maxZoom: 16 },
        );
      }
    });
    return () => {
      mapRef.current = null;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  useEffect(() => {
    if (mapRef.current?.getLayer(`${SOURCE_ID}-selected`)) {
      mapRef.current.setFilter(`${SOURCE_ID}-selected`, [
        "==",
        ["get", "__rowIndex"],
        selectedIndex ?? -1,
      ]);
    }
  }, [selectedIndex]);

  const kinds = presentGeometryKinds(rows);
  return (
    <div className="flex flex-col gap-1">
      <div ref={containerRef} data-testid="pipeline-preview-map" style={{ height: 300 }} />
      {kinds.size > 0 && (
        <div className="flex gap-3 text-[10px] text-ink-2">
          {LEGEND_ENTRIES.filter((e) => kinds.has(e.kind)).map((e) => (
            <span key={e.kind} className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: e.color }} />
              {t(e.labelKey)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
