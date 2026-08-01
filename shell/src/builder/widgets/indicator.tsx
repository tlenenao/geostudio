// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { ExplorerMenu } from "./ExplorerMenu";
import { useAnalyticsContext } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { evaluateExpression } from "../expr";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import type { DatasetConfig } from "../../api/types";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

type KpiComparison = {
  active: boolean;
  loading: boolean;
  value: number | null;
  delta: number | null;
  deltaPct: number | null;
  sparklinePoints: { bucket: string; value: number }[];
};

// Shared mechanic (Task 3, spec §3): fetches the dataset config (needed to
// know `timeField`), then — only once referencePeriod/sparkline is actually
// requested AND ctx.timeRange + dataset.timeField are both active — issues
// up to 3 independent `statistics` queries (current value, reference value,
// bucketed sparkline series). Each `useQuery` call is unconditional (Rules
// of Hooks); `enabled` gates the network request, not the hook call.
function useKpiComparison(
  datasetId: string | undefined,
  originSourceId: string,
  referencePeriod: ReferenceMode | undefined,
  sparklineEnabled: boolean,
  agg: string,
  field: string,
): KpiComparison {
  const client = useItemClient();
  const analyticsCtx = useAnalyticsContext();
  const wantsComparison = Boolean(referencePeriod || sparklineEnabled);

  const datasetQuery = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => client.getDatasetConfig(datasetId as string),
    enabled: Boolean(wantsComparison && datasetId),
  });
  const dataset = datasetQuery.data;
  const timeRange = analyticsCtx.timeRange;
  const active = wantsComparison && Boolean(dataset?.timeField) && Boolean(timeRange);

  const valueQuery = useQuery({
    queryKey: ["kpi-value", datasetId, timeRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod),
  });

  const referenceRange = active && referencePeriod ? referenceWindow(timeRange as { from: string; to: string }, referencePeriod) : null;
  const referenceQuery = useQuery({
    queryKey: ["kpi-reference", datasetId, referenceRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod && referenceRange),
  });

  const bucket = active && timeRange ? bucketFor(timeRange) : "day";
  const sparklineQuery = useQuery({
    queryKey: ["kpi-sparkline", datasetId, timeRange, bucket, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, {
        groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: field || undefined,
      }),
    ),
    enabled: Boolean(active && sparklineEnabled),
  });

  const value = referencePeriod && valueQuery.data ? Number(valueQuery.data[0]?.properties.value ?? 0) : null;
  const reference = referencePeriod && referenceQuery.data ? Number(referenceQuery.data[0]?.properties.value ?? 0) : null;
  const delta = value !== null && reference !== null ? value - reference : null;
  const deltaPct = delta !== null && reference !== null && reference !== 0 ? delta / reference : null;
  const sparklinePoints = sparklineEnabled && dataset?.timeField && sparklineQuery.data
    ? sparklineQuery.data.map((r) => ({ bucket: String(r.properties[dataset.timeField as string] ?? ""), value: Number(r.properties.value ?? 0) }))
    : [];

  const loading = active && (
    (Boolean(referencePeriod) && (valueQuery.isLoading || referenceQuery.isLoading)) ||
    (sparklineEnabled && sparklineQuery.isLoading)
  );

  return { active, loading, value, delta, deltaPct, sparklinePoints };
}

function deltaLabel(delta: number, deltaPct: number | null, mode: ReferenceMode): string {
  const refLabel = mode === "previous" ? "période précédente" : "même période l'an dernier";
  const sign = delta >= 0 ? "+" : "";
  const magnitude = deltaPct !== null ? `${sign}${Math.round(deltaPct * 100)} %` : `${sign}${delta}`;
  return `${magnitude} vs ${refLabel}`;
}

