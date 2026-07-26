// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useRef } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import type { MapConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

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

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources }) => (
      <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id })} />
    ),
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });
      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;
      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url }]
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
                if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""));
              }}
            />
          </Suspense>
        </div>
      );
    },
  });
}
