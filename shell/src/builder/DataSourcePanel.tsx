import type { DataSource } from "../api/types";

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
      { id: crypto.randomUUID(), type: "features", service: "featureserv", layer: "", query: {} },
    ]);
  }
  function remove(id: string) {
    onChange(sources.filter((s) => s.id !== id));
  }
  function patch(id: string, changes: Partial<DataSource>) {
    onChange(sources.map((s) => (s.id === id ? { ...s, ...changes } : s)));
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
                <option value="static">Statique</option>
              </select>
              <button type="button" aria-label={`Retirer ${s.layer || s.id}`} className="text-xs text-red-600" onClick={() => remove(s.id)}>✕</button>
            </div>
            {s.type === "features" && (
              <input aria-label={`Collection de la source ${s.id}`} placeholder="collection"
                className="mt-1 h-8 w-full rounded border border-slate-300 px-2 text-xs"
                value={s.layer} onChange={(e) => patch(s.id, { layer: e.target.value })} />
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
