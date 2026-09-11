// SPDX-License-Identifier: Apache-2.0
import type { FilterOperator, FilterRow } from "../visualQuery/compileFilter";
import type { JoinConfig, MetricFunction, SummaryConfig } from "../visualQuery/inferSchema";
import type { RawClientOp } from "./applyClientOp";

const FILTER_OPERATORS = new Set<FilterOperator>([
  "eq",
  "neq",
  "gt",
  "gte",
  "lt",
  "lte",
  "contains",
]);
const METRIC_FUNCTIONS = new Set<MetricFunction>([
  "count",
  "countDistinct",
  "sum",
  "avg",
  "median",
  "percentile",
  "stddev",
  "min",
  "max",
]);

function isValidGeneratedFilterRow(row: unknown): row is FilterRow {
  if (typeof row !== "object" || row === null) return false;
  const r = row as Record<string, unknown>;
  return (
    typeof r.column === "string" &&
    typeof r.operator === "string" &&
    FILTER_OPERATORS.has(r.operator as FilterOperator) &&
    typeof r.value === "string"
  );
}

function isValidGeneratedJoin(join: unknown): join is JoinConfig {
  if (typeof join !== "object" || join === null) return false;
  const j = join as Record<string, unknown>;
  return (
    typeof j.collectionId === "string" &&
    typeof j.on === "string" &&
    (j.how === "inner" || j.how === "left")
  );
}

function isValidGeneratedSummary(summary: unknown): summary is SummaryConfig {
  if (typeof summary !== "object" || summary === null) return false;
  const s = summary as Record<string, unknown>;
  if (!Array.isArray(s.groupBy) || !s.groupBy.every((g) => typeof g === "string")) return false;
  if (!Array.isArray(s.metrics)) return false;
  return s.metrics.every((m) => {
    if (typeof m !== "object" || m === null) return false;
    const metric = m as Record<string, unknown>;
    return (
      typeof metric.alias === "string" &&
      typeof metric.function === "string" &&
      METRIC_FUNCTIONS.has(metric.function as MetricFunction)
    );
  });
}

export function applyVisualQueryClientOp(
  raw: RawClientOp,
  setters: {
    setFilters: (rows: FilterRow[]) => void;
    setJoin: (join: JoinConfig | null) => void;
    setSummary: (summary: SummaryConfig | null) => void;
  },
): void {
  if (raw.op !== "applyVisualQueryDraft") return;
  const args = raw.args as { filters?: unknown; join?: unknown; summary?: unknown };
  if (Array.isArray(args.filters)) {
    setters.setFilters(args.filters.filter(isValidGeneratedFilterRow) as FilterRow[]);
  }
  if ("join" in args) {
    if (args.join === null) setters.setJoin(null);
    else if (isValidGeneratedJoin(args.join)) setters.setJoin(args.join);
  }
  if ("summary" in args) {
    if (args.summary === null) setters.setSummary(null);
    else if (isValidGeneratedSummary(args.summary))
      setters.setSummary(args.summary as SummaryConfig);
  }
}
