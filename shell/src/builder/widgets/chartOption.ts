// SPDX-License-Identifier: Apache-2.0
import type { EChartsOption } from "echarts";
import type { DataRecord } from "../../api/types";
import type { BucketGranularity } from "../../lib/comparisonWindow";

export type ChartProps = {
  dataSourceId?: string;
  chartType?: string; // bar|line|area|scatter|pie|doughnut|radar|heatmap|gauge|boxplot|sankey|treemap|sunburst|funnel|histogram
  categoryField?: string;
  valueField?: string; // measure key for pie/gauge/funnel/histogram (defaults to first series)
  stack?: boolean;
  legend?: boolean;
  zoom?: boolean;
  xAxisType?: string; // category|value|time|log
  yAxisType?: string; // value|log|category
  yAxisFormat?: string; // any non-empty value → grouped number formatting
  yAxisUnit?: string;
  title?: string;
  advancedOption?: string; // raw ECharts option JSON, deep-merged last
  // Field-role mapping used only by sankey and treemap/sunburst — every
  // other chart type keeps categoryField/valueField (SP-14f §3).
  encodings?: { source?: string; target?: string; levels?: string[]; value?: string };
};

type Row = Record<string, unknown>;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// Deep-merge plain objects (arrays and scalars from `override` win outright).
function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
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

type TreeNode = { name: string; value?: number; children?: TreeNode[] };

