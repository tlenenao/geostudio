// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { DatasetMetric } from "../api/types";
import { t } from "../i18n";
import { Button } from "../ui/kit/Button";
import { ANALYTICS_AGGREGATES, aggregateNeedsP, DEFAULT_PERCENTILE } from "./aggregates";
import { PercentileInput } from "./PercentileInput";
import "../i18n/domains/admin";

// Même regex et plafond que core DatasetPayload (REV-119).
const METRIC_KEY = /^[a-z][A-Za-z0-9_]{0,63}$/;
const MAX_METRICS = 50;
const cls = "h-9 rounded border border-control bg-surface px-2 text-xs text-ink";

// Éditeur des métriques nommées d'un dataset : clé stable + agrégat + champ.
// Pas de CEL libre (un seul moteur d'évaluation, cf. spec REV-119).
export function DatasetMetricsEditor({
  metrics,
  fieldNames,
  onChange,
}: {
  metrics: Record<string, DatasetMetric>;
  fieldNames: string[];
  onChange: (next: Record<string, DatasetMetric>) => void;
}) {
  const [newKey, setNewKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  function patch(key: string, changes: Partial<DatasetMetric>) {
    onChange({ ...metrics, [key]: { ...metrics[key], ...changes } });
  }
  function add() {
    if (!METRIC_KEY.test(newKey)) return setError(t("datasetMetrics.keyInvalid"));
    if (newKey in metrics) return setError(t("datasetMetrics.keyDuplicate"));
    if (Object.keys(metrics).length >= MAX_METRICS) return setError(t("datasetMetrics.tooMany"));
    setError(null);
    onChange({ ...metrics, [newKey]: { agg: "count" } });
    setNewKey("");
  }
  function remove(key: string) {
    const next = { ...metrics };
    delete next[key];
    onChange(next);
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <p className="text-xs font-medium text-ink-2">{t("datasetMetrics.heading")}</p>
      {Object.entries(metrics).map(([key, m]) => (
        <div key={key} className="flex flex-wrap items-center gap-1 rounded border border-rule p-2">
          <code className="text-xs">{key}</code>
          <input
            aria-label={t("datasetMetrics.labelAria", { key })}
            placeholder={t("datasetMetrics.labelPlaceholder")}
            className={cls}
            value={m.label ?? ""}
            onChange={(e) => patch(key, { label: e.target.value || null })}
          />
          <select
            aria-label={t("datasetMetrics.aggAria", { key })}
            className={cls}
            value={m.agg}
            onChange={(e) =>
              patch(key, {
                agg: e.target.value,
                p: aggregateNeedsP(e.target.value) ? DEFAULT_PERCENTILE : null,
                field: e.target.value === "count" ? null : m.field,
              })
            }
          >
            {ANALYTICS_AGGREGATES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
          {m.agg !== "count" && (
            <select
              aria-label={t("datasetMetrics.fieldAria", { key })}
              className={cls}
              value={m.field ?? ""}
              onChange={(e) => patch(key, { field: e.target.value || null })}
            >
              <option value="">{t("datasetMetrics.fieldPlaceholder")}</option>
              {fieldNames.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          )}
          {aggregateNeedsP(m.agg) && (
            <PercentileInput
              label={t("datasetMetrics.percentileAria", { key })}
              value={Number(m.p ?? DEFAULT_PERCENTILE)}
              onCommit={(p) => patch(key, { p })}
            />
          )}
          <input
            aria-label={t("datasetMetrics.formatAria", { key })}
            placeholder={t("datasetMetrics.formatPlaceholder")}
            className={`${cls} w-24`}
            value={m.format ?? ""}
            onChange={(e) => patch(key, { format: e.target.value || null })}
          />
          <input
            aria-label={t("datasetMetrics.unitAria", { key })}
            placeholder={t("datasetMetrics.unitPlaceholder")}
            className={`${cls} w-20`}
            value={m.unit ?? ""}
            onChange={(e) => patch(key, { unit: e.target.value || null })}
          />
          <button
            type="button"
            aria-label={t("datasetMetrics.removeAria", { key })}
            className="text-xs text-danger"
            onClick={() => remove(key)}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <input
          aria-label={t("datasetMetrics.newKeyAria")}
          placeholder={t("datasetMetrics.newKeyPlaceholder")}
          className={cls}
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
        />
        <Button type="button" variant="outline" size="sm" onClick={add}>
          {t("datasetMetrics.addButton")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
