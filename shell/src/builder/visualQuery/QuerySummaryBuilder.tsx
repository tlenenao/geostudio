// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema } from "../../api/types";
import { DEFAULT_PERCENTILE } from "../aggregates";
import { PercentileInput } from "../PercentileInput";
import { MetricConfig, MetricFunction, SummaryConfig } from "./inferSchema";
import { Button } from "../../ui/button";

const FUNCTION_LABELS: Record<MetricFunction, string> = {
  count: "Compter",
  countDistinct: "Compter les valeurs distinctes",
  sum: "Somme",
  avg: "Moyenne",
  median: "Médiane",
  percentile: "Centile",
  stddev: "Écart-type",
  min: "Minimum",
  max: "Maximum",
};

// sum/avg/min/max n'ont de sens que sur une colonne numérique — defaulter sur
// schema.fields[0] sans regarder le type produirait un choix absurde (ex.
// sommer une colonne texte) dès que le premier champ du schéma n'est pas
// numérique. Repli sur schema.fields[0] seulement si aucun champ numérique
// n'existe (mieux qu'un champ vide, laisse l'utilisateur corriger).
function firstNumericField(schema: CollectionSchema): string | null {
  const numeric = schema.fields.find((f) => f.type === "integer" || f.type === "number");
  return (numeric ?? schema.fields[0])?.name ?? null;
}

export function QuerySummaryBuilder({
  schema,
  value,
  onChange,
}: {
  schema: CollectionSchema;
  value: SummaryConfig;
  onChange: (next: SummaryConfig) => void;
}) {
  function toggleGroupBy(name: string, checked: boolean) {
    onChange({
      ...value,
      groupBy: checked ? [...value.groupBy, name] : value.groupBy.filter((g) => g !== name),
    });
  }
  function updateMetric(index: number, patch: Partial<MetricConfig>) {
    const metrics = value.metrics.map((m, i) => {
      if (i !== index) return m;
      const next = { ...m, ...patch };
      if (next.function === "count") next.sourceColumn = null;
      else if (next.sourceColumn === null) next.sourceColumn = firstNumericField(schema);
      if (next.function === "percentile") {
        if (next.p === null) next.p = DEFAULT_PERCENTILE;
      } else {
        next.p = null;
      }
      return next;
    });
    onChange({ ...value, metrics });
  }
  function addMetric() {
    onChange({
      ...value,
      metrics: [
        ...value.metrics,
        {
          alias: `metrique_${value.metrics.length + 1}`,
          function: "count",
          sourceColumn: null,
          p: null,
        },
      ],
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-slate-500">Regrouper par</p>
      {schema.fields.map((f) => (
        <label key={f.name} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label={`Regrouper par ${f.name}`}
            checked={value.groupBy.includes(f.name)}
            onChange={(e) => toggleGroupBy(f.name, e.target.checked)}
          />
          {f.name}
        </label>
      ))}
      <p className="text-xs font-medium text-slate-500">Métriques</p>
      {value.metrics.map((metric, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            aria-label={`Fonction de la métrique ${i + 1}`}
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={metric.function}
            onChange={(e) => updateMetric(i, { function: e.target.value as MetricFunction })}
          >
            {Object.entries(FUNCTION_LABELS).map(([fn, label]) => (
              <option key={fn} value={fn}>
                {label}
              </option>
            ))}
          </select>
          {metric.function !== "count" && (
            <select
              aria-label={`Colonne de la métrique ${i + 1}`}
              className="h-8 rounded border border-slate-300 px-2 text-xs"
              value={metric.sourceColumn ?? ""}
              onChange={(e) => updateMetric(i, { sourceColumn: e.target.value })}
            >
              {schema.fields.map((f) => (
                <option key={f.name} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
          )}
          {metric.function === "percentile" && (
            <PercentileInput
              label={`Centile de la métrique ${i + 1}`}
              // `??` ne remplace pas NaN (seulement null/undefined) — Number.isFinite
              // couvre aussi ce cas, en plus de null.
              value={Number.isFinite(metric.p) ? (metric.p as number) : DEFAULT_PERCENTILE}
              onCommit={(p) => updateMetric(i, { p })}
            />
          )}
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={addMetric}>
        Ajouter une métrique
      </Button>
    </div>
  );
}
