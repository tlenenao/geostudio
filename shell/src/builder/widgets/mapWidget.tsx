import { lazy, Suspense } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import type { MapConfig } from "../../api/types";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id })} />
    ),
    Component: ({ props, ctx }) => {
      const url = ctx.data?.url;
      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url }]
          : [],
      };
      return (
        <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
          <MapView config={config} />
        </Suspense>
      );
    },
  });
}
