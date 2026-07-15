// SPDX-License-Identifier: Apache-2.0
import type { Variable, VariableType } from "../api/types";

const TYPE_LABELS: Record<VariableType, string> = {
  string: "Texte",
  number: "Nombre",
  bool: "Booléen",
  date: "Date",
  record: "Enregistrement",
  list: "Liste",
};

function defaultValueFor(type: VariableType): Variable["initialValue"] {
  switch (type) {
    case "number": return 0;
    case "bool": return false;
    case "record": return null;
    case "list": return [];
    default: return "";
  }
}

export function VariablesPanel({
  variables,
  onChange,
}: {
  variables: Variable[];
  onChange: (variables: Variable[]) => void;
}) {
  function addVariable() {
    const v: Variable = { id: crypto.randomUUID(), name: `Variable ${variables.length + 1}`, type: "string", initialValue: "" };
    onChange([...variables, v]);
  }
  function remove(id: string) {
    onChange(variables.filter((v) => v.id !== id));
  }
  function rename(id: string, name: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, name } : v)));
  }
  function setType(id: string, type: VariableType) {
    onChange(variables.map((v) => (v.id === id ? { ...v, type, initialValue: defaultValueFor(type) } : v)));
  }
  function setInitialValue(id: string, initialValue: Variable["initialValue"]) {
    onChange(variables.map((v) => (v.id === id ? { ...v, initialValue } : v)));
  }
  return (
    <ul className="flex flex-col gap-1">
      {variables.map((v) => {
        const type = v.type ?? "string";
        return (
          <li key={v.id} className="flex items-center gap-1 rounded border border-slate-200 p-1 text-xs">
            <input
              aria-label={`Renommer la variable ${v.id}`}
              className="w-16 rounded border border-slate-300 px-1"
              defaultValue={v.name}
              onChange={(e) => rename(v.id, e.target.value)}
            />
            <select
              aria-label={`Type de la variable ${v.id}`}
              className="rounded border border-slate-300 px-1"
              value={type}
              onChange={(e) => setType(v.id, e.target.value as VariableType)}
            >
              {(Object.keys(TYPE_LABELS) as VariableType[]).map((t) => (
                <option key={t} value={t}>{TYPE_LABELS[t]}</option>
              ))}
            </select>
            {type === "string" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                className="w-16 rounded border border-slate-300 px-1"
                defaultValue={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {type === "number" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="number"
                className="w-16 rounded border border-slate-300 px-1"
                defaultValue={Number(v.initialValue ?? 0)}
                onChange={(e) => setInitialValue(v.id, Number(e.target.value))}
              />
            )}
            {type === "bool" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="checkbox"
                checked={Boolean(v.initialValue)}
                onChange={(e) => setInitialValue(v.id, e.target.checked)}
              />
            )}
            {type === "date" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="date"
                className="rounded border border-slate-300 px-1"
                defaultValue={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {(type === "record" || type === "list") && (
              <span className="text-slate-400">Définie par câblage d'action</span>
            )}
            <button type="button" aria-label={`Retirer la variable ${v.id}`} className="text-red-600" onClick={() => remove(v.id)}>✕</button>
          </li>
        );
      })}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addVariable}>
          Ajouter une variable
        </button>
      </li>
    </ul>
  );
}
