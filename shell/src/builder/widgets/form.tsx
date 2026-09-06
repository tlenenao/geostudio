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
import { t } from "../../i18n";

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
            <span className="text-[10px] text-slate-400" aria-hidden="true">
              ⠿
            </span>
            <input
              aria-label={t("widgetForm.fieldLabelAria", { name: f.name })}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
            <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
              <input
                type="checkbox"
                aria-label={t("widgetForm.hideFieldAria", { name: f.name })}
                checked={f.hidden}
                onChange={(e) => patch(f.name, { hidden: e.target.checked })}
              />
              {t("widgetForm.hiddenToggle")}
            </label>
            {f.type !== "unsupported" && f.type !== "attachment" && (
              <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
                <input
                  type="checkbox"
                  aria-label={t("widgetForm.requireFieldAria", { name: f.name })}
                  checked={f.required}
                  onChange={(e) => patch(f.name, { required: e.target.checked })}
                />
                {t("widgetForm.requiredToggle")}
              </label>
            )}
          </div>
          {(f.type === "integer" || f.type === "number") && (
            <div className="flex gap-1">
              <input
                aria-label={t("widgetForm.minFieldAria", { name: f.name })}
                type="number"
                placeholder={t("widgetForm.minPlaceholder")}
                className={overrideInputCls}
                value={f.min ?? ""}
                onChange={(e) =>
                  patch(f.name, { min: e.target.value === "" ? undefined : Number(e.target.value) })
                }
              />
              <input
                aria-label={t("widgetForm.maxFieldAria", { name: f.name })}
                type="number"
                placeholder={t("widgetForm.maxPlaceholder")}
                className={overrideInputCls}
                value={f.max ?? ""}
                onChange={(e) =>
                  patch(f.name, { max: e.target.value === "" ? undefined : Number(e.target.value) })
                }
              />
            </div>
          )}
          {f.type === "string" && (
            <input
              aria-label={t("widgetForm.patternFieldAria", { name: f.name })}
              placeholder={t("widgetForm.patternPlaceholder")}
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
        <p className="text-xs text-[var(--gs-color-muted)]">{t("widgetForm.loadingSchema")}</p>
      )}
      {collectionId !== "" && schemaQuery.isError && (
        <p role="alert" className="text-xs text-red-600">
          {t("widgetForm.schemaNotFound", { collectionId })}
        </p>
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
          {t("widgetForm.loadSchemaButton")}
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
  // Un champ attachment ne passe jamais par values/onChange
  // (AttachmentFieldInput gère son propre état via useQuery, cf. Task 11) —
  // required ne peut donc jamais être satisfait pour ce type, y compris pour
  // une config déjà enregistrée avant que l'éditeur n'exclue ce type de la
  // case « Requis » (revue finale de branche, I4). Le bloquer rendrait le
  // formulaire définitivement non soumettable.
  if (field.required && empty && field.type !== "attachment") return t("widgetForm.requiredError");
  if (empty) return null;
  if (field.type === "integer" || field.type === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return t("widgetForm.invalidNumber");
    if (field.min !== undefined && n < field.min)
      return t("widgetForm.minError", { min: field.min });
    if (field.max !== undefined && n > field.max)
      return t("widgetForm.maxError", { max: field.max });
  }
  if (field.type === "string") {
    if (field.maxLength !== undefined && String(value).length > field.maxLength) {
      return t("widgetForm.maxLengthError", { maxLength: field.maxLength });
    }
    if (field.pattern && !new RegExp(field.pattern).test(String(value)))
      return t("widgetForm.invalidFormat");
  }
  if (field.type === "enum" && field.values && !field.values.includes(String(value)))
    return t("widgetForm.invalidValue");
  return null;
}

const fieldInputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

function AttachmentFieldInput({
  collectionId,
  fid,
  fieldKey,
  client,
}: {
  collectionId: string;
  fid: string | null;
  fieldKey: string;
  client: ReturnType<typeof useItemClient>;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["attachments", collectionId, fid, fieldKey],
    queryFn: () => client.listAttachments(collectionId, fid!, fieldKey),
    enabled: fid !== null,
  });
  const [uploading, setUploading] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || fid === null) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const { uploadUrl, key } = await client.presignAttachmentUpload(collectionId, fid, {
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
        await fetch(uploadUrl, {
          method: "PUT",
          body: file,
          headers: { "Content-Type": file.type },
        });
        await client.confirmAttachmentUpload(collectionId, fid, {
          key,
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
      }
      void queryClient.invalidateQueries({
        queryKey: ["attachments", collectionId, fid, fieldKey],
      });
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(attachmentId: string) {
    if (fid === null) return;
    await client.deleteAttachment(collectionId, fid, attachmentId);
    void queryClient.invalidateQueries({ queryKey: ["attachments", collectionId, fid, fieldKey] });
  }

  async function handleDownload(attachmentId: string) {
    if (fid === null) return;
    const { blob, filename } = await client.downloadAttachment(collectionId, fid, attachmentId);
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = filename;
    el.click();
    URL.revokeObjectURL(url);
  }

  if (fid === null) {
    return <p className="text-xs text-ink-3">{t("widgetForm.attachmentsSaveFirst")}</p>;
  }

  return (
    <div className="flex flex-col gap-1">
      <ul className="flex flex-col gap-1">
        {(query.data ?? []).map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-xs">
            <button
              type="button"
              aria-label={a.filename}
              onClick={() => void handleDownload(a.id)}
              className="flex-1 truncate bg-transparent p-0 text-left underline"
            >
              {a.filename}
            </button>
            <button
              type="button"
              aria-label={t("widgetForm.deleteAttachmentAria", { filename: a.filename })}
              className="text-danger underline"
              onClick={() => void handleDelete(a.id)}
            >
              {t("widgetForm.delete")}
            </button>
          </li>
        ))}
      </ul>
      <input
        type="file"
        multiple
        aria-label={t("widgetForm.addFilesAria")}
        disabled={uploading}
        onChange={(e) => void handleFiles(e.target.files)}
      />
    </div>
  );
}