// Builds a root→leaf hierarchy from tidy rows: one path per row through
// `levels`, leaf values accumulated then summed bottom-up into every ancestor.
function buildHierarchy(rows: Row[], levels: string[], valueKey: string): TreeNode[] {
  const roots: TreeNode[] = [];
  const index = new Map<string, TreeNode>();
  for (const row of rows) {
    let path = "";
    let siblings = roots;
    let node: TreeNode | undefined;
    for (const level of levels) {
      const name = String(row[level] ?? "—");
      path = `${path}/${name}`;
      node = index.get(path);
      if (!node) {
        node = { name };
        index.set(path, node);
        siblings.push(node);
      }
      node.children ??= [];
      siblings = node.children;
    }
    if (node) node.value = (node.value ?? 0) + num(row[valueKey]);
  }
  const sumUp = (node: TreeNode): number => {
    if (!node.children || node.children.length === 0) {
      delete node.children;
      return node.value ?? 0;
    }
    node.value = node.children.reduce((acc, c) => acc + sumUp(c), 0);
    return node.value;
  };
  roots.forEach(sumUp);
  return roots;
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

function round2(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : String(n);
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
    tooltip: {
      trigger:
        type === "pie" ||
        type === "doughnut" ||
        type === "gauge" ||
        type === "funnel" ||
        type === "sankey" ||
        type === "treemap" ||
        type === "sunburst"
          ? "item"
          : "axis",
    },
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
      series: [
        {
          type: "pie",
          radius: type === "doughnut" ? ["40%", "70%"] : "70%",
          encode: { itemName: catKey, value: valueKey },
        },
      ],
    });
  }

  if (type === "gauge") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      series: [
        {
          type: "gauge",
          data: [{ value: num(rows[0]?.[valueKey]), name: props.title || valueKey }],
        },
      ],
    });
  }

  if (type === "radar") {
    const maxVal = Math.max(1, ...rows.flatMap((row) => seriesKeys.map((k) => num(row[k]))));
    return finalize(props, {
      ...base,
      radar: { indicator: rows.map((row) => ({ name: String(row[catKey] ?? ""), max: maxVal })) },
      series: [
        {
          type: "radar",
          data: seriesKeys.map((k) => ({ name: k, value: rows.map((row) => num(row[k])) })),
        },
      ],
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
      visualMap: {
        min: Math.min(0, ...values),
        max: Math.max(1, ...values),
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 0,
      },
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

  if (type === "funnel") {
    const valueKey = props.valueField || seriesKeys[0] || "";
    return finalize(props, {
      ...base,
      series: [
        {
          type: "funnel",
          data: rows.map((row) => ({ name: String(row[catKey] ?? ""), value: num(row[valueKey]) })),
        },
      ],
    });
  }

  if (type === "histogram") {
    const labels = rows.map(
      (row) => `${round2(Number(row.bucketStart))}–${round2(Number(row.bucketEnd))}`,
    );
    const counts = rows.map((row) => num(row.count));
    return finalize(props, {
      ...base,
      xAxis: { type: "category", data: labels },
      yAxis,
      series: [{ type: "bar", name: "Effectif", data: counts }],
    });
  }

  if (type === "sankey") {
    const sourceField = props.encodings?.source ?? "";
    const targetField = props.encodings?.target ?? "";
    const valueKey =
      props.encodings?.value ||
      seriesKeys.find((k) => k !== sourceField && k !== targetField) ||
      "";
    const sourceNames = new Set(rows.map((row) => String(row[sourceField] ?? "")));
    const allNames = new Set<string>();
    rows.forEach((row) => {
      allNames.add(String(row[sourceField] ?? ""));
      allNames.add(String(row[targetField] ?? ""));
    });
    const nodes = [...allNames].map((name) => ({
      name,
      _role: sourceNames.has(name) ? "source" : "target",
    }));
    const links = rows.map((row) => ({
      source: String(row[sourceField] ?? ""),
      target: String(row[targetField] ?? ""),
      value: num(row[valueKey]),
    }));
    return finalize(props, { ...base, series: [{ type: "sankey", data: nodes, links }] });
  }

  if (type === "treemap" || type === "sunburst") {
    const levels = props.encodings?.levels ?? [];
    const valueKey = props.encodings?.value || seriesKeys.find((k) => !levels.includes(k)) || "";
    const tree = buildHierarchy(rows, levels, valueKey);
    return finalize(props, { ...base, series: [{ type, data: tree }] });
  }

  // bar | line | area | scatter — dataset + encode, one series per column.
  const seriesType =
    type === "area" || type === "line" ? "line" : type === "scatter" ? "scatter" : "bar";
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

export type ClickParams = {
  name?: string;
  dataType?: string;
  data?: Record<string, unknown>;
  treePathInfo?: { name: string }[];
};

// Generalizes the click→cross-filter mapping across all chart types. Default
// (bar/line/pie/.../funnel): unchanged categoryField behavior. Histogram:
// never resolves (range-filtering is out of the single-value cross-filter
// model). Treemap/sunburst: the deepest clicked hierarchy level. Sankey: the
// clicked node's role (tagged _role in buildOption, see the sankey branch)
// disambiguates whether it maps to encodings.source or encodings.target.
export function resolveClickFilter(
  chartType: string,
  props: ChartProps,
  params: ClickParams,
): { field: string; value: string } | null {
  if (chartType === "histogram") return null;

  if (chartType === "sankey") {
    if (params.dataType !== "node" || params.name == null) return null;
    const role = params.data?._role as "source" | "target" | undefined;
    const field = role === "target" ? props.encodings?.target : props.encodings?.source;
    if (!field) return null;
    return { field, value: String(params.name) };
  }

  if (chartType === "treemap" || chartType === "sunburst") {
    const levels = props.encodings?.levels ?? [];
    if (!levels.length || params.name == null) return null;
    const depth = Math.min(Math.max((params.treePathInfo?.length ?? 1) - 1, 0), levels.length - 1);
    const field = levels[depth];
    if (!field) return null;
    return { field, value: String(params.name) };
  }

  const field = props.categoryField;
  if (!field) return null;
  return { field, value: params.name != null ? String(params.name) : "" };
}

export type ComparePoint = { bucket: string; value: number };

function offsetLabel(bucket: BucketGranularity, index: number): string {
  const unit = bucket === "day" ? "Jour" : bucket === "week" ? "Semaine" : "Mois";
  return `${unit} ${index + 1}`;
}

// Compare-periods mode (SP-14e §5): two line series on a relative offset
// axis (index-based, not calendar dates) so the current window and its
// reference period overlay regardless of their absolute dates. Independent
// of buildOption — when compare mode is off, buildOption is untouched.
export function buildCompareOption(
  props: ChartProps,
  current: ComparePoint[],
  reference: ComparePoint[],
  bucket: BucketGranularity,
): EChartsOption {
  const length = Math.max(current.length, reference.length);
  const categories = Array.from({ length }, (_, i) => offsetLabel(bucket, i));
  const fmt = valueFormatter(props);
  const yAxis: Record<string, unknown> = { type: props.yAxisType ?? "value" };
  if (fmt) yAxis.axisLabel = { formatter: fmt };

  const built: Record<string, unknown> = {
    tooltip: { trigger: "axis" },
    legend: { show: props.legend ?? true },
    xAxis: { type: "category", data: categories },
    yAxis,
    series: [
      { type: "line", name: "Période courante", data: current.map((p) => p.value) },
      {
        type: "line",
        name: "Référence",
        data: reference.map((p) => p.value),
        lineStyle: { type: "dashed" },
        itemStyle: { opacity: 0.6 },
      },
    ],
  };
  if (props.title) built.title = { text: props.title };
  return finalize(props, built);
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
