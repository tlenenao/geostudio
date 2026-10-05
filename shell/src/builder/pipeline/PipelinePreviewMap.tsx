// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "../../map/maplibreWorkerSetup";
import { DEFAULT_BASEMAP } from "../../map/basemaps";
import { t } from "../../i18n";
import type { MessageKey } from "../../i18n";
import { bboxFromFeatureCollection } from "../../lib/geometryBbox";
import { onThemeChange, readToken } from "../../lib/theme";

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
  { kind: "Polygon", color: "var(--gs-accent)", labelKey: "pipelinePreviewMap.legendPolygon" },
  { kind: "LineString", color: "var(--gs-ok)", labelKey: "pipelinePreviewMap.legendLine" },
  { kind: "Point", color: "var(--gs-danger)", labelKey: "pipelinePreviewMap.legendPoint" },
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
    let offTheme: (() => void) | undefined;
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: featureCollection });
      map.addLayer({
        id: `${SOURCE_ID}-fill`,
        type: "fill",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": readToken("--gs-accent", "#0b6e77") /* gs-raw-color-ok: repli jsdom */,
          "fill-opacity": 0.4,
        },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: {
          "line-color": readToken("--gs-ok", "#2a6a50") /* gs-raw-color-ok: repli jsdom */,
          "line-width": 2,
        },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-color": readToken("--gs-danger", "#9a2c45") /* gs-raw-color-ok: repli jsdom */,
          "circle-radius": 5,
        },
      });
      map.addLayer({
        id: `${SOURCE_ID}-selected`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["get", "__rowIndex"], selectedIndex ?? -1],
        paint: {
          "line-color": readToken("--gs-warn", "#85600f") /* gs-raw-color-ok: repli jsdom */,
          "line-width": 3,
        },
      });
      const handleClick = (e: maplibregl.MapLayerMouseEvent) => {
        const idx = e.features?.[0]?.properties?.__rowIndex;
        if (typeof idx === "number") onSelectIndex?.(idx);
      };
      const repaint = () => {
        const paint: [string, "fill-color" | "line-color" | "circle-color", string, string][] = [
          ["fill", "fill-color", "--gs-accent", "#0b6e77"], // gs-raw-color-ok: repli jsdom
          ["line", "line-color", "--gs-ok", "#2a6a50"], // gs-raw-color-ok: repli jsdom
          ["circle", "circle-color", "--gs-danger", "#9a2c45"], // gs-raw-color-ok: repli jsdom
          ["selected", "line-color", "--gs-warn", "#85600f"], // gs-raw-color-ok: repli jsdom
        ];
        for (const [suffix, prop, token, fallback] of paint) {
          map.setPaintProperty(`${SOURCE_ID}-${suffix}`, prop, readToken(token, fallback));
        }
      };
      offTheme = onThemeChange(repaint);
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
      offTheme?.();
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
        <div className="flex gap-3 text-xs text-ink-2">
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
