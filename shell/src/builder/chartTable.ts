// SPDX-License-Identifier: Apache-2.0
// AUD-114 : alternative textuelle d'un graphique — mêmes données que l'option ECharts, en tableau
// (WCAG 1.1.1 / 2.1.1). Seuls les graphiques à catégories ou à points nommés s'y prêtent.
import type { EChartsOption } from "echarts";
import { formatNumber } from "../lib/format";

export type ChartTable = { head: string[]; rows: string[][] };

type Series = { name?: string; data?: unknown[]; encode?: { x?: string; y?: string } };
const MAX_ROWS = 200;

function cell(v: unknown): string {
  if (typeof v === "number") return formatNumber(v, 6);
  if (v && typeof v === "object" && "value" in v) {
    const inner = (v as { value: unknown }).value;
    return cell(Array.isArray(inner) ? inner[inner.length - 1] : inner);
  }
  if (Array.isArray(v)) return cell(v[v.length - 1]);
  return v === null || v === undefined ? "" : String(v);
}

function categoryData(axis: unknown): unknown[] | null {
  const a = Array.isArray(axis) ? axis[0] : axis;
  const data = (a as { data?: unknown })?.data;
  return Array.isArray(data) ? data : null;
}

export function chartTable(option: EChartsOption): ChartTable | null {
  const raw = option.series;
  const series = (Array.isArray(raw) ? raw : raw ? [raw] : []) as Series[];
  if (series.length === 0) return null;
  // bar/line/area : `dataset.source` + `encode` (une série par colonne).
  const source = (option.dataset as { source?: unknown } | undefined)?.source;
  if (Array.isArray(source) && series.every((s) => s.encode?.x && s.encode.y)) {
    const rows = source as Record<string, unknown>[];
    const x = series[0].encode!.x!;
    if (series.every((s) => s.encode!.x === x)) {
      return {
        head: ["", ...series.map((s) => s.name ?? s.encode!.y!)],
        rows: rows
          .slice(0, MAX_ROWS)
          .map((r) => [String(r[x] ?? ""), ...series.map((s) => cell(r[s.encode!.y!]))]),
      };
    }
  }
  if (series.some((s) => !Array.isArray(s.data))) return null;
  const cats = categoryData(option.xAxis) ?? categoryData(option.yAxis);
  if (cats) {
    return {
      head: ["", ...series.map((s, i) => s.name ?? String(i + 1))],
      rows: cats
        .slice(0, MAX_ROWS)
        .map((c, i) => [String(c), ...series.map((s) => cell((s.data as unknown[])[i]))]),
    };
  }
  const first = series[0].data as unknown[];
  if (first.length > 0 && first.every((d) => d && typeof d === "object" && "name" in d)) {
    return {
      head: ["", series[0].name ?? ""],
      rows: first.slice(0, MAX_ROWS).map((d) => [String((d as { name: unknown }).name), cell(d)]),
    };
  }
  return null;
}
