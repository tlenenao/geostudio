// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateSecret, useListSecrets } from "../../api/domains/secrets.hooks";
import type { SecretPayload } from "../../api/types";
import { t } from "../../i18n";

// Filtre d'affichage : ne montre jamais le payload déchiffré (le cœur ne le
// retourne de toute façon jamais, ConnectorSecretOut = {id,name,kind,
// createdAt,updatedAt}) — même discipline documentée par
// core/app/secrets/routes.py. GAP-43.
export function SecretParamSelect({
  value,
  onChange,
  ariaLabel,
  kindFilter,
}: {
  value: string;
  onChange: (name: string) => void;
  ariaLabel: string;
  kindFilter?: SecretPayload["kind"];
}) {
  const secretsQuery = useListSecrets();
  const createSecret = useCreateSecret();
  const [creating, setCreating] = useState(false);
  const options = (secretsQuery.data ?? []).filter((s) => !kindFilter || s.kind === kindFilter);

  return (
    <div className="flex flex-col gap-1">
      <select
        aria-label={ariaLabel}
        className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t("secretParamSelect.choose")}</option>
        {options.map((s) => (
          <option key={s.id} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="w-fit text-xs text-accent hover:underline"
        onClick={() => setCreating(true)}
      >
        {t("secretParamSelect.createSecretButton")}
      </button>
      {creating && (
        <SecretCreateForm
          kindFilter={kindFilter}
          onCreated={(name) => {
            onChange(name);
            setCreating(false);
          }}
          onCancel={() => setCreating(false)}
          createSecret={(input) => createSecret.mutateAsync(input)}
        />
      )}
    </div>
  );
}

const KIND_LABELS: Record<SecretPayload["kind"], string> = {
  api_key: t("secretParamSelect.kindApiKey"),
  bearer_token: t("secretParamSelect.kindBearerToken"),
  basic_auth: t("secretParamSelect.kindBasicAuth"),
  oauth2_client_credentials: t("secretParamSelect.kindOAuth2"),
  postgres_dsn: t("secretParamSelect.kindPostgresDsn"),
  smtp: t("secretParamSelect.kindSmtp"),
};

const ALL_KINDS = Object.keys(KIND_LABELS) as SecretPayload["kind"][];

// Un formulaire minimal par variante, pas un générateur JSON Schema complet —
// les 6 variantes de SecretPayload sont fixes et connues (design SP-53 §1).
function SecretCreateForm({
  kindFilter,
  onCreated,
  onCancel,
  createSecret,
}: {
  kindFilter?: SecretPayload["kind"];
  onCreated: (name: string) => void;
  onCancel: () => void;
  createSecret: (input: { name: string; payload: SecretPayload }) => Promise<{ name: string }>;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<SecretPayload["kind"]>(kindFilter ?? ALL_KINDS[0]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  function field(key: string) {
    return fields[key] ?? "";
  }
  function setFieldValue(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  function buildPayload(): SecretPayload | null {
    switch (kind) {
      case "api_key":
        return {
          kind,
          location: field("location") === "query" ? "query" : "header",
          key: field("key"),
          value: field("value"),
        };
      case "bearer_token":
        return { kind, token: field("token") };
      case "basic_auth":
        return { kind, username: field("username"), password: field("password") };
      case "oauth2_client_credentials":
        return {
          kind,
          tokenUrl: field("tokenUrl"),
          clientId: field("clientId"),
          clientSecret: field("clientSecret"),
        };
      case "postgres_dsn":
        return { kind, dsn: field("dsn") };
      case "smtp":
        return {
          kind,
          host: field("host"),
          port: Number(field("port") || "0"),
          username: field("username"),
          password: field("password"),
          useTls: field("useTls") !== "false",
          fromAddress: field("fromAddress"),
        };
      default:
        return null;
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = buildPayload();
    if (!name || !payload) return;
    try {
      const created = await createSecret({ name, payload });
      onCreated(created.name);
    } catch {
      setError(t("secretParamSelect.createFailed"));
    }
  }

  return (
    <form
      onSubmit={(e) => void submit(e)}
      className="flex flex-col gap-2 rounded border border-rule bg-sunken p-2"
    >
      <label className="flex flex-col gap-1 text-xs">
        {t("secretParamSelect.nameLabel")}
        <input
          aria-label={t("secretParamSelect.nameAria")}
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {!kindFilter && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.typeLabel")}
          <select
            aria-label={t("secretParamSelect.typeAria")}
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={kind}
            onChange={(e) => setKind(e.target.value as SecretPayload["kind"])}
          >
            {ALL_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
      )}
      {kind === "api_key" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.locationLabel")}
            <select
              aria-label={t("secretParamSelect.locationAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("location") || "header"}
              onChange={(e) => setFieldValue("location", e.target.value)}
            >
              <option value="header">{t("secretParamSelect.locationHeaderOption")}</option>
              <option value="query">{t("secretParamSelect.locationQueryOption")}</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.keyLabel")}
            <input
              aria-label={t("secretParamSelect.keyAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("key")}
              onChange={(e) => setFieldValue("key", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.valueLabel")}
            <input
              aria-label={t("secretParamSelect.valueAria")}
              type="password"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("value")}
              onChange={(e) => setFieldValue("value", e.target.value)}
            />
          </label>
        </>
      )}
      {kind === "bearer_token" && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.tokenLabel")}
          <input
            aria-label={t("secretParamSelect.tokenAria")}
            type="password"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={field("token")}
            onChange={(e) => setFieldValue("token", e.target.value)}
          />
        </label>
      )}
      {kind === "basic_auth" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.usernameLabel")}
            <input
              aria-label={t("secretParamSelect.usernameAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("username")}
              onChange={(e) => setFieldValue("username", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.passwordLabel")}
            <input
              aria-label={t("secretParamSelect.passwordAria")}
              type="password"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("password")}
              onChange={(e) => setFieldValue("password", e.target.value)}
            />
          </label>
        </>
      )}
      {kind === "oauth2_client_credentials" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.tokenUrlLabel")}
            <input
              aria-label={t("secretParamSelect.tokenUrlAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("tokenUrl")}
              onChange={(e) => setFieldValue("tokenUrl", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.clientIdLabel")}
            <input
              aria-label={t("secretParamSelect.clientIdAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("clientId")}
              onChange={(e) => setFieldValue("clientId", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.clientSecretLabel")}
            <input
              aria-label={t("secretParamSelect.clientSecretAria")}
              type="password"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("clientSecret")}
              onChange={(e) => setFieldValue("clientSecret", e.target.value)}
            />
          </label>
        </>
      )}
      {kind === "postgres_dsn" && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.dsnLabel")}
          <input
            aria-label={t("secretParamSelect.dsnAria")}
            type="password"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={field("dsn")}
            onChange={(e) => setFieldValue("dsn", e.target.value)}
          />
        </label>
      )}
      {kind === "smtp" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.hostLabel")}
            <input
              aria-label={t("secretParamSelect.hostAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("host")}
              onChange={(e) => setFieldValue("host", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.portLabel")}
            <input
              aria-label={t("secretParamSelect.portAria")}
              type="number"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("port")}
              onChange={(e) => setFieldValue("port", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.usernameLabel")}
            <input
              aria-label={t("secretParamSelect.usernameAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("username")}
              onChange={(e) => setFieldValue("username", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.passwordLabel")}
            <input
              aria-label={t("secretParamSelect.passwordAria")}
              type="password"
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("password")}
              onChange={(e) => setFieldValue("password", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.fromAddressLabel")}
            <input
              aria-label={t("secretParamSelect.fromAddressAria")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field("fromAddress")}
              onChange={(e) => setFieldValue("fromAddress", e.target.value)}
            />
          </label>
        </>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="text-xs text-ink-2 hover:underline" onClick={onCancel}>
          {t("secretParamSelect.cancelButton")}
        </button>
        <button type="submit" className="text-xs font-medium text-accent hover:underline">
          {t("secretParamSelect.createButton")}
        </button>
      </div>
    </form>
  );
}
