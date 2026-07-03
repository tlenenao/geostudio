import type { EChartsOption } from "echarts";
import type { DataRecord } from "../../api/types";

export type ChartProps = {
  dataSourceId?: string;
  chartType?: string; // bar|line|area|scatter|pie|doughnut|radar|heatmap|gauge|boxplot
  categoryField?: string;
  valueField?: string; // measure key for pie/gauge (defaults to first series)
  stack?: boolean;
  legend?: boolean;
  zoom?: boolean;
  xAxisType?: string; // category|value|time|log
  yAxisType?: string; // value|log|category
  yAxisFormat?: string; // any non-empty value → grouped number formatting
  yAxisUnit?: string;
  title?: string;
  advancedOption?: string; // raw ECharts option JSON, deep-merged last
};

type Row = Record<string, unknown>;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// Deep-merge plain objects (arrays and scalars from `override` win outright).
function deepMerge(base: Record<string, unknown>, override: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base };
  for (const [k, v] of Object.entries(override)) {
    const cur = out[k];
    out[k] = isPlainObject(v) && isPlainObject(cur) ? deepMerge(cur, v) : v;
  }
  return out;
}

function pickCatKey(rows: Row[], categoryField?: string): string {
  const first = rows[0] ?? {};
  if (categoryField) return categoryField;
  const keys = Object.keys(first);
  return keys.find((k) => typeof first[k] !== "number") ?? keys[0] ?? "";
}

function num(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

function valueFormatter(props: ChartProps): ((val: unknown) => string) | undefined {
  const unit = String(props.yAxisUnit ?? "");
  const fmt = String(props.yAxisFormat ?? "");
  if (!unit && !fmt) return undefined;
  const nf = fmt ? new Intl.NumberFormat("fr-FR") : null;
  return (val: unknown) => {
    const s = nf && Number.isFinite(Number(val)) ? nf.format(Number(val)) : String(val);
    return unit ? `${s} ${unit}` : s;
  };
}

// Pure translation of the widget config + resolved records into an ECharts
// option. No React, no echarts runtime — the whole surface is unit-testable.
export function buildOption(props: ChartProps, records: DataRecord[]): EChartsOption {
  const rows: Row[] = records.map((r) => r.properties);
  const catKey = pickCatKey(rows, props.categoryField);
  const seriesKeys = Object.keys(rows[0] ?? {}).filter((k) => k !== catKey);
  const type = String(props.chartType ?? "bar");
  const fmt = valueFormatter(props);

  const base: Record<string, unknown> = {
    tooltip: { trigger: type === "pie" || type === "doughnut" || type === "gauge" ? "item" : "axis" },
    legend: { show: props.legend ?? true },
  };
  if (props.title) base.title = { text: props.title };
  if (props.zoom) base.dataZoom = [{ type: "inside" }, { type: "slider" }];

  const yAxis: Record<string, unknown> = { type: props.yAxisType ?? "value" };
  if (fmt) yAxis.axisLabel = { formatter: fmt };
  const xAxis: Record<string, unknown> = { type: props.xAxisType ?? "category" };

  if (type === "pie" || type === "doughnut") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      dataset: { source: rows },
      series: [{
        type: "pie",
        radius: type === "doughnut" ? ["40%", "70%"] : "70%",
        encode: { itemName: catKey, value: valueKey },
      }],
    });
  }

  if (type === "gauge") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      series: [{ type: "gauge", data: [{ value: num(rows[0]?.[valueKey]), name: props.title || valueKey }] }],
    });
  }

  if (type === "radar") {
    const maxVal = Math.max(1, ...rows.flatMap((row) => seriesKeys.map((k) => num(row[k]))));
    return finalize(props, {
      ...base,
      radar: { indicator: rows.map((row) => ({ name: String(row[catKey] ?? ""), max: maxVal })) },
      series: [{
        type: "radar",
        data: seriesKeys.map((k) => ({ name: k, value: rows.map((row) => num(row[k])) })),
      }],
    });
  }

  if (type === "heatmap") {
    const data: [number, number, number][] = [];
    rows.forEach((row, xi) => seriesKeys.forEach((k, yi) => data.push([xi, yi, num(row[k])])));
    const values = data.map((d) => d[2]);
    return finalize(props, {
      ...base,
      xAxis: { type: "category", data: rows.map((row) => String(row[catKey] ?? "")) },
      yAxis: { type: "category", data: seriesKeys },
      visualMap: { min: Math.min(0, ...values), max: Math.max(1, ...values), calculable: true, orient: "horizontal", left: "center", bottom: 0 },
      series: [{ type: "heatmap", data }],
    });
  }

  if (type === "boxplot") {
    return finalize(props, {
      ...base,
      xAxis: { type: "category", data: rows.map((row) => String(row[catKey] ?? "")) },
      yAxis,
      series: [{ type: "boxplot", data: rows.map((row) => seriesKeys.map((k) => num(row[k]))) }],
    });
  }

  // bar | line | area | scatter — dataset + encode, one series per column.
  const seriesType = type === "area" || type === "line" ? "line" : type === "scatter" ? "scatter" : "bar";
  return finalize(props, {
    ...base,
    dataset: { source: rows },
    xAxis,
    yAxis,
    series: seriesKeys.map((k) => ({
      type: seriesType,
      name: k,
      encode: { x: catKey, y: k },
      ...(type === "area" ? { areaStyle: {} } : {}),
      ...(props.stack ? { stack: "total" } : {}),
    })),
  });
}

function finalize(props: ChartProps, built: Record<string, unknown>): EChartsOption {
  const raw = String(props.advancedOption ?? "").trim();
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (isPlainObject(parsed)) return deepMerge(built, parsed) as EChartsOption;
    } catch {
      // Invalid JSON → ignore the escape hatch, keep the built option.
    }
  }
  return built as EChartsOption;
}
