// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateSecret, useDeleteSecret, useListSecrets } from "../../api/domains/secrets.hooks";
import type { SecretPayload } from "../../api/types";
import { t } from "../../i18n";
import { ConfirmDialog } from "../../ui/kit/ConfirmDialog";

// Filtre d'affichage : ne montre jamais le payload déchiffré (le cœur ne le
// retourne de toute façon jamais, ConnectorSecretOut = {id,name,kind,
// createdAt,updatedAt}) — même discipline documentée par
// core/app/secrets/routes.py. GAP-43.
export function SecretParamSelect({
  value,
  onChange,
  ariaLabel,
  kindFilter,
  disabled,
}: {
  value: string;
  onChange: (name: string) => void;
  ariaLabel: string;
  kindFilter?: SecretPayload["kind"];
  // Revue finale Vague C (point 2, D55) : PipelineNodeInspector propage
  // `readOnly` jusqu'ici. Désactive aussi la création/suppression de secret
  // depuis cet inspecteur (pas seulement la sélection de valeur) — une
  // mutation globale de secret déclenchée depuis un pipeline en lecture
  // seule serait tout aussi surprenante que muter le nœud lui-même.
  disabled?: boolean;
}) {
  const secretsQuery = useListSecrets();
  const createSecret = useCreateSecret();
  const deleteSecret = useDeleteSecret();
  const [creating, setCreating] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const options = (secretsQuery.data ?? []).filter((s) => !kindFilter || s.kind === kindFilter);

  return (
    <div className="flex flex-col gap-1">
      <select
        aria-label={ariaLabel}
        className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">{t("secretParamSelect.choose")}</option>
        {options.map((s) => (
          <option key={s.id} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>
      {!disabled && (
        <>
          <ul className="flex flex-col gap-1">
            {options.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 text-xs text-ink-2">
                <span>{s.name}</span>
                <button
                  type="button"
                  className="text-danger hover:underline"
                  onClick={() => setPendingDeleteId(s.id)}
                >
                  {t("secretParamSelect.deleteButton", { name: s.name })}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="w-fit text-xs text-accent hover:underline"
            onClick={() => setCreating(true)}
          >
            {t("secretParamSelect.createSecretButton")}
          </button>
        </>
      )}
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
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t("secretParamSelect.deleteConfirmTitle")}
        message={t("secretParamSelect.deleteConfirmMessage")}
        confirmLabel={t("secretParamSelect.deleteConfirmButton")}
        pending={deleteSecret.isPending}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => {
          if (!pendingDeleteId) return;
          deleteSecret.mutate(pendingDeleteId, {
            onSuccess: () => setPendingDeleteId(null),
          });
        }}
      />
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
  snowflake_dsn: t("secretParamSelect.kindSnowflakeDsn"),
  bigquery_dsn: t("secretParamSelect.kindBigqueryDsn"),
  mssql_dsn: t("secretParamSelect.kindMssqlDsn"),
  oracle_dsn: t("secretParamSelect.kindOracleDsn"),
  databricks_dsn: t("secretParamSelect.kindDatabricksDsn"),
  s3_credentials: t("secretParamSelect.kindS3Credentials"),
  azure_blob_credentials: t("secretParamSelect.kindAzureBlobCredentials"),
  gcs_credentials: t("secretParamSelect.kindGcsCredentials"),
};

const BUCKET_PLACEHOLDER_KEYS = {
  s3_credentials: "secretParamSelect.bucketUrlPlaceholderS3",
  azure_blob_credentials: "secretParamSelect.bucketUrlPlaceholderAz",
  gcs_credentials: "secretParamSelect.bucketUrlPlaceholderGs",
} as const;

const ALL_KINDS = Object.keys(KIND_LABELS) as SecretPayload["kind"][];

// Un formulaire minimal par variante, pas un générateur JSON Schema complet —
// les variantes de SecretPayload sont fixes et connues (design SP-53 §1 ;
// 13 depuis Vague 2 : bigquery_dsn/mssql_dsn/oracle_dsn/s3_credentials/
// azure_blob_credentials/gcs_credentials en plus des 7 précédentes).
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
      case "snowflake_dsn":
      case "bigquery_dsn":
      case "mssql_dsn":
      case "oracle_dsn":
      case "databricks_dsn":
        return { kind, dsn: field("dsn") };
      case "s3_credentials":
        return {
          kind,
          awsAccessKeyId: field("awsAccessKeyId"),
          awsSecretAccessKey: field("awsSecretAccessKey"),
          endpointUrl: field("endpointUrl") || undefined,
          bucketUrl: field("bucketUrl"),
        };
      case "azure_blob_credentials":
        return {
          kind,
          accountName: field("accountName"),
          accountKey: field("accountKey"),
          bucketUrl: field("bucketUrl"),
        };
      case "gcs_credentials": {
        const parsed = JSON.parse(field("serviceAccountInfo") || "{}") as Record<string, unknown>;
        return { kind, serviceAccountInfo: parsed, bucketUrl: field("bucketUrl") };
      }
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
    setError(null);
    let payload: SecretPayload | null;
    try {
      payload = buildPayload();
    } catch {
      setError(t("secretParamSelect.serviceAccountInfoInvalid"));
      return;
    }
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
      className="flex flex-col gap-2 rounded border border-rule bg-sunken p-2 text-ink"
    >
      <label className="flex flex-col gap-1 text-xs">
        {t("secretParamSelect.nameLabel")}
        <input
          aria-label={t("secretParamSelect.nameAria")}
          placeholder={t("secretParamSelect.namePlaceholder")}
          className="h-8 rounded border border-control bg-surface px-2 text-ink"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {!kindFilter && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.typeLabel")}
          <select
            aria-label={t("secretParamSelect.typeAria")}
            className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
              placeholder={t("secretParamSelect.keyPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("key")}
              onChange={(e) => setFieldValue("key", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.valueLabel")}
            <input
              aria-label={t("secretParamSelect.valueAria")}
              placeholder={t("secretParamSelect.valuePlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
            placeholder={t("secretParamSelect.tokenPlaceholder")}
            type="password"
            className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
              placeholder={t("secretParamSelect.usernamePlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("username")}
              onChange={(e) => setFieldValue("username", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.passwordLabel")}
            <input
              aria-label={t("secretParamSelect.passwordAria")}
              placeholder={t("secretParamSelect.passwordPlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
              placeholder={t("secretParamSelect.tokenUrlPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("tokenUrl")}
              onChange={(e) => setFieldValue("tokenUrl", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.clientIdLabel")}
            <input
              aria-label={t("secretParamSelect.clientIdAria")}
              placeholder={t("secretParamSelect.clientIdPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("clientId")}
              onChange={(e) => setFieldValue("clientId", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.clientSecretLabel")}
            <input
              aria-label={t("secretParamSelect.clientSecretAria")}
              placeholder={t("secretParamSelect.clientSecretPlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("clientSecret")}
              onChange={(e) => setFieldValue("clientSecret", e.target.value)}
            />
          </label>
        </>
      )}
      {(kind === "postgres_dsn" ||
        kind === "snowflake_dsn" ||
        kind === "bigquery_dsn" ||
        kind === "mssql_dsn" ||
        kind === "oracle_dsn" ||
        kind === "databricks_dsn") && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.dsnLabel")}
          <input
            aria-label={t("secretParamSelect.dsnAria")}
            placeholder={t("secretParamSelect.dsnPlaceholder")}
            type="password"
            className="h-8 rounded border border-control bg-surface px-2 text-ink"
            value={field("dsn")}
            onChange={(e) => setFieldValue("dsn", e.target.value)}
          />
        </label>
      )}
      {kind === "s3_credentials" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.awsAccessKeyIdLabel")}
            <input
              aria-label={t("secretParamSelect.awsAccessKeyIdAria")}
              placeholder={t("secretParamSelect.awsAccessKeyIdPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("awsAccessKeyId")}
              onChange={(e) => setFieldValue("awsAccessKeyId", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.awsSecretAccessKeyLabel")}
            <input
              aria-label={t("secretParamSelect.awsSecretAccessKeyAria")}
              placeholder={t("secretParamSelect.awsSecretAccessKeyPlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("awsSecretAccessKey")}
              onChange={(e) => setFieldValue("awsSecretAccessKey", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.endpointUrlLabel")}
            <input
              aria-label={t("secretParamSelect.endpointUrlAria")}
              placeholder={t("secretParamSelect.endpointUrlPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("endpointUrl")}
              onChange={(e) => setFieldValue("endpointUrl", e.target.value)}
            />
          </label>
        </>
      )}
      {kind === "azure_blob_credentials" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.accountNameLabel")}
            <input
              aria-label={t("secretParamSelect.accountNameAria")}
              placeholder={t("secretParamSelect.accountNamePlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("accountName")}
              onChange={(e) => setFieldValue("accountName", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.accountKeyLabel")}
            <input
              aria-label={t("secretParamSelect.accountKeyAria")}
              placeholder={t("secretParamSelect.accountKeyPlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("accountKey")}
              onChange={(e) => setFieldValue("accountKey", e.target.value)}
            />
          </label>
        </>
      )}
      {kind === "gcs_credentials" && (
        <label className="flex flex-col gap-1 text-xs">
          {t("secretParamSelect.serviceAccountInfoLabel")}
          <textarea
            aria-label={t("secretParamSelect.serviceAccountInfoAria")}
            placeholder={t("secretParamSelect.serviceAccountInfoPlaceholder")}
            className="h-24 rounded border border-control bg-surface px-2 py-1 text-ink"
            value={field("serviceAccountInfo")}
            onChange={(e) => setFieldValue("serviceAccountInfo", e.target.value)}
          />
        </label>
      )}
      {(kind === "s3_credentials" ||
        kind === "azure_blob_credentials" ||
        kind === "gcs_credentials") && (
        <div className="flex flex-col gap-1 text-xs">
          <label className="flex flex-col gap-1">
            {t("secretParamSelect.bucketUrlLabel")}
            <input
              aria-label={t("secretParamSelect.bucketUrlAria")}
              placeholder={t(BUCKET_PLACEHOLDER_KEYS[kind])}
              required
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("bucketUrl")}
              onChange={(e) => setFieldValue("bucketUrl", e.target.value)}
            />
          </label>
          <span className="text-ink-2">{t("secretParamSelect.bucketUrlHelp")}</span>
        </div>
      )}
      {kind === "smtp" && (
        <>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.hostLabel")}
            <input
              aria-label={t("secretParamSelect.hostAria")}
              placeholder={t("secretParamSelect.hostPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("host")}
              onChange={(e) => setFieldValue("host", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.portLabel")}
            <input
              aria-label={t("secretParamSelect.portAria")}
              placeholder={t("secretParamSelect.portPlaceholder")}
              type="number"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("port")}
              onChange={(e) => setFieldValue("port", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.usernameLabel")}
            <input
              aria-label={t("secretParamSelect.usernameAria")}
              placeholder={t("secretParamSelect.usernamePlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("username")}
              onChange={(e) => setFieldValue("username", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.passwordLabel")}
            <input
              aria-label={t("secretParamSelect.passwordAria")}
              placeholder={t("secretParamSelect.passwordPlaceholder")}
              type="password"
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("password")}
              onChange={(e) => setFieldValue("password", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t("secretParamSelect.fromAddressLabel")}
            <input
              aria-label={t("secretParamSelect.fromAddressAria")}
              placeholder={t("secretParamSelect.fromAddressPlaceholder")}
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
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
