// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import { useInstanceInfo } from "../../api/hooks";
import { useBusAction } from "../ActionBusContext";
import { FeatureValidationError } from "../../api/itemClient";
import { ApiError } from "../../api/ApiError";
import type {
  AttachmentKind,
  CollectionSchema,
  DataRecord,
  DataSource,
  FieldDomain,
} from "../../api/types";
import type { WidgetContext } from "../registry";
import { plural, t } from "../../i18n";
import { Button } from "../../ui/kit/Button";
import { ConfirmDialog } from "../../ui/kit/ConfirmDialog";
import { FeatureHistoryPanel } from "./FeatureHistoryPanel";
import { ACCURACY_WARN_M, GeometryInput, lineKind, type GeometryIssue } from "./GeometryInput";
import { RelatedRecordsPanel } from "./RelatedRecordsPanel";
import { LoadingState } from "../../ui/kit/LoadingState";
import { evaluateExpression, type ExprContext } from "../expr";
import { formatDateTime } from "../../lib/format";
import "../../i18n/domains/widgets";

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
  // ARC-27 (XLSForm) : aide sous le libellé et condition CEL de pertinence (`relevant`),
  // évaluée sur les valeurs saisies ; un champ non pertinent est masqué, non validé, non envoyé.
  hint?: string;
  visibleWhen?: string;
  // ARC-13 : choix imposés par un domaine `list` ou par les sous-types (calculé à l'affichage
  // depuis le schéma courant, jamais persisté dans la config du widget).
  options?: { value: string | number; label: string }[];
  // L8 (XLSForm `select_multiple`) : plusieurs valeurs parmi `options`, stockées en tableau.
  multiple?: boolean;
  // L8 : nature d'un champ média (reprise du schéma courant si absente de la config).
  kind?: AttachmentKind;
};

// L8 : `accept`/`capture` du sélecteur de fichier selon la nature du média. `capture` ouvre
// directement la caméra/le micro sur mobile ; un fichier générique n'en impose aucun.
export function mediaAttrs(kind: AttachmentKind | undefined): {
  accept?: string;
  capture?: "environment" | "user";
} {
  switch (kind) {
    case "image":
      return { accept: "image/*", capture: "environment" };
    case "video":
      return { accept: "video/*", capture: "environment" };
    case "audio":
      return { accept: "audio/*", capture: "user" };
    default:
      return {};
  }
}

// ARC-13 : champs enrichis des domaines/sous-types du schéma courant ; le domaine du sous-type
// sélectionné l'emporte sur celui du champ. Une plage devient min/max (validés par validateField).
export function applyDomains(
  fields: FormField[],
  schema: CollectionSchema | undefined,
  values: Record<string, unknown>,
): FormField[] {
  if (!schema) return fields;
  const domains = new Map<string, FieldDomain>();
  for (const f of schema.fields) if (f.domain) domains.set(f.name, f.domain);
  const sub = schema.subtypes;
  const current = sub?.items.find((i) => String(i.value) === String(values[sub.field]));
  return fields.map((f) => {
    if (sub && f.name === sub.field) {
      return { ...f, options: sub.items.map((i) => ({ value: i.value, label: i.label })) };
    }
    const dom = current?.domains?.[f.name] ?? domains.get(f.name);
    if (!dom) return f;
    if (dom.type === "list") {
      return {
        ...f,
        options: dom.values.map((v) => ({ value: v, label: dom.labels?.[String(v)] ?? String(v) })),
      };
    }
    return {
      ...f,
      ...(dom.min !== undefined ? { min: dom.min } : {}),
      ...(dom.max !== undefined ? { max: dom.max } : {}),
    };
  });
}

function schemaKind(
  schema: CollectionSchema | undefined,
  name: string,
): AttachmentKind | undefined {
  return schema?.fields.find((x) => x.name === name)?.kind;
}

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
    ...(f.kind ? { kind: f.kind } : {}),
  }));
}

