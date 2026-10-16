// SPDX-License-Identifier: Apache-2.0
import type { DatasetMetric } from "../api/types";

// REV-119 : remplace chaque mesure `{ metric: nom }` d'une requête `statistics`
// par la définition (field/agg/p) de la métrique nommée du dataset. Le libellé de
// ligne est la CLÉ de la métrique (stable), sauf libellé explicite — même règle que
// core `resolve_metrics`. Métrique inconnue : erreur, jamais un `count` silencieux.
export function resolveMetricMeasures(
  query: Record<string, unknown>,
  metrics: Record<string, DatasetMetric> | undefined,
): Record<string, unknown> {
  const measures = query.measures;
  if (!Array.isArray(measures) || !measures.some((m) => m && m.metric)) return query;
  return {
    ...query,
    measures: measures.map((m) => {
      if (!m?.metric) return m;
      const named = metrics?.[m.metric as string];
      if (!named) throw new Error(`unknown metric '${String(m.metric)}'`);
      return {
        field: named.field ?? undefined,
        agg: named.agg,
        p: named.p ?? undefined,
        label: m.label || m.metric,
      };
    }),
  };
}
