// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { DataRecord, DataSource } from "../api/types";
import type { BucketGranularity } from "../lib/comparisonWindow";
import { ANALYTICS_AGGREGATES, aggregateNeedsP, DEFAULT_PERCENTILE } from "./aggregates";
import { PercentileInput } from "./PercentileInput";

type Measure = { field?: string; agg: string; label?: string; p?: number };

const BUCKET_OPTIONS: { value: BucketGranularity; label: string }[] = [
  { value: "hour", label: "Heure" },
  { value: "day", label: "Jour" },
  { value: "week", label: "Semaine" },
  { value: "month", label: "Mois" },
  { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Année" },
];

// Le cœur refuse un bucket sans groupBy à un seul champ
// (_validate_fields: "bucket requires a single-field groupBy"). L'UI
// reflète cet invariant au lieu de laisser construire une requête que le
// serveur rejettera.
function bucketAllowed(groupBy: unknown): boolean {
  if (Array.isArray(groupBy)) return groupBy.length === 1;
  return typeof groupBy === "string" && groupBy.trim() !== "";
}

// A single field ("region") is passed through unchanged; a comma-separated
// value ("origin,destination") becomes a string[] — the multi-field tidy
// groupBy that sankey/treemap/sunburst need (SP-14f).
function parseGroupBy(raw: string): string | string[] {
  const parts = raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.length > 1 ? parts : raw;
}

function groupByDisplayValue(groupBy: unknown): string {
  return Array.isArray(groupBy) ? groupBy.join(",") : String(groupBy ?? "");
}

const inputCls = "h-8 w-full rounded border border-slate-300 px-2 text-xs";
const selectCls = "h-8 w-full rounded border border-slate-300 text-xs";

function StaticRecordRow({
  record,
  onChange,
  onRemove,
}: {
  record: DataRecord;
  onChange: (properties: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [text, setText] = useState(JSON.stringify(record.properties));
  const [error, setError] = useState<string | null>(null);
  function commit() {
    try {
      const parsed = JSON.parse(text);
      setError(null);
      onChange(parsed);
    } catch {
      setError("JSON invalide — modification non enregistrée.");
    }
  }
  return (
    <div className="flex flex-col gap-1 rounded border border-slate-200 p-1">
      <div className="flex items-center gap-1">
        <textarea
          aria-label={`Propriétés de l'enregistrement ${record.id}`}
          className="h-16 flex-1 rounded border border-slate-300 p-1 font-mono text-xs"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
        />
        <button
          type="button"
          aria-label={`Retirer l'enregistrement ${record.id}`}
          className="text-xs text-red-600"
          onClick={onRemove}
        >
          ✕
        </button>
      </div>
      {error && (
        <span role="alert" className="text-xs text-red-600">
          {error}
        </span>
      )}
    </div>
  );
}

export function DataSourcePanel({
  sources,
  onChange,
  onPromote,
  promotingId,
}: {
  sources: DataSource[];
  onChange: (sources: DataSource[]) => void;
  onPromote?: (id: string) => void;
  promotingId?: string | null;
}) {
  function add() {
    onChange([
      ...sources,
      { id: crypto.randomUUID(), type: "features", service: "core", layer: "", query: {} },
    ]);
  }
  function remove(id: string) {
    onChange(sources.filter((s) => s.id !== id));
  }
  function patch(id: string, changes: Partial<DataSource>) {
    onChange(sources.map((s) => (s.id === id ? { ...s, ...changes } : s)));
  }
  function patchQuery(id: string, changes: Record<string, unknown>) {
    const s = sources.find((x) => x.id === id);
    patch(id, { query: { ...(s?.query ?? {}), ...changes } });
  }
  function measuresOf(s: DataSource): Measure[] {
    return Array.isArray(s.query.measures) ? (s.query.measures as Measure[]) : [];
  }
  function setMeasures(s: DataSource, measures: Measure[]) {
    patchQuery(s.id, { measures });
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {sources.map((s) => (
          <li key={s.id} className="rounded border border-slate-200 p-2 text-sm">
            <div className="flex items-center justify-between">
              <select
                aria-label={`Type de la source ${s.id}`}
                className="h-8 rounded border border-slate-300 text-xs"
                value={s.type}
                onChange={(e) => patch(s.id, { type: e.target.value as DataSource["type"] })}
              >
                <option value="features">Features</option>
                <option value="statistics">Statistiques</option>
                <option value="static">Statique</option>
              </select>
              <button
                type="button"
                aria-label={`Retirer ${s.layer || s.id}`}
                className="text-xs text-red-600"
                onClick={() => remove(s.id)}
              >
                ✕
              </button>
            </div>
            {(s.type === "features" || s.type === "statistics") && (
              <input
                aria-label={`Collection de la source ${s.id}`}
                placeholder="collection"
                className={`mt-1 ${inputCls}`}
                value={s.layer}
                onChange={(e) => patch(s.id, { layer: e.target.value })}
              />
            )}
            {s.type === "features" &&
              onPromote &&
              (s.datasetId ? (
                <p className="mt-1 text-xs text-emerald-700">Dataset partagé actif</p>
              ) : (
                <button
                  type="button"
                  aria-label={`Promouvoir en dataset partagé ${s.id}`}
                  className="mt-1 rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100 disabled:opacity-50"
                  disabled={!s.layer || promotingId === s.id}
                  onClick={() => onPromote(s.id)}
                >
                  {promotingId === s.id ? "Promotion…" : "Promouvoir en dataset partagé"}
                </button>
              ))}
            {s.type === "statistics" && (
              <div className="mt-1 flex flex-col gap-1">
                <input
                  aria-label={`Grouper par (source ${s.id})`}
                  placeholder="grouper par (axe X, virgule = plusieurs niveaux)"
                  className={inputCls}
                  value={groupByDisplayValue(s.query.groupBy)}
                  onChange={(e) => {
                    const groupBy = parseGroupBy(e.target.value);
                    // Un bucket devenu invalide (groupBy élargi à plusieurs champs) doit
                    // être effacé ici même : c'est le seul select qui pourrait sinon le
                    // faire, et il est justement désactivé quand bucketAllowed est faux.
                    patchQuery(s.id, {
                      groupBy,
                      bucket: bucketAllowed(groupBy) ? s.query.bucket : undefined,
                    });
                  }}
                />
                <input
                  aria-label={`Séparer par (source ${s.id})`}
                  placeholder="séparer par (séries, optionnel)"
                  className={inputCls}
                  value={String(s.query.split ?? "")}
                  onChange={(e) => patchQuery(s.id, { split: e.target.value })}
                />
                <select
                  aria-label={`Grain temporel (source ${s.id})`}
                  className={selectCls}
                  disabled={!bucketAllowed(s.query.groupBy)}
                  value={String(s.query.bucket ?? "")}
                  onChange={(e) => patchQuery(s.id, { bucket: e.target.value || undefined })}
                >
                  <option value="">Aucun grain temporel</option>
                  {BUCKET_OPTIONS.map((b) => (
                    <option key={b.value} value={b.value}>
                      {b.label}
                    </option>
                  ))}
                </select>
                <div className="flex gap-1">
                  <select
                    aria-label={`Agrégation (source ${s.id})`}
                    className={selectCls}
                    value={String(s.query.agg ?? "count")}
                    onChange={(e) =>
                      patchQuery(s.id, {
                        agg: e.target.value,
                        p: aggregateNeedsP(e.target.value) ? DEFAULT_PERCENTILE : undefined,
                      })
                    }
                  >
                    {ANALYTICS_AGGREGATES.map((a) => (
                      <option key={a.value} value={a.value}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                  <input
                    aria-label={`Champ agrégé (source ${s.id})`}
                    placeholder="champ"
                    className={inputCls}
                    value={String(s.query.field ?? "")}
                    onChange={(e) => patchQuery(s.id, { field: e.target.value })}
                  />
                </div>
                {aggregateNeedsP(String(s.query.agg ?? "count")) && (
                  <PercentileInput
                    label={`Centile (source ${s.id})`}
                    value={Number(s.query.p ?? DEFAULT_PERCENTILE)}
                    className={inputCls}
                    placeholder="centile (1–99)"
                    onCommit={(p) => patchQuery(s.id, { p })}
                  />
                )}
                <input
                  aria-label={`Nombre de classes (source ${s.id})`}
                  type="number"
                  min={1}
                  max={100}
                  placeholder="classes (histogramme)"
                  className={inputCls}
                  value={String(s.query.bins ?? "")}
                  onChange={(e) =>
                    patchQuery(s.id, { bins: e.target.value ? Number(e.target.value) : undefined })
                  }
                />
                {measuresOf(s).length > 0 && (
                  <ul className="flex flex-col gap-1">
                    {measuresOf(s).map((m, mi) => (
                      <li key={mi} className="flex items-center gap-1">
                        <select
                          aria-label={`Agrégation mesure ${mi + 1} (source ${s.id})`}
                          className={selectCls}
                          value={m.agg}
                          onChange={(e) =>
                            setMeasures(
                              s,
                              measuresOf(s).map((x, i) =>
                                i === mi
                                  ? {
                                      ...x,
                                      agg: e.target.value,
                                      p: aggregateNeedsP(e.target.value)
                                        ? DEFAULT_PERCENTILE
                                        : undefined,
                                    }
                                  : x,
                              ),
                            )
                          }
                        >
                          {ANALYTICS_AGGREGATES.map((a) => (
                            <option key={a.value} value={a.value}>
                              {a.label}
                            </option>
                          ))}
                        </select>
                        <input
                          aria-label={`Champ mesure ${mi + 1} (source ${s.id})`}
                          placeholder="champ"
                          className={inputCls}
                          value={String(m.field ?? "")}
                          onChange={(e) =>
                            setMeasures(
                              s,
                              measuresOf(s).map((x, i) =>
                                i === mi ? { ...x, field: e.target.value } : x,
                              ),
                            )
                          }
                        />
                        {aggregateNeedsP(m.agg) && (
                          <PercentileInput
                            label={`Centile mesure ${mi + 1} (source ${s.id})`}
                            value={Number(m.p ?? DEFAULT_PERCENTILE)}
                            className={inputCls}
                            placeholder="centile"
                            onCommit={(p) =>
                              setMeasures(
                                s,
                                measuresOf(s).map((x, i) => (i === mi ? { ...x, p } : x)),
                              )
                            }
                          />
                        )}
                        <button
                          type="button"
                          aria-label={`Retirer la mesure ${mi + 1} de ${s.id}`}
                          className="text-xs text-red-600"
                          onClick={() =>
                            setMeasures(
                              s,
                              measuresOf(s).filter((_, i) => i !== mi),
                            )
                          }
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  type="button"
                  aria-label={`Ajouter une mesure à ${s.id}`}
                  className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                  onClick={() => setMeasures(s, [...measuresOf(s), { agg: "sum", field: "" }])}
                >
                  + Mesure
                </button>
              </div>
            )}
            {s.type === "static" && (
              <div className="mt-1 flex flex-col gap-1">
                {(Array.isArray(s.query.records) ? (s.query.records as DataRecord[]) : []).map(
                  (r) => (
                    <StaticRecordRow
                      key={r.id}
                      record={r}
                      onChange={(properties) =>
                        patchQuery(s.id, {
                          records: (s.query.records as DataRecord[]).map((x) =>
                            x.id === r.id ? { ...x, properties } : x,
                          ),
                        })
                      }
                      onRemove={() =>
                        patchQuery(s.id, {
                          records: (s.query.records as DataRecord[]).filter((x) => x.id !== r.id),
                        })
                      }
                    />
                  ),
                )}
                <button
                  type="button"
                  className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                  onClick={() =>
                    patchQuery(s.id, {
                      records: [
                        ...(Array.isArray(s.query.records)
                          ? (s.query.records as DataRecord[])
                          : []),
                        { id: crypto.randomUUID(), properties: {} },
                      ],
                    })
                  }
                >
                  Ajouter un enregistrement
                </button>
              </div>
            )}
          </li>
        ))}
        {sources.length === 0 && <li className="text-xs text-slate-400">Aucune source.</li>}
      </ul>
      <button
        type="button"
        className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
        onClick={add}
      >
        Ajouter une source
      </button>
    </div>
  );
}
