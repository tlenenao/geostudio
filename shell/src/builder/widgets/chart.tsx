// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useAnalyticsContext, useSetCrossFilter } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import { buildOption, buildCompareOption, type ChartProps, type ComparePoint } from "./chartOption";
import { ExplorerMenu } from "./ExplorerMenu";
import type { DataRecord, DataSource, DatasetConfig } from "../../api/types";

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

function toComparePoints(records: DataRecord[] | undefined, timeField: string): ComparePoint[] {
  return (records ?? []).map((r) => ({ bucket: String(r.properties[timeField] ?? ""), value: Number(r.properties.value ?? 0) }));
}

export function registerChartWidget(): void {
  registerWidget({
    type: "chart",
    label: "Graphique",
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous",
    },
    defaultSize: { w: 6, h: 4 },
    events: ["categorySelected"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      const chartType = String(props.chartType ?? "bar");
      const showCompare = chartType === "line" || chartType === "area";
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })} />
          <label className={labelCls}>Type de graphique
            <select aria-label="Type de graphique" className={inputCls}
              value={chartType} onChange={(e) => set({ chartType: e.target.value })}>
              {CHART_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Champ catégorie / X
            <input aria-label="Champ catégorie" className={inputCls}
              value={String(props.categoryField ?? "")} onChange={(e) => set({ categoryField: e.target.value })} />
          </label>
          <label className={labelCls}>Champ valeur (camembert / jauge / comparaison)
            <input aria-label="Champ valeur" className={inputCls}
              value={String(props.valueField ?? "")} onChange={(e) => set({ valueField: e.target.value })} />
          </label>
          {showCompare && (
            <>
              <label className="flex items-center gap-2">
                <input type="checkbox" aria-label="Comparer les périodes"
                  checked={Boolean(props.compareEnabled)} onChange={(e) => set({ compareEnabled: e.target.checked })} />
                Comparer les périodes
              </label>
              <label className={labelCls}>Période de référence
                <select aria-label="Période de référence" className={inputCls}
                  value={String(props.comparePeriod ?? "previous")} onChange={(e) => set({ comparePeriod: e.target.value })}>
                  <option value="previous">Période précédente</option>
                  <option value="sameLastYear">Même période l'an dernier</option>
                </select>
              </label>
            </>
          )}
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
      const setCrossFilter = useSetCrossFilter();
      const analyticsCtx = useAnalyticsContext();
      const client = useItemClient();
      const data = ctx.data;
      const datasetId = data?.datasetId;
      const chartType = String(props.chartType ?? "bar");
      const originSourceId = String(props.dataSourceId ?? "");
      const compareRequested = Boolean(props.compareEnabled) && (chartType === "line" || chartType === "area");
      const comparePeriod = (props.comparePeriod as ReferenceMode | undefined) ?? "previous";
      const valueField = String(props.valueField ?? "");
      const agg = valueField ? "sum" : "count";

      const datasetQuery = useQuery({
        queryKey: ["dataset", datasetId],
        queryFn: () => client.getDatasetConfig(datasetId as string),
        enabled: Boolean(compareRequested && datasetId),
      });
      const dataset = datasetQuery.data;
      const timeRange = analyticsCtx.timeRange;
      const compareActive = compareRequested && Boolean(dataset?.timeField) && Boolean(timeRange);
      const bucket = compareActive && timeRange ? bucketFor(timeRange) : "day";
      const referenceRange = compareActive && timeRange ? referenceWindow(timeRange, comparePeriod) : null;

      // Cache-key deviation from the naive ["chart-compare-current", datasetId,
      // timeRange, ...] form (see Task 5 brief): resolve the DataSource FIRST via
      // windowedStatisticsSource, then key the query on [label, source?.id,
      // source?.query] — mirrors indicator.tsx's useKpiComparison and
      // DataContext.tsx's own ["datasource", s.id, merged.query] idiom. This
      // folds the widget's own source id (`originSourceId`) and the fully
      // resolved, cross-filter-patched query into the key, so two chart widgets
      // on the same dataset+metric can't collide in the TanStack Query cache.
      const currentSource: DataSource | null = compareActive && timeRange
        ? windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          })
        : null;
      const currentQuery = useQuery({
        queryKey: ["chart-compare-current", currentSource?.id, currentSource?.query],
        queryFn: () => client.queryDataSource(currentSource as DataSource),
        enabled: Boolean(compareActive && currentSource),
      });
      const referenceSource: DataSource | null = compareActive && referenceRange
        ? windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          })
        : null;
      const referenceQuery = useQuery({
        queryKey: ["chart-compare-reference", referenceSource?.id, referenceSource?.query],
        queryFn: () => client.queryDataSource(referenceSource as DataSource),
        enabled: Boolean(compareActive && referenceSource),
      });

      if (compareActive) {
        if (currentQuery.isLoading || referenceQuery.isLoading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
        if (currentQuery.isError || referenceQuery.isError) return <p className="text-xs text-red-600">Erreur de données</p>;
        const timeField = (dataset as DatasetConfig).timeField as string;
        const option = buildCompareOption(
          props as unknown as ChartProps, toComparePoints(currentQuery.data, timeField), toComparePoints(referenceQuery.data, timeField), bucket,
        );
        return (
          <div className="relative h-full">
            <ExplorerMenu datasetId={datasetId} dataSourceId={originSourceId} />
            <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
              <EChart option={option} />
            </Suspense>
          </div>
        );
      }

      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      const categoryField = String(props.categoryField ?? "");
      function handleClick(params: { name?: string }) {
        if (!categoryField) return;
        const value = params.name != null ? String(params.name) : "";
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [categoryField]: value });
        if (data?.datasetId) setCrossFilter(data.datasetId, categoryField, value, originSourceId);
      }
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={originSourceId} />
          <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
            <EChart option={option} onClick={handleClick} />
          </Suspense>
        </div>
      );
    },
  });
}
