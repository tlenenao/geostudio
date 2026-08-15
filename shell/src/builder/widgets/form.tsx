// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useInstanceInfo } from "../../api/hooks";
import { useBusAction } from "../ActionBusContext";
import { FeatureValidationError } from "../../api/itemClient";
import type { CollectionSchema, DataRecord, DataSource } from "../../api/types";
import type { WidgetContext } from "../registry";

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

function FormComponent({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const fields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported")
    .sort((a, b) => a.order - b.order);
  const allFields = ((props.fields as FormField[] | undefined) ?? []).filter((f) => f.type !== "unsupported");
  const geometryType = props.geometryType as string | null | undefined;
  const [lon, setLon] = useState<string>("");
  const [lat, setLat] = useState<string>("");
  const [loadedGeometry, setLoadedGeometry] = useState<unknown>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [genericError, setGenericError] = useState(false);
  const [editingId, setEditingId] = useState<string | number | null>(null);

  const collectionId = ctx.data?.layer ?? "";
  const permissionQuery = useQuery({
    queryKey: ["collection-permission", collectionId],
    queryFn: () => client.getCollectionPermission(collectionId),
    enabled: collectionId !== "",
  });
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  // Defaulting to `true` while the permission query is still loading
  // (`data === undefined`, `isError === false`) avoids a flash of
  // disabled UI in the common case. But a genuinely failed query (e.g.
  // StaticItemClient's zero-backend `unsupported()` rejection in a static
  // export) also leaves `data === undefined` — `?? true` alone can't tell
  // those apart and would fail open, rendering the form as writable when
  // it can never actually write (SP-18a review, I5).
  const canWrite = (permissionQuery.isError ? false : (permissionQuery.data ?? true)) && !readOnly;

  const write = useMutation({
    mutationFn: async (input: { properties: Record<string, unknown>; geometry: unknown | null }) => {
      const feature = { type: "Feature" as const, properties: input.properties, geometry: input.geometry };
      if (editingId !== null) {
        await client.updateFeature(collectionId, String(editingId), feature);
      } else {
        await client.createFeature(collectionId, feature);
      }
    },
  });

  const remove = useMutation({
    mutationFn: () => client.deleteFeature(collectionId, String(editingId)),
  });

  async function handleDelete() {
    if (editingId === null) return;
    if (!window.confirm("Supprimer cet enregistrement ?")) return;
    try {
      await remove.mutateAsync();
      queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties: {} });
      resetTo();
    } catch (err) {
      setGenericError(true);
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", { message: err instanceof Error ? err.message : "unknown" });
    }
  }

  function resetTo() {
    setValues({});
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setLon("");
    setLat("");
    setLoadedGeometry(null);
    setEditingId(null);
    write.reset();
  }
  useBusAction(ctx.bus, ctx.widgetId, "reset", resetTo);

  function handleLoadRecord(payload?: unknown) {
    const record = payload as DataRecord | undefined;
    if (!record) return;
    setEditingId(record.id);
    setValues({ ...record.properties });
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setLoadedGeometry(record.geometry ?? null);
    const geom = record.geometry as { type?: string; coordinates?: number[] } | undefined;
    if (geometryType === "Point" && geom?.type === "Point" && Array.isArray(geom.coordinates)) {
      setLon(String(geom.coordinates[0]));
      setLat(String(geom.coordinates[1]));
    } else {
      setLon("");
      setLat("");
    }
  }
  useBusAction(ctx.bus, ctx.widgetId, "loadRecord", handleLoadRecord);

  function errorFor(field: FormField): string | null {
    if (touched[field.name]) {
      const clientError = validateField(field, values[field.name]);
      if (clientError) return clientError;
    }
    return serverErrors[field.name] ?? null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const allTouched: Record<string, boolean> = {};
    fields.forEach((f) => { allTouched[f.name] = true; });
    setTouched(allTouched);
    const hasClientErrors = fields.some((f) => validateField(f, values[f.name]) !== null);
    if (hasClientErrors) return;
    setServerErrors({});
    setGenericError(false);
    const properties: Record<string, unknown> = {};
    allFields.forEach((f) => {
      if (values[f.name] !== undefined) properties[f.name] = values[f.name];
    });
    const geometry =
      geometryType === "Point"
        ? (lon !== "" && lat !== "" ? { type: "Point", coordinates: [Number(lon), Number(lat)] } : null)
        : loadedGeometry;
    try {
      await write.mutateAsync({ properties, geometry });
      queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      if (editingId === null) {
        resetTo();
      }
    } catch (err) {
      if (err instanceof FeatureValidationError) {
        const byField: Record<string, string> = {};
        err.errors.forEach((fe) => { byField[fe.field] = fe.message; });
        setServerErrors(byField);
      } else {
        setGenericError(true);
      }
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", { message: err instanceof Error ? err.message : "unknown" });
    }
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
      {geometryType === "Point" && (
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">
            Longitude
            <input type="number" step="any" aria-label="Longitude" className={fieldInputCls}
              value={lon} onChange={(e) => setLon(e.target.value)} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            Latitude
            <input type="number" step="any" aria-label="Latitude" className={fieldInputCls}
              value={lat} onChange={(e) => setLat(e.target.value)} />
          </label>
        </div>
      )}
      {editingId !== null && (
        <p className="text-xs text-[var(--gs-color-muted)]">
          Modification de l'enregistrement #{String(editingId)}
          <button type="button" className="ml-2 text-xs underline" onClick={resetTo}>Annuler</button>
          {canWrite && (
            <button
              type="button"
              className="ml-2 text-xs text-red-600 underline"
              disabled={remove.isPending}
              onClick={handleDelete}
            >
              Supprimer
            </button>
          )}
        </p>
      )}
      <div className="mt-auto flex items-center gap-2">
        {canWrite && (
          <button
            type="submit"
            disabled={write.isPending}
            className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {String(props.submitLabel ?? "Enregistrer")}
          </button>
        )}
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm" onClick={resetTo}>
          Réinitialiser
        </button>
      </div>
      {genericError && (
        <p role="alert" className="text-xs text-red-600">Échec de l'enregistrement.</p>
      )}
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
    actions: ["reset", "loadRecord"],
    PropsPanel: FormPropsPanel,
    Component: FormComponent,
  });
}
