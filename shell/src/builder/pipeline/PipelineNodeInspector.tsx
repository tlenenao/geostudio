// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { PipelineNode, PipelineOpEntry, PipelineOpParamProperty } from "../../api/types";
import { t } from "../../i18n";
import { fieldErrorsFor } from "./validation";
import { CollectionParamSelect } from "./CollectionParamSelect";
import { SecretParamSelect } from "./SecretParamSelect";
import "../../i18n/domains/automation";
import { NativeSelect } from "../../ui/kit/NativeSelect";

// Édite un dict[str, str] (transform.aggregate.metrics) ou dict[str, str|null]
// (transform.select.columns) sous forme de lignes clé/valeur. Convention
// MVP pour transform.select : une valeur vidée équivaut à `null` (supprime
// la colonne) au moment de la sauvegarde — cf. design SP-15b §4.4 et le
// manifeste TransformSelectParams.columns côté cœur.
function KeyValueField({
  name,
  value,
  onChange,
  readOnly,
}: {
  name: string;
  value: Record<string, string | null>;
  onChange: (next: Record<string, string | null>) => void;
  readOnly?: boolean;
}) {
  const rows = Object.entries(value);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-2">{name}</span>
      {rows.map(([key, val], i) => (
        <div key={i} className="flex gap-1">
          <input
            aria-label={t("pipelineInspector.keyAria", { name, n: i + 1 })}
            className="h-9 w-1/2 rounded border border-control bg-surface px-2 text-xs text-ink"
            value={key}
            disabled={readOnly}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              delete next[key];
              next[e.target.value] = val;
              onChange(next);
            }}
          />
          <input
            aria-label={`${name} valeur ${i + 1}`}
            className="h-9 w-1/2 rounded border border-control bg-surface px-2 text-xs text-ink"
            value={val ?? ""}
            disabled={readOnly}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              next[key] = e.target.value === "" ? null : e.target.value;
              onChange(next);
            }}
          />
        </div>
      ))}
      {!readOnly && (
        <button
          type="button"
          className="w-fit text-xs text-accent hover:underline"
          onClick={() => onChange({ ...value, "": "" })}
        >
          Ajouter {name}
        </button>
      )}
    </div>
  );
}

// dict[str, str] / dict[str, str | None] : seul cas rendu en lignes clé/valeur texte.
function isStringMap(prop: PipelineOpParamProperty): boolean {
  const ap = prop.additionalProperties;
  if (typeof ap !== "object" || ap === null) return false;
  if (ap.type === "string") return true;
  return (ap.anyOf ?? []).every((a) => a.type === "string" || a.type === "null");
}

// REV-325 : tableaux d'objets / nombres et dictionnaires à valeurs libres (multipartFields,
// paginatorConfig…) : éditeur JSON avancé, comme layer.paint (LayersPanel). Le brouillon texte
// reste local tant que le JSON est invalide ; seul un parse réussi est propagé.
function JsonField({
  name,
  value,
  onChange,
  readOnly,
  expect,
}: {
  name: string;
  value: unknown;
  onChange: (next: unknown) => void;
  readOnly?: boolean;
  expect: "array" | "object";
}) {
  const serialized = JSON.stringify(value ?? (expect === "array" ? [] : {}), null, 2);
  const [draft, setDraft] = useState(serialized);
  const [error, setError] = useState<string | null>(null);
  // AUD-087 : suit une valeur changée de l'extérieur (undo/redo).
  useEffect(() => {
    setDraft(serialized);
    setError(null);
  }, [serialized]);
  function commit() {
    try {
      const parsed: unknown = JSON.parse(draft);
      const shapeOk =
        expect === "array"
          ? Array.isArray(parsed)
          : typeof parsed === "object" && parsed !== null && !Array.isArray(parsed);
      if (!shapeOk) throw new Error("shape");
      setError(null);
      onChange(parsed);
    } catch {
      setError(
        t(
          expect === "array"
            ? "pipelineNodeInspector.jsonNotArray"
            : "pipelineNodeInspector.jsonNotObject",
        ),
      );
    }
  }
  return (
    <label className="flex flex-col gap-1 text-xs">
      {name}
      <textarea
        className="h-24 w-full rounded-md border border-control bg-surface p-2 font-mono text-xs text-ink"
        value={draft}
        disabled={readOnly}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
      />
      {error && (
        <span role="alert" className="text-danger">
          {error}
        </span>
      )}
    </label>
  );
}

