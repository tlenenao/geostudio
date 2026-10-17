// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "../api/hooks";
import type { ApiKeyCreated, ApiKeySummary } from "../api/types";
import { t } from "../i18n";
import { formatDateTime } from "../lib/format";
import { Badge } from "../ui/kit/Badge";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { Field } from "../ui/kit/Field";
import { Input } from "../ui/kit/Input";
import { LoadingState } from "../ui/kit/LoadingState";

/** Clés d'API de service (ARC-06, ADR 0016). Le secret n'existe que dans la
 *  réponse de création : on le garde en état local, jamais en cache de requête. */
export function ApiKeysSection() {
  const keysQuery = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const [name, setName] = useState("");
  const [days, setDays] = useState("90");
  const [readOnly, setReadOnly] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [toRevoke, setToRevoke] = useState<ApiKeySummary | null>(null);
  const [error, setError] = useState<"create" | "revoke" | null>(null);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setCreated(
        await createKey.mutateAsync({ name: name.trim(), expiresInDays: Number(days), readOnly }),
      );
      setName("");
    } catch {
      setError("create");
    }
  }

  async function handleRevoke() {
    if (!toRevoke) return;
    setError(null);
    try {
      await revokeKey.mutateAsync(toRevoke.id);
    } catch {
      setError("revoke");
    }
    setToRevoke(null);
  }

  const daysValid = Number.isInteger(Number(days)) && Number(days) >= 1 && Number(days) <= 365;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.apiKeysTitle")}</h2>
      <p className="text-sm text-ink-2">{t("settings.apiKeysHelp")}</p>

      {created && (
        <Banner variant="warn">
          <div className="flex flex-col gap-2">
            <p>{t("settings.apiKeyCreatedNotice")}</p>
            <code className="break-all rounded bg-sunken px-2 py-1 font-mono text-xs">
              {created.token}
            </code>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void navigator.clipboard?.writeText(created.token)}
              >
                {t("settings.apiKeyCopy")}
              </Button>
              <Button type="button" size="sm" onClick={() => setCreated(null)}>
                {t("settings.apiKeyDismiss")}
              </Button>
            </div>
          </div>
        </Banner>
      )}

      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => void handleCreate(e)}>
        <Field label={t("settings.apiKeyName")} htmlFor="api-key-name">
          <Input
            id="api-key-name"
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label={t("settings.apiKeyExpiry")} htmlFor="api-key-days">
          <Input
            id="api-key-days"
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </Field>
        <label className="flex h-9 items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={readOnly}
            onChange={(e) => setReadOnly(e.target.checked)}
          />
          {t("settings.apiKeyReadOnly")}
        </label>
        <Button type="submit" disabled={!name.trim() || !daysValid || createKey.isPending}>
          {t("settings.apiKeyCreate")}
        </Button>
      </form>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error === "create" ? t("settings.apiKeyCreateError") : t("settings.apiKeyRevokeError")}
        </p>
      )}
      {keysQuery.isLoading && <LoadingState />}
      {keysQuery.isError && (
        <Banner variant="danger" onRetry={() => void keysQuery.refetch()}>
          {t("common.loadError")}
        </Banner>
      )}
      {keysQuery.data && keysQuery.data.length === 0 && (
        <p className="text-sm text-ink-3">{t("settings.apiKeyEmpty")}</p>
      )}
      {keysQuery.data && keysQuery.data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {keysQuery.data.map((key) => (
            <li
              key={key.id}
              className="flex flex-wrap items-center gap-2 rounded-md border border-rule px-3 py-2 text-sm"
            >
              <span className="font-medium text-ink">{key.name}</span>
              <code className="font-mono text-xs text-ink-2">{key.prefix}…</code>
              {key.readOnly && <Badge>{t("settings.apiKeyReadOnly")}</Badge>}
              {key.revokedAt ? (
                <Badge>{t("settings.apiKeyRevoked")}</Badge>
              ) : (
                <>
                  <span className="text-xs text-ink-3">
                    {t("settings.apiKeyExpires", { date: formatDateTime(key.expiresAt) })}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    onClick={() => setToRevoke(key)}
                  >
                    {t("settings.apiKeyRevoke")}
                  </Button>
                </>
              )}
              <span className="w-full text-xs text-ink-3">
                {key.lastUsedAt
                  ? t("settings.apiKeyLastUsed", { date: formatDateTime(key.lastUsedAt) })
                  : t("settings.apiKeyNeverUsed")}
              </span>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={toRevoke !== null}
        title={t("settings.apiKeyRevokeTitle")}
        message={t("settings.apiKeyRevokeMessage", { prefix: toRevoke?.prefix ?? "" })}
        confirmLabel={t("settings.apiKeyRevoke")}
        pending={revokeKey.isPending}
        onConfirm={() => void handleRevoke()}
        onCancel={() => setToRevoke(null)}
      />
    </section>
  );
}
