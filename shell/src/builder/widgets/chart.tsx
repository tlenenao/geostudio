// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useAnalyticsContext, useSetCrossFilter } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import {
  bucketFor,
  referenceWindow,
  windowedStatisticsSource,
  type ReferenceMode,
} from "../../lib/comparisonWindow";
import {
  buildOption,
  buildCompareOption,
  resolveClickFilter,
  type ChartProps,
  type ClickParams,
  type ComparePoint,
} from "./chartOption";
import { ExplorerMenu } from "./ExplorerMenu";
import type { DataRecord, DataSource, DatasetConfig } from "../../api/types";
import { t } from "../../i18n";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

const CHART_TYPES: [string, string][] = [
  ["bar", t("widgetChart.typeBar")],
  ["line", t("widgetChart.typeLine")],
  ["area", t("widgetChart.typeArea")],
  ["scatter", t("widgetChart.typeScatter")],
  ["pie", t("widgetChart.typePie")],
  ["doughnut", t("widgetChart.typeDoughnut")],
  ["radar", t("widgetChart.typeRadar")],
  ["heatmap", t("widgetChart.typeHeatmap")],
  ["gauge", t("widgetChart.typeGauge")],
  ["boxplot", t("widgetChart.typeBoxplot")],
  ["sankey", t("widgetChart.typeSankey")],
  ["treemap", t("widgetChart.typeTreemap")],
  ["sunburst", t("widgetChart.typeSunburst")],
  ["funnel", t("widgetChart.typeFunnel")],
  ["histogram", t("widgetChart.typeHistogram")],
];
const AXIS_TYPES: [string, string][] = [
  ["category", t("widgetChart.axisCategory")],
  ["value", t("widgetChart.axisValue")],
  ["time", t("widgetChart.axisTime")],
  ["log", t("widgetChart.axisLog")],
];

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function toComparePoints(records: DataRecord[] | undefined, timeField: string): ComparePoint[] {
  return (records ?? []).map((r) => ({
    bucket: String(r.properties[timeField] ?? ""),
    value: Number(r.properties.value ?? 0),
  }));
}