function FieldInput({
  field,
  value,
  onChange,
  onBlur,
  collectionId,
  fid,
  client,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
  collectionId: string;
  fid: string | null;
  client: ReturnType<typeof useItemClient>;
}) {
  if (field.type === "attachment") {
    return (
      <AttachmentFieldInput
        collectionId={collectionId}
        fid={fid}
        fieldKey={field.name}
        client={client}
      />
    );
  }
  if (field.type === "boolean") {
    return (
      <input
        type="checkbox"
        aria-label={field.label}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        onBlur={onBlur}
      />
    );
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <input
        type="number"
        aria-label={field.label}
        className={fieldInputCls}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        onBlur={onBlur}
      />
    );
  }
  if (field.type === "date") {
    return (
      <input
        type="date"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      />
    );
  }
  if (field.type === "datetime") {
    return (
      <input
        type="datetime-local"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      />
    );
  }
  if (field.type === "enum") {
    return (
      <select
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      >
        <option value=""></option>
        {(field.values ?? []).map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      aria-label={field.label}
      className={fieldInputCls}
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}

function FormComponent({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const fields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported")
    .sort((a, b) => a.order - b.order);
  const allFields = ((props.fields as FormField[] | undefined) ?? []).filter(
    (f) => f.type !== "unsupported",
  );
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
    mutationFn: async (input: {
      properties: Record<string, unknown>;
      geometry: unknown | null;
    }) => {
      const feature = {
        type: "Feature" as const,
        properties: input.properties,
        geometry: input.geometry,
      };
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
    if (!window.confirm(t("widgetForm.confirmDelete"))) return;
    try {
      await remove.mutateAsync();
      void queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties: {} });
      resetTo();
    } catch (err) {
      setGenericError(true);
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", {
        message: err instanceof Error ? err.message : "unknown",
      });
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
    fields.forEach((f) => {
      allTouched[f.name] = true;
    });
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
        ? lon !== "" && lat !== ""
          ? { type: "Point", coordinates: [Number(lon), Number(lat)] }
          : null
        : loadedGeometry;
    try {
      await write.mutateAsync({ properties, geometry });
      void queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      if (editingId === null) {
        resetTo();
      }
    } catch (err) {
      if (err instanceof FeatureValidationError) {
        const byField: Record<string, string> = {};
        err.errors.forEach((fe) => {
          byField[fe.field] = fe.message;
        });
        setServerErrors(byField);
      } else {
        setGenericError(true);
      }
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", {
        message: err instanceof Error ? err.message : "unknown",
      });
    }
  }

  return (
    <form
      className="flex h-full flex-col gap-2 overflow-auto text-sm"
      onSubmit={(e) => void handleSubmit(e)}
    >
      {fields.map((f) => (
        <label key={f.name} className="flex flex-col gap-1">
          {f.label}
          {f.required ? " *" : ""}
          <FieldInput
            field={f}
            value={values[f.name]}
            onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
            onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
            collectionId={collectionId}
            fid={editingId === null ? null : String(editingId)}
            client={client}
          />
          {errorFor(f) && (
            <span role="alert" className="text-xs text-red-600">
              {errorFor(f)}
            </span>
          )}
        </label>
      ))}
      {geometryType === "Point" && (
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">
            {t("widgetForm.longitude")}
            <input
              type="number"
              step="any"
              aria-label={t("widgetForm.longitude")}
              className={fieldInputCls}
              value={lon}
              onChange={(e) => setLon(e.target.value)}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            {t("widgetForm.latitude")}
            <input
              type="number"
              step="any"
              aria-label={t("widgetForm.latitude")}
              className={fieldInputCls}
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </label>
        </div>
      )}
      {editingId !== null && (
        <p className="text-xs text-[var(--gs-color-muted)]">
          {t("widgetForm.editingRecord", { id: String(editingId) })}
          <button type="button" className="ml-2 text-xs underline" onClick={resetTo}>
            {t("widgetForm.cancel")}
          </button>
          {canWrite && (
            <button
              type="button"
              className="ml-2 text-xs text-red-600 underline"
              disabled={remove.isPending}
              onClick={() => void handleDelete()}
            >
              {t("widgetForm.delete")}
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
            {String(props.submitLabel ?? t("widgetForm.submitDefault"))}
          </button>
        )}
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          onClick={resetTo}
        >
          {t("widgetForm.reset")}
        </button>
      </div>
      {genericError && (
        <p role="alert" className="text-xs text-red-600">
          {t("widgetForm.saveFailed")}
        </p>
      )}
    </form>
  );
}

export function registerFormWidget(): void {
  registerWidget({
    type: "form",
    label: t("widgetForm.paletteLabel"),
    defaultProps: {
      dataSourceId: "",
      fields: [],
      submitLabel: t("widgetForm.submitDefault"),
      geometryType: null,
    },
    defaultSize: { w: 4, h: 6 },
    // `fields` est array-shaped (hors de portée) ; `geometryType` est un
    // enum nullable qui ne rentre pas dans les 4 types de
    // WidgetPropDescriptor — laissé de côté plutôt que forcé.
    configSchema: [
      {
        name: "dataSourceId",
        type: "dataSource",
        label: t("widgetForm.dataSourceConfig"),
        default: "",
      },
      {
        name: "submitLabel",
        type: "string",
        label: t("widgetForm.submitLabelConfig"),
        default: t("widgetForm.submitDefault"),
      },
    ],
    events: ["submitted", "failed"],
    actions: ["reset", "loadRecord"],
    PropsPanel: FormPropsPanel,
    Component: FormComponent,
  });
}