function thresholdLevel(
  criticalWhen: string, warningWhen: string,
  exprCtx: { vars: Record<string, unknown>; user: { name: string }; record: Record<string, unknown> },
): "critical" | "warning" | null {
  if (criticalWhen && evaluateExpression(criticalWhen, exprCtx)) return "critical";
  if (warningWhen && evaluateExpression(warningWhen, exprCtx)) return "warning";
  return null;
}

function sparklineOption(points: { bucket: string; value: number }[]): EChartsOption {
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: "category", show: false, data: points.map((p) => p.bucket) },
    yAxis: { type: "value", show: false },
    series: [{ type: "line", data: points.map((p) => p.value), showSymbol: false, lineStyle: { width: 1.5 } }],
  } as EChartsOption;
}

export function registerIndicatorWidget(): void {
  registerWidget({
    type: "indicator",
    label: "Indicateur",
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé de l'indicateur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Agrégation
          <select aria-label="Agrégation" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.agg ?? "count")} onChange={(e) => onChange({ ...props, agg: e.target.value })}>
            <option value="count">Nombre</option>
            <option value="sum">Somme</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">Champ (pour la somme)
          <input aria-label="Champ agrégé" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Comparer à
          <select aria-label="Comparer à" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.referencePeriod ?? "")}
            onChange={(e) => onChange({ ...props, referencePeriod: e.target.value || undefined })}>
            <option value="">Aucune</option>
            <option value="previous">Période précédente</option>
            <option value="sameLastYear">Même période l'an dernier</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label="Afficher un sparkline"
            checked={Boolean(props.sparkline)} onChange={(e) => onChange({ ...props, sparkline: e.target.checked })} />
          Afficher un sparkline
        </label>
        <label className="flex flex-col gap-1">Seuil critique (CEL)
          <input aria-label="Seuil critique (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.criticalWhen ?? "")} onChange={(e) => onChange({ ...props, criticalWhen: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Seuil d'alerte (CEL)
          <input aria-label="Seuil d'alerte (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.warningWhen ?? "")} onChange={(e) => onChange({ ...props, warningWhen: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      const agg = String(props.agg ?? "count");
      const field = String(props.field ?? "");
      const referencePeriod = (props.referencePeriod as ReferenceMode | undefined) || undefined;
      const sparklineEnabled = Boolean(props.sparkline);
      const criticalWhen = String(props.criticalWhen ?? "");
      const warningWhen = String(props.warningWhen ?? "");

      const comparison = useKpiComparison(
        data?.datasetId, String(props.dataSourceId ?? ""), referencePeriod, sparklineEnabled, agg, field,
      );

      if (!data || data.loading || comparison.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;

      const flatValue =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      const value = comparison.active && referencePeriod && comparison.value !== null ? comparison.value : flatValue;

      const badge = comparison.active && referencePeriod && comparison.delta !== null
        ? deltaLabel(comparison.delta, comparison.deltaPct, referencePeriod)
        : null;

      const level = criticalWhen || warningWhen
        ? thresholdLevel(criticalWhen, warningWhen, {
            vars: ctx.variables ?? {}, user: ctx.user ?? { name: "" },
            record: { value, delta: comparison.delta, deltaPct: comparison.deltaPct },
          })
        : null;

      return (
        <div className="relative flex h-full flex-col items-center justify-center gap-1">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <div className="flex items-center gap-1">
            <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
            {level && (
              <span
                aria-label={level === "critical" ? "Seuil critique atteint" : "Seuil d'alerte atteint"}
                className={`h-2.5 w-2.5 rounded-full ${level === "critical" ? "bg-red-600" : "bg-orange-500"}`}
              />
            )}
          </div>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
          {badge && <span className="text-xs text-[var(--gs-color-muted)]">{badge}</span>}
          {sparklineEnabled && comparison.active && comparison.sparklinePoints.length > 0 && (
            <div className="h-8 w-full">
              <Suspense fallback={null}>
                <EChart option={sparklineOption(comparison.sparklinePoints)} />
              </Suspense>
            </div>
          )}
        </div>
      );
    },
  });
}
