// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { buildLegend, buildMapPaint, detectGeometryKind } from "./mapSymbology";
import type { ColorDomain, LegendSpec, MapEncodings, SizeDomain } from "./mapSymbology";
import type { ItemClient, MapConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function centerFromPayload(p: unknown): [number, number] | null {
  const rec = p as { center?: [number, number]; geometry?: { type?: string; coordinates?: number[] } } | undefined;
  if (rec?.center) return rec.center;
  const g = rec?.geometry;
  if (g?.type === "Point" && Array.isArray(g.coordinates)) return [g.coordinates[0], g.coordinates[1]];
  return null;
}

function geometryFromPayload(p: unknown): unknown | null {
  return (p as { geometry?: unknown } | undefined)?.geometry ?? null;
}

// Bornes min/max d'un champ numérique, interrogées séparément de la
// DataSource "features" qui alimente le rendu — même patron que
// sliderFilter.tsx (measures min/max sur une source "statistics").
function useNumericDomain(client: ItemClient, datasetId: string | undefined, field: string, active: boolean) {
  return useQuery({
    queryKey: ["map-numeric-domain", datasetId, field],
    queryFn: async (): Promise<SizeDomain> => {
      const rows = await client.queryDataSource({
        id: `map-domain-${datasetId}-${field}`, type: "statistics", service: "core",
        layer: "", datasetId, query: { measures: [{ field, agg: "min", label: "min" }, { field, agg: "max", label: "max" }] },
      });
      const properties = rows[0]?.properties ?? {};
      return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
    },
    enabled: active && Boolean(datasetId && field),
  });
}

function MapSymbologyLegend({ legend }: { legend: LegendSpec }) {
  return (
    <div className="absolute bottom-2 right-2 z-10 flex flex-col gap-2 rounded-md bg-white/90 p-2 text-xs shadow">
      {legend.color?.kind === "categorical" && (
        <ul>
          {legend.color.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: e.color }} />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "numeric" && (
        <div>
          <div className="h-2 w-24 rounded"
            style={{ background: `linear-gradient(to right, ${legend.color.colorLow}, ${legend.color.colorHigh})` }} />
          <span>{legend.color.min} – {legend.color.max}</span>
        </div>
      )}
      {legend.size && (
        <div className="flex items-end gap-2">
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMin, height: legend.size.radiusMin }} />
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMax, height: legend.size.radiusMax }} />
          <span>{legend.size.min} – {legend.size.max}</span>
        </div>
      )}
    </div>
  );
}

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const setEncodings = (patch: MapEncodings) => onChange({ ...props, encodings: { ...encodings, ...patch } });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className={labelCls}>Champ couleur
            <input aria-label="Champ couleur" className={inputCls}
              value={String(encodings.color?.field ?? "")}
              onChange={(e) => setEncodings({ color: { field: e.target.value, mode: encodings.color?.mode ?? "categorical" } })} />
          </label>
          <label className={labelCls}>Type de couleur
            <select aria-label="Type de couleur" className={inputCls}
              value={encodings.color?.mode ?? "categorical"}
              onChange={(e) => setEncodings({ color: { field: encodings.color?.field ?? "", mode: e.target.value as "categorical" | "numeric" } })}>
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          <label className={labelCls}>Champ taille
            <input aria-label="Champ taille" className={inputCls}
              value={String(encodings.size?.field ?? "")}
              onChange={(e) => setEncodings({ size: { field: e.target.value } })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });

      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const datasetId = ctx.data?.datasetId;
      const colorField = encodings.color?.field ?? "";
      const colorMode = encodings.color?.mode ?? "categorical";
      const sizeField = encodings.size?.field ?? "";

      const categoricalQuery = useQuery({
        queryKey: ["map-categorical-domain", datasetId, colorField],
        queryFn: async (): Promise<string[]> => {
          const rows = await client.queryDataSource({
            id: `map-domain-${datasetId}-${colorField}`, type: "statistics", service: "core",
            layer: "", datasetId, query: { groupBy: colorField },
          });
          return rows.map((r) => String(r.id));
        },
        enabled: Boolean(datasetId && colorField && colorMode === "categorical"),
      });
      const numericColorQuery = useNumericDomain(client, datasetId, colorField, colorMode === "numeric");
      const sizeQuery = useNumericDomain(client, datasetId, sizeField, true);

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

      const colorDomain: ColorDomain | null = !colorField
        ? null
        : colorMode === "categorical"
          ? (categoricalQuery.data ? { kind: "categorical", values: categoricalQuery.data } : null)
          : (numericColorQuery.data ? { kind: "numeric", ...numericColorQuery.data } : null);
      const sizeDomain: SizeDomain | null = sizeField && sizeQuery.data ? sizeQuery.data : null;
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      const { renderAs, paint } = buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind);
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind);

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url, renderAs, paint }]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""), record.geometry);
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
  });
}