function splitList(text: string): string[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function StringListField({
  name,
  value,
  onChange,
  readOnly,
}: {
  name: string;
  value: string[];
  onChange: (next: string[]) => void;
  readOnly?: boolean;
}) {
  // AUD-087 : texte local (pour taper « a, » sans perdre la virgule) mais resynchronisé
  // quand la valeur change de l'extérieur (undo/redo) — `defaultValue` restait figé.
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  useEffect(() => {
    setText((cur) => (splitList(cur).join(", ") === joined ? cur : joined));
  }, [joined]);
  return (
    <label className="flex flex-col gap-1 text-xs">
      {name}
      <input
        className="h-9 rounded border border-control bg-surface px-2 text-ink"
        value={text}
        disabled={readOnly}
        onChange={(e) => {
          setText(e.target.value);
          onChange(splitList(e.target.value));
        }}
      />
    </label>
  );
}

export function PipelineNodeInspector({
  node,
  opEntry,
  errors,
  onChange,
  readOnly = false,
}: {
  node: PipelineNode;
  opEntry: PipelineOpEntry;
  errors: string[];
  onChange: (params: Record<string, unknown>) => void;
  // Revue finale Vague C (point 2, D55) : sans ceci, les champs restaient
  // éditables (localement, dans `params`) même pour un utilisateur en
  // lecture seule — le garde côté appelant (updateSelectedNodeParams,
  // PipelineBuilderPage.tsx) empêche la persistance mais pas l'illusion
  // d'un champ modifiable qui oublie silencieusement la saisie.
  readOnly?: boolean;
}) {
  const [params, setParams] = useState(node.params);

  useEffect(() => {
    setParams(node.params);
  }, [node.params]);

  function setField(name: string, value: unknown) {
    if (readOnly) return;
    const newParams = { ...params, [name]: value };
    // AUD-087 : un champ vidé disparaît des paramètres (le défaut de l'op s'applique)
    // au lieu d'écrire 0.
    if (value === undefined) delete newParams[name];
    setParams(newParams);
    onChange(newParams);
  }

  // Rendu générique de prop.description (JSON schema) sous le contrôle,
  // quel que soit son type — pas de branche spécifique à un champ nommé
  // "mode" : tout futur champ portant une description en bénéficiera.
  function renderField(name: string, prop: PipelineOpParamProperty) {
    const control = renderControl(name, prop);
    const fieldErrors = fieldErrorsFor(name, errors);
    return (
      <div key={name} className="flex flex-col gap-1">
        {control}
        {prop.description && <p className="text-xs text-ink-2">{prop.description}</p>}
        {fieldErrors.map((err) => (
          <p key={err} role="alert" className="text-xs text-danger">
            {err}
          </p>
        ))}
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
          disabled={readOnly}
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
          disabled={readOnly}
        />
      );
    }
    if (prop.enum) {
      return (
        <label key={name} className="flex flex-col gap-1 text-xs">
          {name}
          <NativeSelect
            className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink w-auto"
            value={String(params[name] ?? prop.default ?? "")}
            onChange={(e) => setField(name, e.target.value)}
            disabled={readOnly}
          >
            {/* j06b-015 : sans valeur ni défaut, une option vide visible — sinon le
                navigateur affiche la 1re option alors que rien n'est enregistré. */}
            {(params[name] ?? prop.default) === undefined && <option value="">—</option>}
            {prop.enum.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </NativeSelect>
        </label>
      );
    }
    if (prop.type === "boolean") {
      return (
        <label key={name} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={Boolean(params[name])}
            onChange={(e) => setField(name, e.target.checked)}
            disabled={readOnly}
          />
          {name}
        </label>
      );
    }
    if (prop.type === "array" && prop.items?.type !== "string") {
      return (
        <JsonField
          key={name}
          name={name}
          expect="array"
          value={params[name]}
          onChange={(v) => setField(name, v)}
          readOnly={readOnly}
        />
      );
    }
    if (prop.type === "object" && !isStringMap(prop)) {
      return (
        <JsonField
          key={name}
          name={name}
          expect="object"
          value={params[name]}
          onChange={(v) => setField(name, v)}
          readOnly={readOnly}
        />
      );
    }
    if (prop.type === "array") {
      return (
        <StringListField
          key={name}
          name={name}
          value={(params[name] as string[] | undefined) ?? []}
          onChange={(v) => setField(name, v)}
          readOnly={readOnly}
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
          readOnly={readOnly}
        />
      );
    }
    return (
      <label key={name} className="flex flex-col gap-1 text-xs">
        {name}
        <input
          type={prop.type === "number" || prop.type === "integer" ? "number" : "text"}
          className="h-9 rounded border border-control bg-surface px-2 text-ink"
          value={String(params[name] ?? "")}
          onChange={(e) =>
            setField(
              name,
              prop.type === "number" || prop.type === "integer"
                ? e.target.value === ""
                  ? undefined
                  : Number(e.target.value)
                : e.target.value,
            )
          }
          disabled={readOnly}
        />
      </label>
    );
  }

  const requiredNames = new Set(opEntry.paramsSchema.required ?? []);
  const entries = Object.entries(opEntry.paramsSchema.properties);
  const requiredEntries = entries.filter(([name]) => requiredNames.has(name));
  const optionalEntries = entries.filter(([name]) => !requiredNames.has(name));

  const allFieldNames = Object.keys(opEntry.paramsSchema.properties);
  const unmatchedErrors = errors.filter(
    (e) => !allFieldNames.some((name) => fieldErrorsFor(name, [e]).length > 0),
  );

  return (
    <div className="flex flex-col gap-2 p-2">
      {requiredEntries.length > 0 && (
        <div className="flex flex-col gap-2">
          {optionalEntries.length > 0 && (
            <h4 className="text-xs font-semibold uppercase text-ink-2">
              {t("pipelineNodeInspector.requiredSection")}
            </h4>
          )}
          {requiredEntries.map(([name, prop]) => renderField(name, prop))}
        </div>
      )}
      {optionalEntries.length > 0 && (
        <div className="flex flex-col gap-2">
          {requiredEntries.length > 0 && (
            <h4 className="text-xs font-semibold uppercase text-ink-2">
              {t("pipelineNodeInspector.optionalSection")}
            </h4>
          )}
          {optionalEntries.map(([name, prop]) => renderField(name, prop))}
        </div>
      )}
      {unmatchedErrors.map((err) => (
        <p key={err} role="alert" className="text-xs text-danger">
          {err}
        </p>
      ))}
    </div>
  );
}
