// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
// Source unique des agrégats du chemin analytique (AggregateRequestBody,
// core/app/analytics/aggregate.py). Les deux <select> de DataSourcePanel
// (requête simple et mesures) lisent cette liste au lieu de la dupliquer.
// L'ordre est celui affiché à l'auteur : du plus courant au plus rare.
export const ANALYTICS_AGGREGATES: { value: string; label: string }[] = (
  ["count", "countDistinct", "sum", "avg", "median", "percentile", "stddev", "min", "max"] as const
).map((value) => ({ value, label: t(`aggregate.${value}`) }));

// Seul "percentile" porte un paramètre. Il est exprimé en POURCENTAGE
// (0 < p < 100), jamais en fraction — le serveur divise par 100 lui-même.
export function aggregateNeedsP(agg: string): boolean {
  return agg === "percentile";
}

// Valeur par défaut posée quand l'auteur bascule un agrégat vers "percentile"
// dans DataSourcePanel — sans elle la source part immédiatement une requête
// "percentile" sans p, que le cœur rejette systématiquement en 422. Reprise
// telle quelle par l'assistant de requête visuelle (Task 10).
export const DEFAULT_PERCENTILE = 50;
