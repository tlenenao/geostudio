// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { Variable, VariableType } from "../api/types";
import { t } from "../i18n";
import { Button } from "../ui/kit/Button";

const TYPE_LABELS: Record<VariableType, string> = {
  string: t("variablesPanel.typeString"),
  number: t("variablesPanel.typeNumber"),
  bool: t("variablesPanel.typeBool"),
  date: t("variablesPanel.typeDate"),
  record: t("variablesPanel.typeRecord"),
  list: t("variablesPanel.typeList"),
};

function defaultValueFor(type: VariableType): Variable["initialValue"] {
  switch (type) {
    case "number":
      return 0;
    case "bool":
      return false;
    case "record":
      return null;
    case "list":
      return [];
    default:
      return "";
  }
}

// P10.11 : un nom de variable sert de clé de valeur au runtime et d'identifiant CEL —
// non vide, identifiant valide, unique.
function nameError(name: string, others: string[]): string | null {
  if (name.trim() === "") return t("variablesPanel.nameEmpty");
  if (!/^[A-Za-z_]\w*$/.test(name)) return t("variablesPanel.nameInvalid");
  if (others.includes(name)) return t("variablesPanel.nameDuplicate");
  return null;
}

// Champ contrôlé par le brouillon (P10.08 : suit l'undo/redo) mais qui ne
// valide dans le brouillon qu'un nom valide ; le texte invalide reste local.
function NameField({
  id,
  value,
  others,
  onCommit,
}: {
  id: string;
  value: string;
  others: string[];
  onCommit: (name: string) => void;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const error = nameError(text, others);
  return (
    <span className="flex flex-col">
      <input
        aria-label={t("variablesPanel.renameAria", { id })}
        aria-invalid={error !== null}
        className="w-16 rounded border border-rule px-1"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (!nameError(e.target.value, others)) onCommit(e.target.value);
        }}
        onBlur={() => error && setText(value)}
      />
      {error && (
        <span role="alert" className="text-danger">
          {error}
        </span>
      )}
    </span>
  );
}

export function VariablesPanel({
  variables,
  onChange,
}: {
  variables: Variable[];
  onChange: (variables: Variable[]) => void;
}) {
  function addVariable() {
    const taken = new Set(variables.map((x) => x.name));
    let n = variables.length + 1;
    while (taken.has(`variable_${n}`)) n++;
    const v: Variable = {
      id: crypto.randomUUID(),
      name: `variable_${n}`,
      type: "string",
      initialValue: "",
    };
    onChange([...variables, v]);
  }
  function remove(id: string) {
    onChange(variables.filter((v) => v.id !== id));
  }
  function rename(id: string, name: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, name } : v)));
  }
  function setType(id: string, type: VariableType) {
    onChange(
      variables.map((v) => (v.id === id ? { ...v, type, initialValue: defaultValueFor(type) } : v)),
    );
  }
  function setInitialValue(id: string, initialValue: Variable["initialValue"]) {
    onChange(variables.map((v) => (v.id === id ? { ...v, initialValue } : v)));
  }
  return (
    <ul className="flex flex-col gap-1">
      {variables.map((v) => {
        const type = v.type ?? "string";
        return (
          <li key={v.id} className="flex items-center gap-1 rounded border border-rule p-1 text-xs">
            <NameField
              id={v.id}
              value={v.name}
              others={variables.filter((x) => x.id !== v.id).map((x) => x.name)}
              onCommit={(name) => rename(v.id, name)}
            />
            <select
              aria-label={t("variablesPanel.typeAria", { id: v.id })}
              className="rounded border border-rule px-1"
              value={type}
              onChange={(e) => setType(v.id, e.target.value as VariableType)}
            >
              {(Object.keys(TYPE_LABELS) as VariableType[]).map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABELS[t]}
                </option>
              ))}
            </select>
            {type === "string" && (
              <input
                aria-label={t("variablesPanel.initialValueAria", { id: v.id })}
                className="w-16 rounded border border-rule px-1"
                value={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {type === "number" && (
              <input
                aria-label={t("variablesPanel.initialValueAria", { id: v.id })}
                type="number"
                className="w-16 rounded border border-rule px-1"
                value={Number(v.initialValue ?? 0)}
                onChange={(e) => setInitialValue(v.id, Number(e.target.value))}
              />
            )}
            {type === "bool" && (
              <input
                aria-label={t("variablesPanel.initialValueAria", { id: v.id })}
                type="checkbox"
                checked={Boolean(v.initialValue)}
                onChange={(e) => setInitialValue(v.id, e.target.checked)}
              />
            )}
            {type === "date" && (
              <input
                aria-label={t("variablesPanel.initialValueAria", { id: v.id })}
                type="date"
                className="rounded border border-rule px-1"
                value={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {(type === "record" || type === "list") && (
              <span className="text-ink-2">{t("variablesPanel.definedByWiring")}</span>
            )}
            <button
              type="button"
              aria-label={t("variablesPanel.removeAria", { id: v.id })}
              className="text-danger"
              onClick={() => remove(v.id)}
            >
              ✕
            </button>
          </li>
        );
      })}
      <li>
        <Button type="button" size="sm" variant="outline" onClick={addVariable}>
          {t("variablesPanel.addButton")}
        </Button>
      </li>
    </ul>
  );
}