const overrideInputCls = "h-9 w-full rounded border border-rule px-2 text-xs";

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

  // Une ref : une variable locale serait perdue à chaque re-rendu pendant le glisser (REV-365 g).
  const dragIndex = useRef<number | null>(null);

  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((f, i) => (
        <li
          key={f.name}
          draggable
          onDragStart={(e) => {
            dragIndex.current = i;
            e.dataTransfer.setData("text/plain", String(i));
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (dragIndex.current !== null) reorder(dragIndex.current, i);
            dragIndex.current = null;
          }}
          className="flex cursor-move flex-col gap-1 rounded border border-rule p-1.5"
        >
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs text-ink-2" aria-hidden="true">
              ⠿
            </span>
            <button
              type="button"
              className="rounded border border-rule px-1 text-xs disabled:opacity-50"
              aria-label={t("widgetForm.moveFieldUpAria", { name: f.name })}
              disabled={i === 0}
              onClick={() => reorder(i, i - 1)}
            >
              ↑
            </button>
            <button
              type="button"
              className="rounded border border-rule px-1 text-xs disabled:opacity-50"
              aria-label={t("widgetForm.moveFieldDownAria", { name: f.name })}
              disabled={i === sorted.length - 1}
              onClick={() => reorder(i, i + 1)}
            >
              ↓
            </button>
            <input
              aria-label={t("widgetForm.fieldLabelAria", { name: f.name })}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
            <label className="flex items-center gap-1 whitespace-nowrap text-xs">
              {/* eslint-disable-next-line geostudio/label-no-aria-label -- le nom accessible contient le texte visible et ajoute le contexte dynamique (champ/ligne) */}
              <input
                type="checkbox"
                aria-label={t("widgetForm.hideFieldAria", { name: f.name })}
                checked={f.hidden}
                onChange={(e) => patch(f.name, { hidden: e.target.checked })}
              />
              {t("widgetForm.hiddenToggle")}
            </label>
            {f.type !== "unsupported" && f.type !== "attachment" && f.type !== "list" && (
              <label className="flex items-center gap-1 whitespace-nowrap text-xs">
                {/* eslint-disable-next-line geostudio/label-no-aria-label -- le nom accessible contient le texte visible et ajoute le contexte dynamique (champ/ligne) */}
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
        <LoadingState label={t("widgetForm.loadingSchema")} />
      )}
      {collectionId !== "" && schemaQuery.isError && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.schemaNotFound", { collectionId })}
        </p>
      )}
      {collectionId !== "" && schemaQuery.data && fields.length === 0 && (
        <button
          type="button"
          className="rounded border border-rule px-2 py-1 text-xs hover:bg-sunken"
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

// ARC-27 : un champ sans `visibleWhen` est toujours pertinent ; sinon la condition CEL est évaluée
// avec chaque champ du formulaire lié à sa valeur (null si non renseigné). Un résultat qui n'est
// pas exactement `true` (faux, erreur d'opérande nul…) masque le champ, comme `relevant`.
export function isFieldVisible(
  field: FormField,
  values: Record<string, unknown>,
  allNames: string[],
): boolean {
  if (!field.visibleWhen) return true;
  const bindings: Record<string, unknown> = {};
  for (const n of allNames) bindings[n] = values[n] === undefined ? null : values[n];
  return evaluateExpression(field.visibleWhen, bindings as unknown as ExprContext) === true;
}

type Client = ReturnType<typeof useItemClient>;

async function uploadAttachment(
  client: Client,
  collectionId: string,
  fid: string,
  fieldKey: string,
  file: File,
) {
  const contentType = file.type || "application/octet-stream";
  const { uploadUrl, key } = await client.presignAttachmentUpload(collectionId, fid, {
    fieldKey,
    filename: file.name,
    contentType,
    size: file.size,
  });
  const res = await fetch(uploadUrl, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": contentType },
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  await client.confirmAttachmentUpload(collectionId, fid, {
    key,
    fieldKey,
    filename: file.name,
    contentType,
  });
}

function validateField(field: FormField, value: unknown): string | null {
  const empty =
    value === undefined ||
    value === null ||
    value === "" ||
    (Array.isArray(value) && !value.length);
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

const fieldInputCls = "h-9 rounded-md border border-rule px-2 text-sm";

function AttachmentFieldInput({
  collectionId,
  fid,
  fieldKey,
  client,
  labelledBy,
  queued,
  onQueue,
  kind,
}: {
  kind?: AttachmentKind;
  collectionId: string;
  fid: string | null;
  fieldKey: string;
  client: ReturnType<typeof useItemClient>;
  labelledBy: string;
  // ARC-27 (mode mobile) : sur une nouvelle saisie, le fichier est gardé puis envoyé après
  // l'enregistrement, au lieu d'exiger d'enregistrer d'abord.
  queued?: File | null;
  onQueue?: (file: File | null) => void;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["attachments", collectionId, fid, fieldKey],
    queryFn: () => client.listAttachments(collectionId, fid!, fieldKey),
    enabled: fid !== null,
  });
  const [fileStatus, setFileStatus] = useState<Record<string, "uploading" | "done" | "error">>({});
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || fid === null) return;
    for (const file of Array.from(files)) {
      setFileStatus((s) => ({ ...s, [file.name]: "uploading" }));
      try {
        await uploadAttachment(client, collectionId, fid, fieldKey, file);
        setFileStatus((s) => ({ ...s, [file.name]: "done" }));
      } catch (err) {
        console.error("AttachmentFieldInput: upload failed", err);
        setFileStatus((s) => ({ ...s, [file.name]: "error" }));
      }
    }
    void queryClient.invalidateQueries({
      queryKey: ["attachments", collectionId, fid, fieldKey],
    });
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

  // Photo en file d'attente (aussi après un envoi échoué, saisie déjà créée) : on garde le champ.
  if (onQueue && (fid === null || queued)) {
    return (
      <div className="flex flex-col gap-1">
        <input
          type="file"
          {...mediaAttrs(kind ?? "image")}
          aria-labelledby={labelledBy}
          onChange={(e) => onQueue(e.target.files?.[0] ?? null)}
        />
        {queued && (
          <p className="text-xs text-ink-2">
            {t("widgetForm.photoReady", { filename: queued.name })}
          </p>
        )}
      </div>
    );
  }
  if (fid === null) {
    return <p className="text-xs text-ink-3">{t("widgetForm.attachmentsSaveFirst")}</p>;
  }

  return (
    <div className="flex flex-col gap-1">
      <ul className="flex flex-col gap-1" aria-labelledby={labelledBy}>
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
              onClick={() => setPendingDeleteId(a.id)}
            >
              {t("widgetForm.delete")}
            </button>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t("widgetForm.confirmDeleteAttachmentTitle")}
        message={t("widgetForm.confirmDeleteAttachment", {
          filename: (query.data ?? []).find((a) => a.id === pendingDeleteId)?.filename ?? "",
        })}
        confirmLabel={t("widgetForm.delete")}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => {
          const id = pendingDeleteId;
          setPendingDeleteId(null);
          if (id !== null) void handleDelete(id);
        }}
      />
      <input
        type="file"
        multiple
        {...(kind ? { accept: mediaAttrs(kind).accept } : {})}
        aria-label={t("widgetForm.addFilesAria")}
        disabled={Object.values(fileStatus).some((s) => s === "uploading")}
        onChange={(e) => void handleFiles(e.target.files)}
      />
      {Object.entries(fileStatus)
        .filter(([, status]) => status !== "done")
        .map(([filename, status]) => (
          <p key={filename} className="text-xs text-ink-2">
            {status === "uploading"
              ? t("widgetForm.attachmentUploading", { filename })
              : t("widgetForm.attachmentError", { filename })}
          </p>
        ))}
    </div>
  );
}

// L8 : `select_multiple` — cases à cocher dans un groupe nommé par le libellé du champ.
function MultiChoiceInput({
  field,
  value,
  onChange,
  onBlur,
  error,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
  error: string | null;
}) {
  const picked = Array.isArray(value) ? (value as (string | number)[]) : [];
  return (
    <div
      id={`field-${field.name}`}
      role="group"
      aria-labelledby={`field-${field.name}-label`}
      {...(error ? { "aria-invalid": "true" as const } : {})}
      {...(field.required ? { "aria-required": "true" as const } : {})}
      tabIndex={-1}
      className="flex flex-col gap-1"
    >
      {(field.options ?? []).map((o) => (
        <label key={String(o.value)} className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={picked.some((p) => String(p) === String(o.value))}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...picked, o.value]
                  : picked.filter((p) => String(p) !== String(o.value)),
              )
            }
            onBlur={onBlur}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function FieldInput({
  field,
  value,
  onChange,
  onBlur,
  error,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
  error: string | null;
}) {
  const fieldId = `field-${field.name}`;
  const errorId = `field-${field.name}-error`;
  const errorProps = error ? { "aria-invalid": "true" as const, "aria-describedby": errorId } : {};
  // D32 : `aria-required` seul (jamais l'attribut natif `required`) —
  // annonce le caractère requis aux lecteurs d'écran sans réactiver la
  // validation navigateur native, qui court-circuiterait le flux
  // touched/validateField existant et, pour la branche boolean,
  // forcerait `checked=true` alors que `false` explicite est une valeur
  // valide (validateField, ligne 221).
  const requiredProps = field.required ? { "aria-required": "true" as const } : {};

  // La branche `attachment` est traitée à part par l'appelant (form.tsx,
  // fields.map) : AttachmentFieldInput y est rendu directement, avec son
  // propre <span id> de label relié par aria-labelledby (D38) — FieldInput
  // n'est donc jamais appelé pour ce type.
  if (field.options && field.type !== "boolean" && field.type !== "attachment") {
    const options = field.options;
    return (
      <select
        id={fieldId}
        aria-label={field.label}
        className={fieldInputCls}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) =>
          onChange(options.find((o) => String(o.value) === e.target.value)?.value ?? undefined)
        }
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      >
        <option value=""></option>
        {options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }
  if (field.type === "boolean") {
    return (
      <input
        id={fieldId}
        type="checkbox"
        aria-label={field.label}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <input
        id={fieldId}
        type="number"
        aria-label={field.label}
        className={fieldInputCls}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "date") {
    return (
      <input
        id={fieldId}
        type="date"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "datetime") {
    return (
      <input
        id={fieldId}
        type="datetime-local"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "enum") {
    return (
      <select
        id={fieldId}
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
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
      id={fieldId}
      type="text"
      aria-label={field.label}
      className={fieldInputCls}
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      {...errorProps}
      {...requiredProps}
    />
  );
}

// ARC-27 : « mes saisies » — enregistrements créés par l'appelant, plus récents d'abord.
function MyEntries({ client, collectionId }: { client: Client; collectionId: string }) {
  const query = useQuery({
    queryKey: ["my-entries", collectionId],
    queryFn: () => (client.listMyEntries ? client.listMyEntries(collectionId, 20) : []),
    retry: false,
  });
  const entries = query.data ?? [];
  return (
    <section aria-label={t("widgetForm.myEntries")} className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">{t("widgetForm.myEntries")}</h3>
      {query.isError && <p className="text-xs text-danger">{t("widgetForm.myEntriesError")}</p>}
      {!query.isError && entries.length === 0 && (
        <p className="text-xs text-ink-2">{t("widgetForm.myEntriesEmpty")}</p>
      )}
      <ul className="flex flex-col gap-1">
        {entries.map((e) => {
          const first = Object.values(e.properties).find((v) => typeof v === "string" && v !== "");
          return (
            <li key={e.fid} className="flex justify-between gap-2 text-xs">
              <span className="truncate">{String(first ?? `#${e.fid}`)}</span>
              <time dateTime={e.at} className="text-ink-2">
                {formatDateTime(e.at)}
              </time>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function FormComponent({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const baseFields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported" && f.type !== "list")
    .sort((a, b) => a.order - b.order);
  // Les colonnes `list` (non éditables ici) sont renvoyées telles que chargées :
  // le PUT remplace tout, les omettre les mettrait à NULL (c01-004).
  const allFields = ((props.fields as FormField[] | undefined) ?? []).filter(
    (f) => f.type !== "unsupported",
  );
  const geometryType = props.geometryType as string | null | undefined;
  // ARC-27 : mode collecte mobile (GPS, photo à l'enregistrement, « mes saisies »).
  const mobile = props.mobile === true;
  const showMyEntries = props.showMyEntries === true;
  const [pendingFiles, setPendingFiles] = useState<Record<string, File | null>>({});
  const [geoError, setGeoError] = useState(false);
  function locate() {
    setGeoError(false);
    if (!navigator.geolocation) return setGeoError(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLon(String(pos.coords.longitude));
        setLat(String(pos.coords.latitude));
        setAccuracy(typeof pos.coords.accuracy === "number" ? pos.coords.accuracy : null);
      },
      () => setGeoError(true),
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }
  const [accuracy, setAccuracy] = useState<number | null>(null);
  // L8 : géométrie ligne/polygone (GeometryInput) ; `geomKey` remonte le composant quand la
  // géométrie est remplacée de l'extérieur (reset, chargement d'un enregistrement).
  const [geomIssue, setGeomIssue] = useState<GeometryIssue>(null);
  const [geomKey, setGeomKey] = useState(0);
  const [geometryError, setGeometryError] = useState<string | null>(null);
  const [lon, setLon] = useState<string>("");
  const [lat, setLat] = useState<string>("");
  const [loadedGeometry, setLoadedGeometry] = useState<unknown>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [genericError, setGenericError] = useState(false);
  const [attachmentFailed, setAttachmentFailed] = useState(false);
  // ARC-04 : ETag de l'enregistrement en cours d'édition (If-Match) ; conflit = 412.
  const [etag, setEtag] = useState<string | null>(null);
  // REV-367 d : lecture de l'ETag en cours (pas de soumission sans If-Match) et champs
  // saisis par l'utilisateur (la lecture tardive ne les écrase pas).
  const [etagLoading, setEtagLoading] = useState(false);
  const editedRef = useRef<Set<string>>(new Set());
  const [conflict, setConflict] = useState(false);
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // Résumé d'erreurs figé à la soumission (REV-223) : ne se recalcule pas à chaque frappe,
  // sinon le role=alert serait réannoncé en continu. null = aucune soumission en cours.
  // Les messages par champ restent rendus mais sans role=alert tant que le résumé est affiché
  // (REV-323 : plus de double annonce) ; relus au focus via aria-describedby.
  const [summaryNames, setSummaryNames] = useState<string[] | null>(null);

  const collectionId = ctx.data?.layer ?? "";
  // ARC-13 : domaines et sous-types lus au schéma courant (ils peuvent changer après la
  // configuration du widget) ; sans schéma, le formulaire reste celui de la config.
  const schemaQuery = useQuery({
    queryKey: ["collection-schema-domains", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    enabled: collectionId !== "",
    staleTime: 60_000,
    retry: false,
  });
  const withDomains = applyDomains(baseFields, schemaQuery.data, values);
  const everyName = withDomains.map((f) => f.name);
  // ARC-27 : seuls les champs pertinents (`visibleWhen`) sont affichés, validés et envoyés.
  const fields = withDomains.filter((f) => isFieldVisible(f, values, everyName));
  const irrelevant = new Set(withDomains.filter((f) => !fields.includes(f)).map((f) => f.name));
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
      let fid: string | number;
      if (editingId !== null) {
        const args = [collectionId, String(editingId), feature] as const;
        if (etag) await client.updateFeature(...args, { ifMatch: etag });
        else await client.updateFeature(...args);
        fid = editingId;
      } else {
        fid = (await client.createFeature(collectionId, feature)).id;
      }
      // Photos mises en file : envoyées une fois la saisie identifiée (création ou reprise après
      // échec). Un échec ne fait pas échouer la saisie déjà enregistrée ; il est remonté
      // pour que le formulaire reste ouvert sur cette saisie avec les fichiers à renvoyer.
      const failed: Record<string, File> = {};
      for (const [key, file] of Object.entries(pendingFiles)) {
        if (!file) continue;
        try {
          await uploadAttachment(client, collectionId, String(fid), key, file);
        } catch {
          failed[key] = file;
        }
      }
      return { fid, failed };
    },
  });

  const remove = useMutation({
    mutationFn: () =>
      etag
        ? client.deleteFeature(collectionId, String(editingId), { ifMatch: etag })
        : client.deleteFeature(collectionId, String(editingId)),
  });

  async function handleDelete() {
    if (editingId === null) return;
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

  // Lit l'état serveur de l'enregistrement : ETag + valeurs à jour (client sans
  // `getFeature` ou lecture en échec : on garde ce qui est affiché, sans If-Match).
  async function syncFromServer(fid: string | number, applyValues: boolean) {
    if (!client.getFeature) return;
    setEtagLoading(true);
    try {
      const f = await client.getFeature(collectionId, String(fid));
      setEtag(f.etag);
      if (applyValues) {
        // Les champs déjà saisis par l'utilisateur priment sur la lecture serveur.
        const edited = editedRef.current;
        setValues((old) => {
          const next = { ...f.properties };
          for (const name of edited) if (name in old) next[name] = old[name];
          return next;
        });
        if (!edited.has("__geom")) {
          setLoadedGeometry(f.geometry ?? null);
          setGeomKey((k) => k + 1);
          const g = f.geometry as { type?: string; coordinates?: number[] } | null;
          if (geometryType === "Point" && g?.type === "Point" && Array.isArray(g.coordinates)) {
            setLon(String(g.coordinates[0]));
            setLat(String(g.coordinates[1]));
          }
        }
      }
    } catch {
      setEtag(null);
    } finally {
      setEtagLoading(false);
    }
  }

  function resetTo() {
    editedRef.current = new Set();
    setEtag(null);
    setConflict(false);
    setValues({});
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setAttachmentFailed(false);
    setLon("");
    setLat("");
    setLoadedGeometry(null);
    setGeomKey((k) => k + 1);
    setGeomIssue(null);
    setGeometryError(null);
    setAccuracy(null);
    setEditingId(null);
    setSummaryNames(null);
    setPendingFiles({});
    setGeoError(false);
    write.reset();
  }
  useBusAction(ctx.bus, ctx.widgetId, "reset", resetTo);

  function handleLoadRecord(payload?: unknown) {
    const record = payload as DataRecord | undefined;
    if (!record) return;
    setEditingId(record.id);
    setConflict(false);
    editedRef.current = new Set();
    setEtag(null);
    void syncFromServer(record.id, true);
    setValues({ ...record.properties });
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setSummaryNames(null);
    setLoadedGeometry(record.geometry ?? null);
    setGeomKey((k) => k + 1);
    setGeomIssue(null);
    setGeometryError(null);
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
    // REV-367 d : jamais d'écriture sans If-Match tant que l'ETag est en cours de lecture.
    if (etagLoading) return;
    const allTouched: Record<string, boolean> = {};
    fields.forEach((f) => {
      allTouched[f.name] = true;
    });
    setTouched(allTouched);
    const invalidNow = fields.filter((f) => validateField(f, values[f.name]) !== null);
    setSummaryNames(invalidNow.map((f) => f.name));
    const firstInvalid = invalidNow[0];
    // L8 : géométrie requise (schéma courant) ou incomplète (ligne < 2 points, polygone < 3).
    const pointGeometry =
      geometryType === "Point" && lon !== "" && lat !== ""
        ? { type: "Point", coordinates: [Number(lon), Number(lat)] }
        : null;
    const geometryNow = geometryType === "Point" ? pointGeometry : loadedGeometry;
    const geometryMissing =
      !!geometryType && schemaQuery.data?.geometry?.required === true && geometryNow === null;
    setGeometryError(geometryMissing ? t("widgetForm.geometryRequired") : null);
    if (firstInvalid) {
      // REV-223 : focus sur le premier champ invalide (les contrôles portent id=field-<name>).
      document.getElementById(`field-${firstInvalid.name}`)?.focus();
      return;
    }
    if (geomIssue !== null || geometryMissing) return;
    setServerErrors({});
    setGenericError(false);
    setAttachmentFailed(false);
    const properties: Record<string, unknown> = {};
    allFields.forEach((f) => {
      if (values[f.name] !== undefined && !irrelevant.has(f.name))
        properties[f.name] = values[f.name];
    });
    // L8 : précision du fix GPS, seulement si la collection déclare la colonne `gps_accuracy`.
    if (accuracy !== null && allFields.some((f) => f.name === "gps_accuracy"))
      properties.gps_accuracy = Math.round(accuracy);
    const geometry = geometryNow;
    try {
      const { fid, failed } = await write.mutateAsync({ properties, geometry });
      void queryClient.invalidateQueries({ queryKey: ["datasource"] });
      void queryClient.invalidateQueries({ queryKey: ["my-entries", collectionId] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      if (Object.keys(failed).length > 0) {
        // Ne jamais vider le formulaire : saisie créée, photos à renvoyer par un nouvel envoi.
        setEditingId(fid);
        setPendingFiles(failed);
        setAttachmentFailed(true);
        return;
      }
      if (editingId === null) {
        resetTo();
      } else {
        // Reprise après échec d'envoi : photos parties, on vide la file (sinon doublon).
        setPendingFiles({});
        void syncFromServer(editingId, false);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 412 && editingId !== null) {
        // ARC-04 : modifié ailleurs depuis la lecture — message + rechargement des valeurs.
        setConflict(true);
        editedRef.current = new Set();
        void syncFromServer(editingId, true);
        void queryClient.invalidateQueries({ queryKey: ["datasource"] });
      } else if (err instanceof FeatureValidationError) {
        const byField: Record<string, string> = {};
        err.errors.forEach((fe) => {
          byField[fe.field] = fe.message;
        });
        setServerErrors(byField);
        const serverInvalid = fields.filter((f) => f.name in byField);
        setSummaryNames(serverInvalid.map((f) => f.name));
        // REV-323 : le focus suit aussi l'erreur serveur (comme l'erreur client plus haut).
        if (serverInvalid[0]) document.getElementById(`field-${serverInvalid[0].name}`)?.focus();
        // P10.02 : une erreur sur un champ absent du formulaire (tenant_id,
        // champ masqué, géométrie…) n'a aucun emplacement visible : message générique.
        const shown = new Set(fields.map((f) => f.name));
        if (err.errors.some((fe) => !shown.has(fe.field))) setGenericError(true);
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
      className={
        mobile
          ? "flex h-full flex-col gap-3 overflow-auto text-base [&_input]:min-h-11 [&_select]:min-h-11 [&_button]:min-h-11"
          : "flex h-full flex-col gap-2 overflow-auto text-sm"
      }
      onSubmit={(e) => void handleSubmit(e)}
      noValidate
    >
      {summaryNames !== null &&
        (() => {
          const invalid = fields.filter((f) => summaryNames.includes(f.name));
          if (invalid.length === 0) return null;
          const title = t(
            plural(invalid.length, "widgetForm.errorSummaryOne", "widgetForm.errorSummaryMany"),
            { count: invalid.length },
          );
          return (
            <div
              role="alert"
              aria-label={title}
              className="rounded border border-danger bg-danger-soft p-2 text-xs text-danger"
            >
              <p className="font-medium">{title}</p>
              <ul className="list-disc pl-4">
                {invalid.map((f) => (
                  <li key={f.name}>
                    <a
                      href={`#field-${f.name}`}
                      className="underline"
                      onClick={(e) => {
                        e.preventDefault();
                        document.getElementById(`field-${f.name}`)?.focus();
                      }}
                    >
                      {f.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}
      {fields.map((f) =>
        f.multiple && f.options ? (
          <div key={f.name} className="flex flex-col gap-1">
            <span id={`field-${f.name}-label`}>
              {f.label}
              {f.required ? " *" : ""}
            </span>
            {f.hint && <span className="text-xs text-ink-2">{f.hint}</span>}
            <MultiChoiceInput
              field={f}
              value={values[f.name]}
              onChange={(v) => {
                editedRef.current.add(f.name);
                setValues((old) => ({ ...old, [f.name]: v }));
              }}
              onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
              error={errorFor(f)}
            />
            {errorFor(f) && (
              <span
                id={`field-${f.name}-error`}
                role={summaryNames?.length ? undefined : "alert"}
                className="text-xs text-danger"
              >
                {errorFor(f)}
              </span>
            )}
          </div>
        ) : f.type === "attachment" ? (
          <div key={f.name} className="flex flex-col gap-1">
            <span id={`field-${f.name}-label`}>
              {f.label}
              {f.required ? " *" : ""}
            </span>
            {f.hint && <span className="text-xs text-ink-2">{f.hint}</span>}
            <AttachmentFieldInput
              collectionId={collectionId}
              fid={editingId === null ? null : String(editingId)}
              fieldKey={f.name}
              client={client}
              labelledBy={`field-${f.name}-label`}
              {...((f.kind ?? schemaKind(schemaQuery.data, f.name))
                ? { kind: (f.kind ?? schemaKind(schemaQuery.data, f.name))! }
                : {})}
              {...(mobile
                ? {
                    queued: pendingFiles[f.name] ?? null,
                    onQueue: (file: File | null) =>
                      setPendingFiles((old) => ({ ...old, [f.name]: file })),
                  }
                : {})}
            />
          </div>
        ) : (
          <label key={f.name} className="flex flex-col gap-1">
            {f.label}
            {f.required ? " *" : ""}
            {f.hint && <span className="text-xs text-ink-2">{f.hint}</span>}
            <FieldInput
              field={f}
              value={values[f.name]}
              onChange={(v) =>
                setValues((old) => {
                  editedRef.current.add(f.name);
                  const next = { ...old, [f.name]: v };
                  // ARC-13 : choisir un sous-type pré-remplit ses défauts sur les champs vides.
                  const sub = schemaQuery.data?.subtypes;
                  if (sub && sub.field === f.name) {
                    const picked = sub.items.find((i) => String(i.value) === String(v));
                    for (const [k, d] of Object.entries(picked?.defaults ?? {}))
                      if (next[k] === undefined || next[k] === "") next[k] = d;
                  }
                  return next;
                })
              }
              onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
              error={errorFor(f)}
            />
            {errorFor(f) && (
              // REV-323 : pas de double annonce — quand le résumé (role=alert) est affiché, le
              // message du champ n'est plus qu'un `aria-describedby` relu au focus.
              <span
                id={`field-${f.name}-error`}
                role={summaryNames?.length ? undefined : "alert"}
                className="text-xs text-danger"
              >
                {errorFor(f)}
              </span>
            )}
          </label>
        ),
      )}
      {lineKind(geometryType) && (
        <GeometryInput
          key={geomKey}
          geometryType={geometryType!}
          value={loadedGeometry}
          onChange={(g, issue) => {
            editedRef.current.add("__geom");
            setLoadedGeometry(g);
            setGeomIssue(issue);
            setGeometryError(null);
          }}
        />
      )}
      {geometryError && (
        <p role="alert" className="text-xs text-danger">
          {geometryError}
        </p>
      )}
      {mobile && geometryType === "Point" && (
        <div className="flex flex-col gap-1">
          {/* eslint-disable-next-line geostudio/panel-trigger-aria -- message d'erreur transitoire, pas un panneau */}
          <Button type="button" variant="outline" onClick={locate}>
            {t("widgetForm.useMyPosition")}
          </Button>
          {geoError && (
            <p role="alert" className="text-xs text-danger">
              {t("widgetForm.positionError")}
            </p>
          )}
          {accuracy !== null && (
            <p
              className={accuracy > ACCURACY_WARN_M ? "text-xs text-danger" : "text-xs text-ink-2"}
              role={accuracy > ACCURACY_WARN_M ? "alert" : undefined}
            >
              {t(
                accuracy > ACCURACY_WARN_M ? "widgetForm.accuracyWarning" : "widgetForm.accuracyOk",
                { meters: Math.round(accuracy) },
              )}
            </p>
          )}
        </div>
      )}
      {geometryType === "Point" && (
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">
            {t("widgetForm.longitude")}
            <input
              type="number"
              step="any"
              className={fieldInputCls}
              value={lon}
              onChange={(e) => {
                editedRef.current.add("__geom");
                setLon(e.target.value);
              }}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            {t("widgetForm.latitude")}
            <input
              type="number"
              step="any"
              className={fieldInputCls}
              value={lat}
              onChange={(e) => {
                editedRef.current.add("__geom");
                setLat(e.target.value);
              }}
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
              className="ml-2 text-xs text-danger underline"
              disabled={remove.isPending}
              onClick={() => setConfirmingDelete(true)}
            >
              {t("widgetForm.delete")}
            </button>
          )}
        </p>
      )}
      {editingId !== null && (
        <RelatedRecordsPanel client={client} collectionId={collectionId} fid={String(editingId)} />
      )}
      {editingId !== null && (
        <FeatureHistoryPanel
          client={client}
          collectionId={collectionId}
          fid={String(editingId)}
          canWrite={canWrite}
          onRestored={() => {
            editedRef.current = new Set();
            void syncFromServer(editingId, true);
            void queryClient.invalidateQueries({ queryKey: ["datasource"] });
          }}
        />
      )}
      <ConfirmDialog
        open={confirmingDelete}
        title={t("widgetForm.confirmDeleteTitle")}
        message={t("widgetForm.confirmDelete")}
        confirmLabel={t("widgetForm.delete")}
        pending={remove.isPending}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => {
          setConfirmingDelete(false);
          void handleDelete();
        }}
      />
      <div className="mt-auto flex items-center gap-2">
        {canWrite && (
          // gs-raw-color-ok (SP-B12c grounding) : text-white reste ici volontairement, même
          // convention que widgets/index.tsx (bouton) et tabs.tsx (onglet actif).
          <button
            type="submit"
            disabled={write.isPending || etagLoading}
            className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white disabled:opacity-50" // gs-raw-color-ok: cf. commentaire ci-dessus
          >
            {String(props.submitLabel ?? t("widgetForm.submitDefault"))}
          </button>
        )}
        <button
          type="button"
          className="rounded border border-rule px-3 py-1.5 text-sm"
          onClick={resetTo}
        >
          {t("widgetForm.reset")}
        </button>
      </div>
      {showMyEntries && collectionId !== "" && (
        <MyEntries client={client} collectionId={collectionId} />
      )}
      {conflict && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.conflict")}
        </p>
      )}
      {genericError && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.saveFailed")}
        </p>
      )}
      {attachmentFailed && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.attachmentRetry")}
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
