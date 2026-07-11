import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource } from "../../api/types";

export type FormField = {
  name: string;
  type: CollectionSchema["fields"][number]["type"];
  label: string;
  order: number;
  hidden: boolean;
  required: boolean;
  maxLength?: number;
  values?: string[];
  min?: number;
  max?: number;
  pattern?: string;
};

function fieldsFromSchema(schema: CollectionSchema): FormField[] {
  return schema.fields.map((f, i) => ({
    name: f.name,
    type: f.type,
    label: f.name,
    order: i,
    hidden: false,
    required: f.required,
    ...(f.maxLength !== undefined ? { maxLength: f.maxLength } : {}),
    ...(f.values !== undefined ? { values: f.values } : {}),
  }));
}

const overrideInputCls = "h-8 w-full rounded border border-slate-300 px-2 text-xs";

function FieldOverrides({
  fields,
  onChange,
}: {
  fields: FormField[];
  onChange: (fields: FormField[]) => void;
}) {
  const sorted = [...fields].sort((a, b) => a.order - b.order);

  function patch(name: string, changes: Partial<FormField>) {
    onChange(fields.map((f) => (f.name === name ? { ...f, ...changes } : f)));
  }

  function reorder(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return;
    const next = [...sorted];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    onChange(next.map((f, i) => ({ ...f, order: i })));
  }

  let dragIndex: number | null = null;

  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((f, i) => (
        <li
          key={f.name}
          draggable
          onDragStart={(e) => {
            dragIndex = i;
            e.dataTransfer.setData("text/plain", String(i));
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (dragIndex !== null) reorder(dragIndex, i);
            dragIndex = null;
          }}
          className="flex cursor-move flex-col gap-1 rounded border border-slate-200 p-1.5"
        >
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-slate-400" aria-hidden="true">⠿</span>
            <input
              aria-label={`Label du champ ${f.name}`}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
            <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
              <input
                type="checkbox"
                aria-label={`Masquer ${f.name}`}
                checked={f.hidden}
                onChange={(e) => patch(f.name, { hidden: e.target.checked })}
              />
              Masqué
            </label>
            {f.type !== "unsupported" && (
              <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
                <input
                  type="checkbox"
                  aria-label={`Requis ${f.name}`}
                  checked={f.required}
                  onChange={(e) => patch(f.name, { required: e.target.checked })}
                />
                Requis
              </label>
            )}
          </div>
          {(f.type === "integer" || f.type === "number") && (
            <div className="flex gap-1">
              <input
                aria-label={`Min ${f.name}`}
                type="number"
                placeholder="min"
                className={overrideInputCls}
                value={f.min ?? ""}
                onChange={(e) => patch(f.name, { min: e.target.value === "" ? undefined : Number(e.target.value) })}
              />
              <input
                aria-label={`Max ${f.name}`}
                type="number"
                placeholder="max"
                className={overrideInputCls}
                value={f.max ?? ""}
                onChange={(e) => patch(f.name, { max: e.target.value === "" ? undefined : Number(e.target.value) })}
              />
            </div>
          )}
          {f.type === "string" && (
            <input
              aria-label={`Motif ${f.name}`}
              placeholder="motif (regex, optionnel)"
              className={overrideInputCls}
              value={f.pattern ?? ""}
              onChange={(e) => patch(f.name, { pattern: e.target.value || undefined })}
            />
          )}
        </li>
      ))}
    </ul>
  );
}

