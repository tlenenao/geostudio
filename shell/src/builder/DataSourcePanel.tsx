import type { DataSource } from "../api/types";

type Measure = { field?: string; agg: string; label?: string };

const inputCls = "h-8 w-full rounded border border-slate-300 px-2 text-xs";
const selectCls = "h-8 w-full rounded border border-slate-300 text-xs";

export function DataSourcePanel({
  sources,
  onChange,
}: {
  sources: DataSource[];
  onChange: (sources: DataSource[]) => void;
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
              <select aria-label={`Type de la source ${s.id}`} className="h-8 rounded border border-slate-300 text-xs"
                value={s.type} onChange={(e) => patch(s.id, { type: e.target.value as DataSource["type"] })}>
                <option value="features">Features</option>
                <option value="statistics">Statistiques</option>
                <option value="static">Statique</option>
              </select>
              <button type="button" aria-label={`Retirer ${s.layer || s.id}`} className="text-xs text-red-600" onClick={() => remove(s.id)}>✕</button>
            </div>
            {(s.type === "features" || s.type === "statistics") && (
              <input aria-label={`Collection de la source ${s.id}`} placeholder="collection"
                className={`mt-1 ${inputCls}`}
                value={s.layer} onChange={(e) => patch(s.id, { layer: e.target.value })} />
            )}
            {s.type === "statistics" && (
              <div className="mt-1 flex flex-col gap-1">
                <input aria-label={`Grouper par (source ${s.id})`} placeholder="grouper par (axe X)"
                  className={inputCls}
                  value={String(s.query.groupBy ?? "")} onChange={(e) => patchQuery(s.id, { groupBy: e.target.value })} />
                <input aria-label={`Séparer par (source ${s.id})`} placeholder="séparer par (séries, optionnel)"
                  className={inputCls}
                  value={String(s.query.split ?? "")} onChange={(e) => patchQuery(s.id, { split: e.target.value })} />
                <div className="flex gap-1">
                  <select aria-label={`Agrégation (source ${s.id})`} className={selectCls}
                    value={String(s.query.agg ?? "count")} onChange={(e) => patchQuery(s.id, { agg: e.target.value })}>
                    <option value="count">Nombre</option>
                    <option value="sum">Somme</option>
                    <option value="avg">Moyenne</option>
                    <option value="min">Min</option>
                    <option value="max">Max</option>
                  </select>
                  <input aria-label={`Champ agrégé (source ${s.id})`} placeholder="champ"
                    className={inputCls}
                    value={String(s.query.field ?? "")} onChange={(e) => patchQuery(s.id, { field: e.target.value })} />
                </div>
                {measuresOf(s).length > 0 && (
                  <ul className="flex flex-col gap-1">
                    {measuresOf(s).map((m, mi) => (
                      <li key={mi} className="flex items-center gap-1">
                        <select aria-label={`Agrégation mesure ${mi + 1} (source ${s.id})`} className={selectCls}
                          value={m.agg} onChange={(e) => setMeasures(s, measuresOf(s).map((x, i) => (i === mi ? { ...x, agg: e.target.value } : x)))}>
                          <option value="count">Nombre</option>
                          <option value="sum">Somme</option>
                          <option value="avg">Moyenne</option>
                          <option value="min">Min</option>
                          <option value="max">Max</option>
                        </select>
                        <input aria-label={`Champ mesure ${mi + 1} (source ${s.id})`} placeholder="champ"
                          className={inputCls}
                          value={String(m.field ?? "")} onChange={(e) => setMeasures(s, measuresOf(s).map((x, i) => (i === mi ? { ...x, field: e.target.value } : x)))} />
                        <button type="button" aria-label={`Retirer la mesure ${mi + 1} de ${s.id}`} className="text-xs text-red-600"
                          onClick={() => setMeasures(s, measuresOf(s).filter((_, i) => i !== mi))}>✕</button>
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" aria-label={`Ajouter une mesure à ${s.id}`}
                  className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                  onClick={() => setMeasures(s, [...measuresOf(s), { agg: "sum", field: "" }])}>
                  + Mesure
                </button>
              </div>
            )}
          </li>
        ))}
        {sources.length === 0 && <li className="text-xs text-slate-400">Aucune source.</li>}
      </ul>
      <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
        Ajouter une source
      </button>
    </div>
  );
}
