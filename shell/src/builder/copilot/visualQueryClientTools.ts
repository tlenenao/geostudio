// SPDX-License-Identifier: Apache-2.0
// Outil CLIENT du copilote sur la requête visuelle (GAP-17) — applique
// filtres/jointure/résumé générés au formulaire, jamais de création ni
// d'exécution. Un seul outil pour les trois volets.
//
// M3 (revue finale de branche GAP-17) : ce commentaire affirmait une
// « fusion » sur le patron de `setFilter` — c'est faux et ça l'a toujours
// été. Chacun des trois volets est REMPLACÉ, pas fusionné : `filters` écrase
// le tableau entier (aucune fusion ligne à ligne), `join`/`summary`
// remplacent la valeur courante. Seule exception, posée par I4 : un tableau
// `filters` dont AUCUNE ligne ne survit à la validation est un no-op, pour
// ne pas effacer silencieusement des filtres saisis à la main
// (applyVisualQueryClientOp.ts).
type ClientToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };

const FILTER_ROW_JSON_SCHEMA = {
  type: "object",
  properties: {
    column: { type: "string" },
    operator: { type: "string", enum: ["eq", "neq", "gt", "gte", "lt", "lte", "contains"] },
    value: { type: "string" },
  },
  required: ["column", "operator", "value"],
};

const METRIC_JSON_SCHEMA = {
  type: "object",
  properties: {
    alias: { type: "string" },
    function: {
      type: "string",
      enum: [
        "count",
        "countDistinct",
        "sum",
        "avg",
        "median",
        "percentile",
        "stddev",
        "min",
        "max",
      ],
    },
    sourceColumn: { type: ["string", "null"] },
    p: { type: ["number", "null"] },
  },
  required: ["alias", "function"],
};

export function buildVisualQueryClientToolSchemas(): ClientToolSchema[] {
  return [
    {
      name: "applyVisualQueryDraft",
      description:
        "Applique des filtres/une jointure/un résumé générés à la requête visuelle en cours " +
        "d'édition. Ne crée ni n'exécute rien — l'utilisateur doit valider le formulaire.",
      inputSchema: {
        type: "object",
        properties: {
          filters: { type: "array", items: FILTER_ROW_JSON_SCHEMA },
          join: {
            type: ["object", "null"],
            properties: {
              collectionId: { type: "string" },
              on: { type: "string" },
              how: { type: "string", enum: ["inner", "left"] },
            },
          },
          summary: {
            type: ["object", "null"],
            properties: {
              groupBy: { type: "array", items: { type: "string" } },
              metrics: { type: "array", items: METRIC_JSON_SCHEMA },
            },
          },
        },
      },
    },
  ];
}
