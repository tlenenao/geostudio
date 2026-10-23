// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  useDeleteLlmSettings,
  useLlmSettings,
  useLlmUsage,
  useSaveLlmSettings,
} from "../api/hooks";
import { apiErrorMessage } from "../api/apiErrorMessage";
import { t } from "../i18n";
import "../i18n/domains/admin";
import { formatNumber } from "../lib/format";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { Field } from "../ui/kit/Field";
import { Input } from "../ui/kit/Input";
import { LoadingState } from "../ui/kit/LoadingState";
import { PageTitle } from "../ui/kit/PageTitle";
import { Panel } from "../ui/kit/Panel";
import { QueryErrorState } from "../ui/kit/QueryErrorState";

// AUD-106 : consommation de tokens du tenant ; AUD-149 : fournisseur LLM propre au
// tenant (« apportez votre modèle »). La clé d'API est en écriture seule : le cœur ne
// la renvoie jamais, le champ vide à l'enregistrement la conserve.

function UsageSection() {
  const usage = useLlmUsage();
  const data = usage.data;
  return (
    <Panel className="flex flex-col gap-3 border border-rule bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">{t("llm.usageTitle")}</h2>
      {usage.isPending && <LoadingState />}
      {usage.isError && (
        <QueryErrorState
          queries={[usage]}
          notFoundMessage={t("llm.usageLoadFailed")}
          loadErrorMessage={t("llm.usageLoadFailed")}
        />
      )}
      {data && (
        <>
          <p className="text-sm text-ink" role="status">
            {data.dailyLimit === null
              ? t("llm.usedTodayNoLimit", { used: formatNumber(data.usedToday, 0) })
              : t("llm.usedToday", {
                  used: formatNumber(data.usedToday, 0),
                  limit: formatNumber(data.dailyLimit, 0),
                })}
          </p>
          {data.days.length === 0 ? (
            <p className="text-sm text-ink-2">{t("llm.noUsage")}</p>
          ) : (
            <table className="w-full border-collapse text-left text-sm text-ink">
              <caption className="sr-only">{t("llm.usageTitle")}</caption>
              <thead>
                <tr className="border-b border-rule">
                  <th scope="col" className="px-3 py-2 font-medium text-ink-2">
                    {t("llm.columnDay")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium text-ink-2">
                    {t("llm.columnCalls")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium text-ink-2">
                    {t("llm.columnPrompt")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium text-ink-2">
                    {t("llm.columnCompletion")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.days.map((d) => (
                  <tr key={d.day} className="border-b border-rule">
                    <th scope="row" className="px-3 py-2 font-normal">
                      {d.day}
                    </th>
                    <td className="px-3 py-2 text-right">{formatNumber(d.calls, 0)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(d.promptTokens, 0)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(d.completionTokens, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Panel>
  );
}

function SettingsSection() {
  const settings = useLlmSettings();
  const save = useSaveLlmSettings();
  const remove = useDeleteLlmSettings();
  const [model, setModel] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [limit, setLimit] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<"idle" | "saved" | "removed">("idle");
  const [error, setError] = useState<string | null>(null);
  const data = settings.data;

  useEffect(() => {
    if (!data) return;
    setModel(data.model ?? "");
    setApiUrl(data.apiUrl ?? "");
    setLimit(data.dailyTokenLimit == null ? "" : String(data.dailyTokenLimit));
    setApiKey("");
  }, [data]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult("idle");
    try {
      await save.mutateAsync({
        model: model.trim() || null,
        apiUrl: apiUrl.trim() || null,
        // Absente = conserver : on n'envoie jamais une chaîne vide.
        ...(apiKey ? { apiKey } : {}),
        dailyTokenLimit: limit.trim() === "" ? null : Number(limit),
      });
      setResult("saved");
    } catch (err) {
      setError(apiErrorMessage(err, t("llm.saveFailed")));
    }
  }

  async function handleRemove() {
    setConfirming(false);
    setError(null);
    setResult("idle");
    try {
      await remove.mutateAsync();
      setResult("removed");
    } catch (err) {
      setError(apiErrorMessage(err, t("llm.removeFailed")));
    }
  }

  const limitInvalid = limit.trim() !== "" && !/^\d+$/.test(limit.trim());

  return (
    <Panel className="flex flex-col gap-3 border border-rule bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">{t("llm.settingsTitle")}</h2>
      <p className="text-sm text-ink-2">{t("llm.settingsDescription")}</p>
      {settings.isPending && <LoadingState />}
      {settings.isError && (
        <QueryErrorState
          queries={[settings]}
          notFoundMessage={t("llm.settingsLoadFailed")}
          loadErrorMessage={t("llm.settingsLoadFailed")}
        />
      )}
      {data && (
        <form className="flex flex-col gap-3" onSubmit={(e) => void handleSave(e)}>
          <p className="text-sm text-ink-2">
            {data.configured ? t("llm.statusTenant") : t("llm.statusEnv")}
          </p>
          <Field label={t("llm.modelLabel")} htmlFor="llm-model">
            <Input id="llm-model" value={model} onChange={(e) => setModel(e.target.value)} />
          </Field>
          <Field label={t("llm.apiUrlLabel")} htmlFor="llm-url" hint={t("llm.apiUrlHint")}>
            <Input
              id="llm-url"
              type="url"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
            />
          </Field>
          <Field
            label={t("llm.apiKeyLabel")}
            htmlFor="llm-key"
            hint={data.hasApiKey ? t("llm.apiKeyKept") : t("llm.apiKeyRequired")}
          >
            <Input
              id="llm-key"
              type="password"
              autoComplete="new-password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </Field>
          <Field
            label={t("llm.limitLabel")}
            htmlFor="llm-limit"
            hint={t("llm.limitHint")}
            error={limitInvalid ? t("llm.limitInvalid") : undefined}
          >
            <Input
              id="llm-limit"
              inputMode="numeric"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={limitInvalid || save.isPending}>
              {t("llm.save")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!data.configured || remove.isPending}
              onClick={() => setConfirming(true)}
            >
              {t("llm.remove")}
            </Button>
          </div>
        </form>
      )}
      <ConfirmDialog
        open={confirming}
        title={t("llm.removeConfirmTitle")}
        message={t("llm.removeConfirmMessage")}
        confirmLabel={t("llm.remove")}
        pending={remove.isPending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void handleRemove()}
      />
      {result === "saved" && (
        <p role="status" className="text-sm text-ink-2">
          {t("llm.saved")}
        </p>
      )}
      {result === "removed" && (
        <p role="status" className="text-sm text-ink-2">
          {t("llm.removed")}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </Panel>
  );
}

export function LlmGovernancePage() {
  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{ id: "back", label: t("domain.catalog"), content: <SettingsNav /> }}
        work={{
          id: "llm",
          label: t("llm.title"),
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <PageTitle>{t("llm.heading")}</PageTitle>
              <UsageSection />
              <SettingsSection />
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("llm.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("llm.helpText")}</p>
            </div>
          ),
        }}
      />
    </div>
  );
}
