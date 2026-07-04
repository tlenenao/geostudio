import { lazy, Suspense } from "react";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { buildOption, type ChartProps } from "./chartOption";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

const CHART_TYPES: [string, string][] = [
  ["bar", "Barres"], ["line", "Lignes"], ["area", "Aires"], ["scatter", "Nuage de points"],
  ["pie", "Camembert"], ["doughnut", "Anneau"], ["radar", "Radar"], ["heatmap", "Carte de chaleur"],
  ["gauge", "Jauge"], ["boxplot", "Boîte à moustaches"],
];
const AXIS_TYPES: [string, string][] = [
  ["category", "Catégorie"], ["value", "Valeur"], ["time", "Temps"], ["log", "Logarithmique"],
];

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

export function registerChartWidget(): void {
  registerWidget({
    type: "chart",
    label: "Graphique",
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "",
    },
    defaultSize: { w: 6, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })} />
          <label className={labelCls}>Type de graphique
            <select aria-label="Type de graphique" className={inputCls}
              value={String(props.chartType ?? "bar")} onChange={(e) => set({ chartType: e.target.value })}>
              {CHART_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Champ catégorie / X
            <input aria-label="Champ catégorie" className={inputCls}
              value={String(props.categoryField ?? "")} onChange={(e) => set({ categoryField: e.target.value })} />
          </label>
          <label className={labelCls}>Champ valeur (camembert / jauge)
            <input aria-label="Champ valeur" className={inputCls}
              value={String(props.valueField ?? "")} onChange={(e) => set({ valueField: e.target.value })} />
          </label>
          <label className={labelCls}>Type d'axe X
            <select aria-label="Type d'axe X" className={inputCls}
              value={String(props.xAxisType ?? "category")} onChange={(e) => set({ xAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Type d'axe Y
            <select aria-label="Type d'axe Y" className={inputCls}
              value={String(props.yAxisType ?? "value")} onChange={(e) => set({ yAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Unité de l'axe Y
            <input aria-label="Unité de l'axe Y" className={inputCls}
              value={String(props.yAxisUnit ?? "")} onChange={(e) => set({ yAxisUnit: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du graphique" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Empiler les séries"
              checked={Boolean(props.stack)} onChange={(e) => set({ stack: e.target.checked })} />
            Empiler les séries
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Afficher la légende"
              checked={props.legend !== false} onChange={(e) => set({ legend: e.target.checked })} />
            Afficher la légende
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Activer le zoom"
              checked={Boolean(props.zoom)} onChange={(e) => set({ zoom: e.target.checked })} />
            Activer le zoom
          </label>
          <label className={labelCls}>Option ECharts avancée (JSON)
            <textarea aria-label="Option ECharts avancée (JSON)"
              className="rounded-md border border-slate-300 p-2 font-mono text-xs" rows={4}
              placeholder='{"color":["#f00"]}'
              value={String(props.advancedOption ?? "")} onChange={(e) => set({ advancedOption: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      return (
        <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
          <EChart option={option} />
        </Suspense>
      );
    },
  });
}
