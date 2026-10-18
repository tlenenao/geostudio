// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { loadRuntimeConfig } from "../config";
import { ApiError } from "../api/ApiError";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { fetchPublicKit, submitPublic } from "../api/domains/publicSubmit";
import type { CollectKit } from "../api/types";
import {
  applyDomains,
  fieldInputCls,
  FieldInput,
  MultiChoiceInput,
  mediaAttrs,
  validateField,
  type FormField,
} from "../builder/widgets/form";
import { GeometryInput, lineKind, type GeometryIssue } from "../builder/widgets/GeometryInput";
import { evaluateExpression, type ExprContext } from "../builder/expr";
import { compressImage } from "../offline/compressImage";
import { t } from "../i18n";
import { Button } from "../ui/kit/Button";
import { LoadingState } from "../ui/kit/LoadingState";
import "../i18n/domains/widgets";

// Route publique hors `<ProtectedLayout>` : aucune session, la configuration est relue de
// l'environnement comme pour EmbedPage.
// Le cœur est servi sous /v1 (createBase() l'ajoute de même pour l'ItemClient).
const coreV1 = `${loadRuntimeConfig().coreUrl}/v1`;

// Même plafond que le cœur (`service.MAX_FILES`).
const MAX_FILES = 5;

function fieldsOf(kit: CollectKit): FormField[] {
  return kit.schema.fields
    .filter((f) => f.type !== "unsupported")
    .map((f, i) => ({
      name: f.name,
      type: f.type,
      label: f.label ?? f.name,
      order: i,
      hidden: false,
      required: f.required,
      ...(f.maxLength !== undefined ? { maxLength: f.maxLength } : {}),
      ...(f.values !== undefined ? { values: f.values } : {}),
      ...(f.kind ? { kind: f.kind } : {}),
      ...(f.type === "list" ? { multiple: true } : {}),
    }));
}

function loadErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 404) return t("collect.notFound");
  if (err instanceof ApiError && err.status === 410) return t("collect.expired");
  if (err instanceof CoreUnreachableError) return t("collect.unreachable");
  return t("collect.loadError");
}

function sendErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return t("collect.notFound");
    if (err.status === 410) return t("collect.expired");
    if (err.status === 403) return t("collect.powRejected");
    if (err.status === 429)
      return /quota/i.test(err.detail ?? "")
        ? t("collect.quotaExhausted")
        : t("collect.rateLimited");
  }
  return t("collect.sendError");
}

export function CollectPage({ token }: { token: string }) {
  const kitQuery = useQuery({
    queryKey: ["collect-kit", token],
    queryFn: () => fetchPublicKit(coreV1, token),
    retry: false,
  });
  const kit = kitQuery.data ?? null;
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 p-4">
      <h1 className="text-lg font-semibold text-ink">{kit?.title ?? t("docTitle.collect")}</h1>
      {kitQuery.isLoading && <LoadingState />}
      {kitQuery.isError && (
        <p role="alert" className="text-sm text-danger">
          {loadErrorMessage(kitQuery.error)}
        </p>
      )}
      {kit && <CollectForm key={token} kit={kit} token={token} />}
    </main>
  );
}

