// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { PipelineNode, PipelineOpEntry, PipelineOpParamProperty } from "../../api/types";
import { CollectionParamSelect } from "./CollectionParamSelect";
import { SecretParamSelect } from "./SecretParamSelect";

// Édite un dict[str, str] (transform.aggregate.metrics) ou dict[str, str|null]
// (transform.select.columns) sous forme de lignes clé/valeur. Convention
// MVP pour transform.select : une valeur vidée équivaut à `null` (supprime
// la colonne) au moment de la sauvegarde — cf. design SP-15b §4.4 et le
// manifeste TransformSelectParams.columns côté cœur.
function KeyValueField({
  name,
  value,
  onChange,
}: {
  name: string;
  value: Record<string, string | null>;
  onChange: (next: Record<string, string | null>) => void;
}) {
  const rows = Object.entries(value);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-2">{name}</span>
      {rows.map(([key, val], i) => (
        <div key={i} className="flex gap-1">
          <input
            aria-label={`${name} clé ${i + 1}`}
            className="h-8 w-1/2 rounded border border-rule bg-surface px-2 text-xs text-ink"
            value={key}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              delete next[key];
              next[e.target.value] = val;
              onChange(next);
            }}
          />
          <input
            aria-label={`${name} valeur ${i + 1}`}
            className="h-8 w-1/2 rounded border border-rule bg-surface px-2 text-xs text-ink"
            value={val ?? ""}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              next[key] = e.target.value === "" ? null : e.target.value;
              onChange(next);
            }}
          />
        </div>
      ))}
      <button
        type="button"
        className="w-fit text-xs text-accent hover:underline"
        onClick={() => onChange({ ...value, "": "" })}
      >
        Ajouter {name}
      </button>
    </div>
  );
}

function StringListField({
  name,
  value,
  onChange,
}: {
  name: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      {name}
      <input
        aria-label={name}
        className="h-8 rounded border border-rule bg-surface px-2 text-ink"
        defaultValue={value.join(", ")}
        onChange={(e) =>
          onChange(
            e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
      />
    </label>
  );
}

export function PipelineNodeInspector({
  node,
  opEntry,
  errors,
  onChange,
}: {
  node: PipelineNode;
  opEntry: PipelineOpEntry;
  errors: string[];
  onChange: (params: Record<string, unknown>) => void;
}) {
  const [params, setParams] = useState(node.params);

  useEffect(() => {
    setParams(node.params);
  }, [node.params]);

  function setField(name: string, value: unknown) {
    const newParams = { ...params, [name]: value };
    setParams(newParams);
    onChange(newParams);
  }

  // Rendu générique de prop.description (JSON schema) sous le contrôle,
  // quel que soit son type — pas de branche spécifique à un champ nommé
  // "mode" : tout futur champ portant une description en bénéficiera.
  function renderField(name: string, prop: PipelineOpParamProperty) {
    const control = renderControl(name, prop);
    if (!prop.description) return control;
    return (
      <div key={name} className="flex flex-col gap-1">
        {control}
        <p className="text-xs text-ink-2">{prop.description}</p>
      </div>
    );
  }

  function renderControl(name: string, prop: PipelineOpParamProperty) {
    if (prop.format === "collection-id") {
      return (
        <CollectionParamSelect
          key={name}
          ariaLabel={name}
          value={String(params[name] ?? "")}
          variant={node.kind === "writer" ? "writable" : "readable"}
          onChange={(id) => setField(name, id)}
        />
      );
    }
    if (prop.format === "secret-name") {
      return (
        <SecretParamSelect
          key={name}
          ariaLabel={name}
          value={String(params[name] ?? "")}
          onChange={(v) => setField(name, v)}
        />
      );
    }
    if (prop.enum) {
      return (
        <label key={name} className="flex flex-col gap-1 text-xs">
          {name}
          <select
            aria-label={name}
            className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={String(params[name] ?? prop.default ?? "")}
            onChange={(e) => setField(name, e.target.value)}
          >
            {prop.enum.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      );
    }
    if (prop.type === "boolean") {
      return (
        <label key={name} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label={name}
            checked={Boolean(params[name])}
            onChange={(e) => setField(name, e.target.checked)}
          />
          {name}
        </label>
      );
    }
    if (prop.type === "array") {
      return (
        <StringListField
          key={name}
          name={name}
          value={(params[name] as string[] | undefined) ?? []}
          onChange={(v) => setField(name, v)}
        />
      );
    }
    if (prop.type === "object") {
      return (
        <KeyValueField
          key={name}
          name={name}
          value={(params[name] as Record<string, string | null> | undefined) ?? {}}
          onChange={(v) => setField(name, v)}
        />
      );
    }
    return (
      <label key={name} className="flex flex-col gap-1 text-xs">
        {name}
        <input
          type={prop.type === "number" || prop.type === "integer" ? "number" : "text"}
          aria-label={name}
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
          value={String(params[name] ?? "")}
          onChange={(e) =>
            setField(
              name,
              prop.type === "number" || prop.type === "integer"
                ? Number(e.target.value)
                : e.target.value,
            )
          }
        />
      </label>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-2">
      {Object.entries(opEntry.paramsSchema.properties).map(([name, prop]) =>
        renderField(name, prop),
      )}
      {errors.map((err) => (
        <p key={err} role="alert" className="text-xs text-danger">
          {err}
        </p>
      ))}
    </div>
  );
}