function FormPropsPanel({
  props,
  onChange,
  dataSources,
}: {
  props: Record<string, unknown>;
  onChange: (props: Record<string, unknown>) => void;
  dataSources: DataSource[];
}) {
  const client = useItemClient();
  const dataSourceId = String(props.dataSourceId ?? "");
  const fields = (props.fields as FormField[] | undefined) ?? [];
  const source = dataSources.find((s) => s.id === dataSourceId);
  const collectionId = source?.layer ?? "";
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    enabled: collectionId !== "",
  });

  return (
    <div className="flex flex-col gap-2 text-sm">
      <DataSourceSelect
        value={dataSourceId}
        dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id, fields: [], geometryType: null })}
      />
      {collectionId !== "" && schemaQuery.isLoading && (
        <p className="text-xs text-[var(--gs-color-muted)]">Chargement du schéma…</p>
      )}
      {collectionId !== "" && schemaQuery.isError && (
        <p role="alert" className="text-xs text-red-600">Schéma introuvable pour « {collectionId} ».</p>
      )}
      {collectionId !== "" && schemaQuery.data && fields.length === 0 && (
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
          onClick={() =>
            onChange({
              ...props,
              fields: fieldsFromSchema(schemaQuery.data),
              geometryType: schemaQuery.data.geometry?.type ?? null,
            })
          }
        >
          Charger les champs du schéma
        </button>
      )}
      {fields.length > 0 && (
        <FieldOverrides fields={fields} onChange={(next) => onChange({ ...props, fields: next })} />
      )}
    </div>
  );
}

function validateField(field: FormField, value: unknown): string | null {
  const empty = value === undefined || value === null || value === "";
  if (field.required && empty) return "Champ requis";
  if (empty) return null;
  if (field.type === "integer" || field.type === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return "Nombre invalide";
    if (field.min !== undefined && n < field.min) return `Doit être ≥ ${field.min}`;
    if (field.max !== undefined && n > field.max) return `Doit être ≤ ${field.max}`;
  }
  if (field.type === "string") {
    if (field.maxLength !== undefined && String(value).length > field.maxLength) {
      return `${field.maxLength} caractères maximum`;
    }
    if (field.pattern && !new RegExp(field.pattern).test(String(value))) return "Format invalide";
  }
  if (field.type === "enum" && field.values && !field.values.includes(String(value))) return "Valeur invalide";
  return null;
}

const fieldInputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

function FieldInput({
  field,
  value,
  onChange,
  onBlur,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
}) {
  if (field.type === "boolean") {
    return (
      <input type="checkbox" aria-label={field.label} checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)} onBlur={onBlur} />
    );
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <input type="number" aria-label={field.label} className={fieldInputCls}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} onBlur={onBlur} />
    );
  }
  if (field.type === "date") {
    return (
      <input type="date" aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
    );
  }
  if (field.type === "datetime") {
    return (
      <input type="datetime-local" aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
    );
  }
  if (field.type === "enum") {
    return (
      <select aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur}>
        <option value=""></option>
        {(field.values ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    );
  }
  return (
    <input type="text" aria-label={field.label} className={fieldInputCls}
      value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
  );
}

function FormComponent({ props }: { props: Record<string, unknown> }) {
  const fields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported")
    .sort((a, b) => a.order - b.order);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  function errorFor(field: FormField): string | null {
    if (!touched[field.name]) return null;
    return validateField(field, values[field.name]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const allTouched: Record<string, boolean> = {};
    fields.forEach((f) => { allTouched[f.name] = true; });
    setTouched(allTouched);
  }

  return (
    <form className="flex h-full flex-col gap-2 overflow-auto text-sm" onSubmit={handleSubmit}>
      {fields.map((f) => (
        <label key={f.name} className="flex flex-col gap-1">
          {f.label}{f.required ? " *" : ""}
          <FieldInput
            field={f}
            value={values[f.name]}
            onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
            onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
          />
          {errorFor(f) && <span role="alert" className="text-xs text-red-600">{errorFor(f)}</span>}
        </label>
      ))}
      <div className="mt-auto flex items-center gap-2">
        <button type="submit" className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white">
          {String(props.submitLabel ?? "Enregistrer")}
        </button>
      </div>
    </form>
  );
}

export function registerFormWidget(): void {
  registerWidget({
    type: "form",
    label: "Formulaire",
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
    events: ["submitted", "failed"],
    actions: ["reset"],
    PropsPanel: FormPropsPanel,
    Component: FormComponent,
  });
}