function CollectForm({ kit, token }: { kit: CollectKit; token: string }) {
  const baseFields = useMemo(() => fieldsOf(kit), [kit]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [geometry, setGeometry] = useState<unknown>(null);
  const [geomIssue, setGeomIssue] = useState<GeometryIssue>(null);
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [geomKey, setGeomKey] = useState(0);
  const [honeypot, setHoneypot] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // Un seul identifiant par saisie : un renvoi après coupure ne la compte pas deux fois.
  const opId = useRef(crypto.randomUUID());

  const fields = applyDomains(baseFields, kit.schema as never, values);
  const geometryType = kit.schema.geometry?.type ?? null;
  const pointGeometry =
    geometryType === "Point" && lon !== "" && lat !== ""
      ? { type: "Point", coordinates: [Number(lon), Number(lat)] }
      : null;
  const geometryNow = geometryType === "Point" ? pointGeometry : geometry;

  const bindings = Object.fromEntries(
    fields.map((f) => [f.name, values[f.name] === undefined ? null : values[f.name]]),
  ) as unknown as ExprContext;
  const ruleErrors: Record<string, string> = {};
  for (const r of kit.rules) {
    if (r.kind !== "constraint" || !r.field) continue;
    if (evaluateExpression(r.expression, bindings) === false)
      ruleErrors[r.field] ??= r.message ?? t("widgetForm.invalidValue");
  }
  const errorFor = (f: FormField): string | null => {
    if (!touched[f.name] && !submitted) return null;
    if (f.type === "attachment")
      return f.required && !files[f.name] ? t("widgetForm.requiredError") : null;
    return validateField(f, values[f.name]) ?? ruleErrors[f.name] ?? null;
  };
  const chosen = Object.values(files).filter((f): f is File => f !== null);
  const geometryMissing = kit.geometryRequired && geometryNow === null;
  const valid =
    fields.every((f) =>
      f.type === "attachment"
        ? !f.required || !!files[f.name]
        : validateField(f, values[f.name]) === null && !ruleErrors[f.name],
    ) &&
    !geometryMissing &&
    geomIssue === null &&
    chosen.length <= MAX_FILES;

  function locate() {
    navigator.geolocation?.getCurrentPosition((pos) => {
      setLon(String(pos.coords.longitude));
      setLat(String(pos.coords.latitude));
      setAccuracy(typeof pos.coords.accuracy === "number" ? pos.coords.accuracy : null);
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setFailure(null);
    if (!valid) {
      const first = fields.find((f) => errorFor({ ...f }) !== null || ruleErrors[f.name]);
      if (first) document.getElementById(`field-${first.name}`)?.focus();
      return;
    }
    const properties: Record<string, unknown> = {};
    for (const f of fields)
      if (f.type !== "attachment" && values[f.name] !== undefined)
        properties[f.name] = values[f.name];
    if (accuracy !== null && fields.some((f) => f.name === "gps_accuracy"))
      properties.gps_accuracy = Math.round(accuracy);
    setSending(true);
    try {
      await submitPublic(coreV1, token, {
        feature: { type: "Feature", properties, geometry: geometryNow },
        files: Object.entries(files)
          .filter((e): e is [string, File] => e[1] !== null)
          .map(([fieldKey, file]) => ({ fieldKey, file })),
        clientOpId: opId.current,
        honeypot,
      });
      setDone(true);
    } catch (err) {
      setFailure(sendErrorMessage(err));
    } finally {
      setSending(false);
    }
  }

  function another() {
    opId.current = crypto.randomUUID();
    setValues({});
    setFiles({});
    setTouched({});
    setSubmitted(false);
    setGeometry(null);
    setGeomIssue(null);
    setGeomKey((k) => k + 1);
    setLon("");
    setLat("");
    setAccuracy(null);
    setDone(false);
  }

  if (done) {
    return (
      <div className="flex flex-col gap-3">
        <p role="status" className="text-sm text-ink">
          {t("collect.thanks")}
        </p>
        <Button type="button" variant="outline" className="self-start" onClick={another}>
          {t("collect.another")}
        </Button>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={(e) => void onSubmit(e)} className="flex flex-col gap-3">
      <p className="text-xs text-ink-2">{t("collect.requiredNote")}</p>
      {fields.map((f) => {
        const err = errorFor(f);
        if (f.type === "attachment") {
          const id = `field-${f.name}`;
          return (
            <label key={f.name} className="flex flex-col gap-1">
              {f.label}
              {f.required ? " *" : ""}
              <input
                id={id}
                type="file"
                className="text-sm"
                {...mediaAttrs(f.kind)}
                aria-required={f.required ? "true" : undefined}
                aria-invalid={err ? "true" : undefined}
                onChange={(e) => {
                  const picked = e.target.files?.[0] ?? null;
                  setTouched((o) => ({ ...o, [f.name]: true }));
                  // Une photo est réduite dès le choix (zone à faible débit).
                  if (picked && (f.kind ?? "image") === "image")
                    void compressImage(picked).then((c) =>
                      setFiles((o) => ({ ...o, [f.name]: c })),
                    );
                  else setFiles((o) => ({ ...o, [f.name]: picked }));
                }}
              />
              {files[f.name] && (
                <span className="text-xs text-ink-2">
                  {t("collect.fileField", { name: files[f.name]!.name })}
                </span>
              )}
              {err && (
                <span role="alert" className="text-xs text-danger">
                  {err}
                </span>
              )}
            </label>
          );
        }
        const input =
          f.multiple && f.options ? (
            <MultiChoiceInput
              field={f}
              value={values[f.name]}
              onChange={(v) => setValues((o) => ({ ...o, [f.name]: v }))}
              onBlur={() => setTouched((o) => ({ ...o, [f.name]: true }))}
              error={err}
            />
          ) : (
            <FieldInput
              field={f}
              value={values[f.name]}
              onChange={(v) => setValues((o) => ({ ...o, [f.name]: v }))}
              onBlur={() => setTouched((o) => ({ ...o, [f.name]: true }))}
              error={err}
            />
          );
        const label = `${f.label}${f.required ? " *" : ""}`;
        return f.multiple && f.options ? (
          <div key={f.name} className="flex flex-col gap-1">
            <span id={`field-${f.name}-label`}>{label}</span>
            {input}
            {err && (
              <span id={`field-${f.name}-error`} role="alert" className="text-xs text-danger">
                {err}
              </span>
            )}
          </div>
        ) : (
          <label key={f.name} className="flex flex-col gap-1">
            {label}
            {input}
            {err && (
              <span id={`field-${f.name}-error`} role="alert" className="text-xs text-danger">
                {err}
              </span>
            )}
          </label>
        );
      })}
      {lineKind(geometryType ?? "") && (
        <GeometryInput
          key={geomKey}
          geometryType={geometryType!}
          value={geometry}
          onChange={(g, issue) => {
            setGeometry(g);
            setGeomIssue(issue);
          }}
        />
      )}
      {geometryType === "Point" && (
        <div className="flex flex-col gap-2">
          <Button type="button" variant="outline" className="self-start" onClick={locate}>
            {t("widgetForm.useMyPosition")}
          </Button>
          <div className="flex gap-2">
            <label className="flex flex-1 flex-col gap-1">
              {t("widgetForm.longitude")}
              <input
                type="number"
                step="any"
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
                className={fieldInputCls}
                value={lat}
                onChange={(e) => setLat(e.target.value)}
              />
            </label>
          </div>
        </div>
      )}
      {submitted && geometryMissing && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.geometryRequired")}
        </p>
      )}
      {submitted && chosen.length > MAX_FILES && (
        <p role="alert" className="text-xs text-danger">
          {t("collect.maxFiles", { max: MAX_FILES })}
        </p>
      )}
      {/* Piège à robots : hors écran, hors tabulation, jamais annoncé. */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-10000px" }}>
        <input
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          aria-label={t("collect.honeypot")}
          value={honeypot}
          onChange={(e) => setHoneypot(e.target.value)}
        />
      </div>
      {failure && (
        <p role="alert" className="text-sm text-danger">
          {failure}
        </p>
      )}
      <Button type="submit" disabled={sending} className="self-start">
        {sending ? t("collect.sending") : t("collect.submit")}
      </Button>
    </form>
  );
}
