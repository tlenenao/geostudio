// SPDX-License-Identifier: Apache-2.0
import type { FilterOperator, FilterRow } from "../visualQuery/compileFilter";
import type {
  JoinConfig,
  MetricConfig,
  MetricFunction,
  SummaryConfig,
} from "../visualQuery/inferSchema";
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

// metricExpr (compilePipeline.ts) fait `quoteIdent(metric.sourceColumn!)` pour
// toute fonction autre que "count" — un `sourceColumn` absent y jetterait un
// TypeError non rattrapé, potentiellement après création de ressources
// backend réelles (VisualQueryWizardPage, flux "create"). "percentile" a en
// plus sa propre garde runtime sur `p` (0 < p < 100, cf. metricExpr) : un `p`
// non numérique ou hors bornes y lève une Error explicite, mais tout aussi
// non rattrapée par l'appelant de ce module. Un metric invalide sur l'un ou
// l'autre point doit être traité comme un join invalide : le résumé entier
// est ignoré (jamais une application partielle groupBy-sans-metrics).
function isValidGeneratedMetric(m: unknown): m is MetricConfig {
  if (typeof m !== "object" || m === null) return false;
  const metric = m as Record<string, unknown>;
  if (typeof metric.alias !== "string") return false;
  if (
    typeof metric.function !== "string" ||
    !METRIC_FUNCTIONS.has(metric.function as MetricFunction)
  )
    return false;
  const fn = metric.function as MetricFunction;

  // Round-trip contract avec decompileMetrics (compilePipeline.ts) : seul
  // "count" produit/attend sourceColumn: null, toute autre fonction attend
  // une chaîne non nulle (c'est elle que metricExpr quote dans le SQL émis).
  if (fn === "count") {
    if (metric.sourceColumn !== null) return false;
  } else if (typeof metric.sourceColumn !== "string") {
    return false;
  }

  // Idem pour p : seul "percentile" en a besoin (0 < p < 100, borne vérifiée
  // à l'exécution par metricExpr) ; toute autre fonction attend p: null.
  if (fn === "percentile") {
    if (typeof metric.p !== "number" || !(metric.p > 0 && metric.p < 100)) return false;
  } else if (metric.p !== null) {
    return false;
  }

  return true;
}

function isValidGeneratedSummary(summary: unknown): summary is SummaryConfig {
  if (typeof summary !== "object" || summary === null) return false;
  const s = summary as Record<string, unknown>;
  if (!Array.isArray(s.groupBy) || !s.groupBy.every((g) => typeof g === "string")) return false;
  if (!Array.isArray(s.metrics)) return false;
  return s.metrics.every(isValidGeneratedMetric);
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
