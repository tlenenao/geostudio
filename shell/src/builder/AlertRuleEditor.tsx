// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useAlertEvaluations, useAlertRulesForDataset, useCreateAlertRule } from "../api/hooks";
import type { AlertChannel, AlertRuleSummary } from "../api/types";
import { t } from "../i18n";
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import { SecretParamSelect } from "./pipeline/SecretParamSelect";
import type { PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ANALYTICS_AGGREGATES, aggregateNeedsP, DEFAULT_PERCENTILE } from "./aggregates";
import { PercentileInput } from "./PercentileInput";

function AlertRuleRow({ rule }: { rule: AlertRuleSummary }) {
  const evaluationsQuery = useAlertEvaluations(rule.itemId);
  const latest = evaluationsQuery.data?.[0];
  return (
    <div className="flex items-center justify-between border-t border-rule py-1 text-xs">
      <span>{rule.title}</span>
      <span className={latest?.state === "firing" ? "font-semibold text-danger" : "text-ink-2"}>
        {latest ? latest.state : "—"}
      </span>
    </div>
  );
}

export function AlertRuleEditor({
  datasetItemId,
  owner,
}: {
  datasetItemId: string;
  owner: string;
}) {
  const rulesQuery = useAlertRulesForDataset(datasetItemId);
  const createRule = useCreateAlertRule();
  const [name, setName] = useState("");
  const [expr, setExpr] = useState("");
  const [channel, setChannel] = useState<AlertChannel>({ kind: "webhook", url: "" });
  const [agg, setAgg] = useState("count");
  const [field, setField] = useState("");
  const [p, setP] = useState(DEFAULT_PERCENTILE);
  const [refreshPolicy, setRefreshPolicy] = useState<PipelineRefreshPolicy | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  async function handleCreate() {
    setCreateError(null);
    try {
      const query: Record<string, unknown> = { agg };
      if (agg !== "count" && field) query.field = field;
      if (aggregateNeedsP(agg)) query.p = p;
      await createRule.mutateAsync({
        title: name,
        owner,
        alert: {
          datasetItemId,
          query,
          condition: { expr },
          refreshPolicy: refreshPolicy ?? { enabled: true, cron: "*/15 * * * *" },
          channels: [channel],
          messageTemplate: "Alert {ruleName}: value={value} ({state})",
        },
      });
      setName("");
      setExpr("");
      setChannel({ kind: "webhook", url: "" });
      setAgg("count");
      setField("");
      setP(DEFAULT_PERCENTILE);
      setRefreshPolicy(null);
    } catch {
      setCreateError(t("alertRule.createError"));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-ink-2">{t("alertRule.heading")}</p>
      {rulesQuery.isError && (
        <p role="alert" className="text-sm text-danger">
          {t("alertRule.loadError")}
        </p>
      )}
      {(rulesQuery.data ?? []).map((rule) => (
        <AlertRuleRow key={rule.itemId} rule={rule} />
      ))}
      <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
        <label className="flex flex-col gap-1">
          {t("alertRule.nameLabel")}
          <input
            aria-label={t("alertRule.nameLabel")}
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("alertRule.conditionLabel")}
          <input
            aria-label={t("alertRule.conditionLabel")}
            className="h-8 rounded border border-rule bg-surface px-2 font-mono text-ink"
            placeholder="value > 100"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("alertRule.channelLabel")}
          <select
            aria-label={t("alertRule.channelLabel")}
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={channel.kind}
            onChange={(e) =>
              setChannel(
                e.target.value === "webhook"
                  ? { kind: "webhook", url: "" }
                  : { kind: "email", to: "", smtpSecretName: "" },
              )
            }
          >
            <option value="webhook">{t("alertRule.channelWebhookOption")}</option>
            <option value="email">{t("alertRule.channelEmailOption")}</option>
          </select>
        </label>
        {channel.kind === "webhook" && (
          <label className="flex flex-col gap-1">
            {t("alertRule.webhookUrlLabel")}
            <input
              aria-label={t("alertRule.webhookUrlLabel")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={channel.url}
              onChange={(e) => setChannel({ kind: "webhook", url: e.target.value })}
            />
          </label>
        )}
        {channel.kind === "email" && (
          <>
            <label className="flex flex-col gap-1">
              {t("alertRule.recipientLabel")}
              <input
                aria-label={t("alertRule.recipientLabel")}
                className="h-8 rounded border border-rule bg-surface px-2 text-ink"
                value={channel.to}
                onChange={(e) =>
                  setChannel({
                    kind: "email",
                    to: e.target.value,
                    smtpSecretName: channel.smtpSecretName,
                  })
                }
              />
            </label>
            <SecretParamSelect
              ariaLabel="secretName"
              kindFilter="smtp"
              value={channel.smtpSecretName}
              onChange={(v) => setChannel({ kind: "email", to: channel.to, smtpSecretName: v })}
            />
          </>
        )}
        <label className="flex flex-col gap-1">
          {t("alertRule.aggregateLabel")}
          <select
            aria-label={t("alertRule.aggregateLabel")}
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={agg}
            onChange={(e) => setAgg(e.target.value)}
          >
            {ANALYTICS_AGGREGATES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        {agg !== "count" && (
          <label className="flex flex-col gap-1">
            {t("alertRule.fieldLabel")}
            <input
              aria-label={t("alertRule.fieldLabel")}
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
              value={field}
              onChange={(e) => setField(e.target.value)}
            />
          </label>
        )}
        {aggregateNeedsP(agg) && (
          <PercentileInput
            label={t("alertRule.percentileLabel")}
            value={p}
            className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
            onCommit={setP}
          />
        )}
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => void handleCreate()}
          disabled={createRule.isPending}
        >
          {t("alertRule.createButton")}
        </Button>
        {createError && (
          <p role="alert" className="text-danger">
            {createError}
          </p>
        )}
      </div>
    </div>
  );
}
