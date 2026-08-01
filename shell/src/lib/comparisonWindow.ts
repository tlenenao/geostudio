// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { derivePatch } from "./analyticsPatch";

export type ReferenceMode = "previous" | "sameLastYear";
export type BucketGranularity = "day" | "week" | "month";

const MS_PER_DAY = 86_400_000;

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
}

// `current.from`/`current.to` are "YYYY-MM-DD" strings, parsed by `new
// Date(...)` as UTC midnight (ISO date-only parsing rule) — every accessor
// here stays UTC too, so the computed calendar day never drifts depending on
// the runtime's local timezone offset.
function shiftYears(d: Date, years: number): Date {
  const year = d.getUTCFullYear() + years;
  const month = d.getUTCMonth();
  const day = d.getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(day, daysInMonth(year, month))));
}

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function referenceWindow(
  current: { from: string; to: string },
  mode: ReferenceMode,
): { from: string; to: string } {
  const from = new Date(current.from), to = new Date(current.to);
  if (mode === "sameLastYear") {
    return { from: toISODate(shiftYears(from, -1)), to: toISODate(shiftYears(to, -1)) };
  }
  const durationMs = to.getTime() - from.getTime();
  const refTo = new Date(from.getTime());
  const refFrom = new Date(from.getTime() - durationMs);
  return { from: toISODate(refFrom), to: toISODate(refTo) };
}

export function bucketFor(current: { from: string; to: string }): BucketGranularity {
  const days = (new Date(current.to).getTime() - new Date(current.from).getTime()) / MS_PER_DAY;
  return days <= 31 ? "day" : days <= 180 ? "week" : "month";
}

// Shared query-construction mechanic (spec §3), reused by indicator's KPI
// comparison (Task 4) and chart's period-comparison mode (Task 5): builds a
// synthetic `statistics` DataSource for one time window and merges it with
// the same ambient filters (extent, cross-filter) DataContext would apply
// for the widget's own flat value — only `timeRange` is substituted.
export function windowedStatisticsSource(
  originSourceId: string,
  datasetId: string,
  dataset: DatasetConfig,
  analyticsCtx: AnalyticsContextState,
  window: { from: string; to: string },
  query: { groupBy?: string; bucket?: BucketGranularity; agg: string; field?: string },
): DataSource {
  const synthetic: DataSource = { id: originSourceId, type: "statistics", service: "core", layer: "", datasetId, query: {} };
  const patch = derivePatch(synthetic, { ...analyticsCtx, timeRange: window }, { [datasetId]: dataset });
  return { ...synthetic, query: { ...query, ...patch } };
}
