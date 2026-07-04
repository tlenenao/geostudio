import type { Variable } from "../api/types";

export function VariablesPanel({
  variables,
  onChange,
}: {
  variables: Variable[];
  onChange: (variables: Variable[]) => void;
}) {
  function addVariable() {
    const v: Variable = { id: crypto.randomUUID(), name: `Variable ${variables.length + 1}`, initialValue: "" };
    onChange([...variables, v]);
  }
  function remove(id: string) {
    onChange(variables.filter((v) => v.id !== id));
  }
  function rename(id: string, name: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, name } : v)));
  }
  function setInitialValue(id: string, initialValue: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, initialValue } : v)));
  }
  return (
    <ul className="flex flex-col gap-1">
      {variables.map((v) => (
        <li key={v.id} className="flex items-center gap-1 rounded border border-slate-200 p-1 text-xs">
          <input
            aria-label={`Renommer la variable ${v.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            defaultValue={v.name}
            onChange={(e) => rename(v.id, e.target.value)}
          />
          <input
            aria-label={`Valeur initiale de la variable ${v.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            defaultValue={v.initialValue}
            onChange={(e) => setInitialValue(v.id, e.target.value)}
          />
          <button type="button" aria-label={`Retirer la variable ${v.id}`} className="text-red-600" onClick={() => remove(v.id)}>✕</button>
        </li>
      ))}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addVariable}>
          Ajouter une variable
        </button>
      </li>
    </ul>
  );
}