export function registerChartWidget(): void {
  registerWidget({
    type: "chart",
    label: t("widgetChart.paletteLabel"),
    defaultProps: {
      dataSourceId: "",
      chartType: "bar",
      categoryField: "",
      valueField: "",
      stack: false,
      legend: true,
      zoom: false,
      xAxisType: "category",
      yAxisType: "value",
      yAxisFormat: "",
      yAxisUnit: "",
      title: "",
      advancedOption: "",
      compareEnabled: false,
      comparePeriod: "previous",
    },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: t("widgetChart.dataSource"), default: "" },
      { name: "chartType", type: "string", label: t("widgetChart.chartType"), default: "bar" },
      { name: "categoryField", type: "string", label: t("widgetChart.categoryField"), default: "" },
      { name: "valueField", type: "string", label: t("widgetChart.valueField"), default: "" },
      { name: "stack", type: "boolean", label: t("widgetChart.stackConfig"), default: false },
      { name: "legend", type: "boolean", label: t("widgetChart.legendConfig"), default: true },
      { name: "zoom", type: "boolean", label: t("widgetChart.zoomConfig"), default: false },
      { name: "xAxisType", type: "string", label: t("widgetChart.xAxisType"), default: "category" },
      { name: "yAxisType", type: "string", label: t("widgetChart.yAxisType"), default: "value" },
      {
        name: "yAxisFormat",
        type: "string",
        label: t("widgetChart.yAxisFormatConfig"),
        default: "",
      },
      { name: "yAxisUnit", type: "string", label: t("widgetChart.yAxisUnitConfig"), default: "" },
      { name: "title", type: "string", label: t("widgetChart.title"), default: "" },
      {
        name: "advancedOption",
        type: "string",
        label: t("widgetChart.advancedOption"),
        default: "",
      },
      {
        name: "compareEnabled",
        type: "boolean",
        label: t("widgetChart.compareConfig"),
        default: false,
      },
      {
        name: "comparePeriod",
        type: "string",
        label: t("widgetChart.comparePeriodConfig"),
        default: "previous",
      },
    ],
    defaultSize: { w: 6, h: 4 },
    events: ["categorySelected"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      const chartType = String(props.chartType ?? "bar");
      const showCompare = chartType === "line" || chartType === "area";
      const showCategoryValue =
        chartType !== "sankey" && chartType !== "treemap" && chartType !== "sunburst";
      const showSankeyEncodings = chartType === "sankey";
      const showHierarchyEncodings = chartType === "treemap" || chartType === "sunburst";
      const encodings = (props.encodings as ChartProps["encodings"]) ?? {};
      const setEncodings = (patch: Record<string, unknown>) =>
        set({ encodings: { ...encodings, ...patch } });
      const levels = encodings.levels ?? [];
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect
            value={String(props.dataSourceId ?? "")}
            dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })}
          />
          <label className={labelCls}>
            {t("widgetChart.chartType")}
            <select
              aria-label={t("widgetChart.chartType")}
              className={inputCls}
              value={chartType}
              onChange={(e) => set({ chartType: e.target.value })}
            >
              {CHART_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          {showCategoryValue && (
            <>
              <label className={labelCls}>
                {t("widgetChart.categoryFieldLabel")}
                <input
                  aria-label={t("widgetChart.categoryField")}
                  className={inputCls}
                  value={String(props.categoryField ?? "")}
                  onChange={(e) => set({ categoryField: e.target.value })}
                />
              </label>
              <label className={labelCls}>
                {t("widgetChart.valueFieldLabel")}
                <input
                  aria-label={t("widgetChart.valueField")}
                  className={inputCls}
                  value={String(props.valueField ?? "")}
                  onChange={(e) => set({ valueField: e.target.value })}
                />
              </label>
            </>
          )}
          {showSankeyEncodings && (
            <>
              <label className={labelCls}>
                {t("widgetChart.sourceField")}
                <input
                  aria-label={t("widgetChart.sourceField")}
                  className={inputCls}
                  value={String(encodings.source ?? "")}
                  onChange={(e) => setEncodings({ source: e.target.value })}
                />
              </label>
              <label className={labelCls}>
                {t("widgetChart.targetField")}
                <input
                  aria-label={t("widgetChart.targetField")}
                  className={inputCls}
                  value={String(encodings.target ?? "")}
                  onChange={(e) => setEncodings({ target: e.target.value })}
                />
              </label>
            </>
          )}
          {showHierarchyEncodings && (
            <div className={labelCls}>
              <span>{t("widgetChart.levelsLabel")}</span>
              {levels.map((lvl, i) => (
                <div key={i} className="flex items-center gap-1">
                  <input
                    aria-label={t("widgetChart.levelN", { n: i + 1 })}
                    className={inputCls}
                    value={lvl}
                    onChange={(e) =>
                      setEncodings({ levels: levels.map((l, j) => (j === i ? e.target.value : l)) })
                    }
                  />
                  <button
                    type="button"
                    aria-label={t("widgetChart.removeLevel", { n: i + 1 })}
                    className="text-xs text-red-600"
                    onClick={() => setEncodings({ levels: levels.filter((_, j) => j !== i) })}
                  >
                    ✕
                  </button>
                </div>
              ))}
              {levels.length < 3 && (
                <button
                  type="button"
                  className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                  onClick={() => setEncodings({ levels: [...levels, ""] })}
                >
                  {t("widgetChart.addLevel")}
                </button>
              )}
            </div>
          )}
          {showCompare && (
            <>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={t("widgetChart.compareToggle")}
                  checked={Boolean(props.compareEnabled)}
                  onChange={(e) => set({ compareEnabled: e.target.checked })}
                />
                {t("widgetChart.compareToggle")}
              </label>
              <label className={labelCls}>
                {t("widgetChart.referencePeriodLabel")}
                <select
                  aria-label={t("widgetChart.referencePeriodLabel")}
                  className={inputCls}
                  value={String(props.comparePeriod ?? "previous")}
                  onChange={(e) => set({ comparePeriod: e.target.value })}
                >
                  <option value="previous">{t("widgetChart.periodPrevious")}</option>
                  <option value="sameLastYear">{t("widgetChart.periodSameLastYear")}</option>
                </select>
              </label>
            </>
          )}
          <label className={labelCls}>
            {t("widgetChart.xAxisType")}
            <select
              aria-label={t("widgetChart.xAxisType")}
              className={inputCls}
              value={String(props.xAxisType ?? "category")}
              onChange={(e) => set({ xAxisType: e.target.value })}
            >
              {AXIS_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            {t("widgetChart.yAxisType")}
            <select
              aria-label={t("widgetChart.yAxisType")}
              className={inputCls}
              value={String(props.yAxisType ?? "value")}
              onChange={(e) => set({ yAxisType: e.target.value })}
            >
              {AXIS_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            {t("widgetChart.yAxisUnitLabel")}
            <input
              aria-label={t("widgetChart.yAxisUnitLabel")}
              className={inputCls}
              value={String(props.yAxisUnit ?? "")}
              onChange={(e) => set({ yAxisUnit: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetChart.title")}
            <input
              aria-label={t("widgetChart.titleAria")}
              className={inputCls}
              value={String(props.title ?? "")}
              onChange={(e) => set({ title: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={t("widgetChart.stackToggle")}
              checked={Boolean(props.stack)}
              onChange={(e) => set({ stack: e.target.checked })}
            />
            {t("widgetChart.stackToggle")}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={t("widgetChart.legendToggle")}
              checked={props.legend !== false}
              onChange={(e) => set({ legend: e.target.checked })}
            />
            {t("widgetChart.legendToggle")}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={t("widgetChart.zoomToggle")}
              checked={Boolean(props.zoom)}
              onChange={(e) => set({ zoom: e.target.checked })}
            />
            {t("widgetChart.zoomToggle")}
          </label>
          <label className={labelCls}>
            {t("widgetChart.advancedOption")}
            <textarea
              aria-label={t("widgetChart.advancedOption")}
              className="rounded-md border border-slate-300 p-2 font-mono text-xs"
              rows={4}
              placeholder='{"color":["#f00"]}'
              value={String(props.advancedOption ?? "")}
              onChange={(e) => set({ advancedOption: e.target.value })}
            />
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
      const compareRequested =
        Boolean(props.compareEnabled) && (chartType === "line" || chartType === "area");
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
      const referenceRange =
        compareActive && timeRange ? referenceWindow(timeRange, comparePeriod) : null;

      // Cache-key deviation from the naive ["chart-compare-current", datasetId,
      // timeRange, ...] form (see Task 5 brief): resolve the DataSource FIRST via
      // windowedStatisticsSource, then key the query on [label, source?.id,
      // source?.query] — mirrors indicator.tsx's useKpiComparison and
      // DataContext.tsx's own ["datasource", s.id, merged.query] idiom. This
      // folds the widget's own source id (`originSourceId`) and the fully
      // resolved, cross-filter-patched query into the key, so two chart widgets
      // on the same dataset+metric can't collide in the TanStack Query cache.
      const currentSource: DataSource | null =
        compareActive && timeRange
          ? windowedStatisticsSource(
              originSourceId,
              datasetId as string,
              dataset as DatasetConfig,
              analyticsCtx,
              timeRange,
              {
                groupBy: (dataset as DatasetConfig).timeField as string,
                bucket,
                agg,
                field: valueField || undefined,
              },
            )
          : null;
      const currentQuery = useQuery({
        queryKey: ["chart-compare-current", currentSource?.id, currentSource?.query],
        queryFn: () => client.queryDataSource(currentSource as DataSource),
        enabled: Boolean(compareActive && currentSource),
      });
      const referenceSource: DataSource | null =
        compareActive && referenceRange
          ? windowedStatisticsSource(
              originSourceId,
              datasetId as string,
              dataset as DatasetConfig,
              analyticsCtx,
              referenceRange,
              {
                groupBy: (dataset as DatasetConfig).timeField as string,
                bucket,
                agg,
                field: valueField || undefined,
              },
            )
          : null;
      const referenceQuery = useQuery({
        queryKey: ["chart-compare-reference", referenceSource?.id, referenceSource?.query],
        queryFn: () => client.queryDataSource(referenceSource as DataSource),
        enabled: Boolean(compareActive && referenceSource),
      });

      if (compareActive) {
        if (currentQuery.isLoading || referenceQuery.isLoading)
          return <p className="text-xs text-[var(--gs-color-muted)]">{t("common.loading")}</p>;
        if (currentQuery.isError || referenceQuery.isError)
          return <p className="text-xs text-red-600">{t("common.dataError")}</p>;
        const timeField = (dataset as DatasetConfig).timeField as string;
        const option = buildCompareOption(
          props as unknown as ChartProps,
          toComparePoints(currentQuery.data, timeField),
          toComparePoints(referenceQuery.data, timeField),
          bucket,
        );
        return (
          <div className="relative h-full">
            <ExplorerMenu
              datasetId={datasetId}
              dataSourceId={originSourceId}
              resolvedSource={data?.resolvedSource}
              hasGeometry={data?.hasGeometry}
            />
            <Suspense
              fallback={
                <div className="text-xs text-ink-2">{t("widgetChart.loadingFallback")}</div>
              }
            >
              <EChart option={option} />
            </Suspense>
          </div>
        );
      }

      if (!data || data.loading)
        return <p className="text-xs text-[var(--gs-color-muted)]">{t("common.loading")}</p>;
      if (data.error) return <p className="text-xs text-red-600">{t("common.dataError")}</p>;
      if (data.records.length === 0)
        return <p className="text-xs text-[var(--gs-color-muted)]">{t("common.noData")}</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      function handleClick(params: ClickParams) {
        const resolved = resolveClickFilter(chartType, props as unknown as ChartProps, params);
        if (!resolved) return;
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [resolved.field]: resolved.value });
        if (data?.datasetId)
          setCrossFilter(data.datasetId, resolved.field, resolved.value, originSourceId);
      }
      return (
        <div className="relative h-full">
          <ExplorerMenu
            datasetId={data.datasetId}
            dataSourceId={originSourceId}
            resolvedSource={data.resolvedSource}
            hasGeometry={data.hasGeometry}
          />
          <Suspense
            fallback={<div className="text-xs text-ink-2">{t("widgetChart.loadingFallback")}</div>}
          >
            <EChart option={option} onClick={handleClick} />
          </Suspense>
        </div>
      );
    },
  });
}
