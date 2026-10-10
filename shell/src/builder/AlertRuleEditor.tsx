// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  useAlertEvaluations,
  useAlertRulesForDataset,
  useCreateAlertRule,
  useEvaluateAlertRule,
  useSaveAlertRule,
} from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import { isConflictError } from "../api/ApiError";
import { SaveConflictNotice } from "./SaveConflictNotice";
import type { AlertChannel, AlertRulePayload, AlertRuleSummary } from "../api/types";
import { apiErrorMessage } from "../api/apiErrorMessage";
import { t, type MessageKey } from "../i18n";
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import { SecretParamSelect } from "./pipeline/SecretParamSelect";
import type { PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ANALYTICS_AGGREGATES, aggregateNeedsP, DEFAULT_PERCENTILE } from "./aggregates";
import { PercentileInput } from "./PercentileInput";
import { formatDateTime } from "../lib/format";
import "../i18n/domains/automation";

// GET /alerts/{id}/evaluations pagine déjà côté cœur (limit/offset, SP-50)
// mais cette ligne tronquait silencieusement l'historique à la limite par
// défaut du cœur (100) sans jamais l'envoyer ni exposer de contrôle — même
// patron que ReportRunPanel/PipelineRunPanel (limite croissante, pas
// d'offset).
const EVALUATIONS_PAGE_SIZE = 100;

function AlertRuleRow({
  rule,
  onEdit,
}: {
  rule: AlertRuleSummary;
  onEdit: (rule: AlertRuleSummary) => void;
}) {
  const [limit, setLimit] = useState(EVALUATIONS_PAGE_SIZE);
  const evaluationsQuery = useAlertEvaluations(rule.itemId, { limit });
  const evaluateNow = useEvaluateAlertRule();
  const evaluations = evaluationsQuery.data ?? [];
  const latest = evaluations[0];
  return (
    <div className="flex flex-col gap-1 border-t border-rule py-1 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span>{rule.title}</span>
        <div className="flex items-center gap-2">
          <span className={latest?.state === "firing" ? "font-semibold text-danger" : "text-ink-2"}>
            {latest
              ? t(
                  `alertRule.state${latest.state[0].toUpperCase()}${latest.state.slice(1)}` as MessageKey,
                )
              : "—"}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={() => onEdit(rule)}>
            {t("alertRule.editButton")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={evaluateNow.isPending}
            onClick={() => evaluateNow.mutate(rule.itemId)}
          >
            {t("alertRule.evaluateNowButton")}
          </Button>
        </div>
      </div>
      {latest && (
        <p className="text-ink-2">
          {latest.value !== null && `${t("alertRule.value", { value: latest.value })} · `}
          {formatDateTime(latest.createdAt)}
        </p>
      )}
      {latest?.error && (
        <p className="text-danger" data-testid="alert-latest-error">
          {latest.error}
        </p>
      )}
      {latest?.notifyStatus === "failed" && (
        <p className="text-danger">
          {t("alertRule.notifyFailed", { reason: latest.notifyError ?? "" })}
        </p>
      )}
      {evaluateNow.isError && (
        <p role="alert" className="text-danger">
          {apiErrorMessage(evaluateNow.error, t("alertRule.evaluateError"))}
        </p>
      )}
      {evaluateNow.isSuccess && (
        <p role="status" className="text-ink-2">
          {t("alertRule.evaluateStarted")}
        </p>
      )}
      {evaluations.length >= limit && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => setLimit((l) => l + EVALUATIONS_PAGE_SIZE)}
        >
          {t("alertRule.loadMore")}
        </Button>
      )}
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

  const client = useItemClient();
  const saveRule = useSaveAlertRule();
  // REV-271 : règle en cours de modification (payload complet relu, version lue).
  const [editing, setEditing] = useState<{ itemId: string; payload: AlertRulePayload } | null>(
    null,
  );
  const [conflict, setConflict] = useState(false);

  function resetForm() {
    setName("");
    setExpr("");
    setChannel({ kind: "webhook", url: "" });
    setAgg("count");
    setField("");
    setP(DEFAULT_PERCENTILE);
    setRefreshPolicy(null);
    setEditing(null);
    setConflict(false);
  }

  async function loadForEdit(itemId: string, title: string) {
    setCreateError(null);
    try {
      const payload = await client.getAlertRuleConfig(itemId);
      setName(title);
      setExpr(payload.condition.expr);
      setChannel(payload.channels[0] ?? { kind: "webhook", url: "" });
      setAgg(String(payload.query.agg ?? "count"));
      setField(typeof payload.query.field === "string" ? payload.query.field : "");
      setP(typeof payload.query.p === "number" ? payload.query.p : DEFAULT_PERCENTILE);
      setRefreshPolicy(payload.refreshPolicy);
      setEditing({ itemId, payload });
      setConflict(false);
    } catch {
      setCreateError(t("alertRule.loadError"));
    }
  }

  function buildQuery(): Record<string, unknown> {
    const query: Record<string, unknown> = { agg };
    if (agg !== "count" && field) query.field = field;
    if (aggregateNeedsP(agg)) query.p = p;
    return query;
  }

  async function handleUpdate() {
    if (editing === null) return;
    setCreateError(null);
    try {
      await saveRule.mutateAsync({
        itemId: editing.itemId,
        datasetItemId,
        payload: {
          ...editing.payload, // conserve messageTemplate, canaux au-delà du premier, baseVersion
          query: buildQuery(),
          condition: { expr },
          refreshPolicy: refreshPolicy ?? editing.payload.refreshPolicy,
          channels: [channel, ...editing.payload.channels.slice(1)],
        },
      });
      resetForm();
    } catch (e) {
      if (isConflictError(e)) {
        setConflict(true);
        return;
      }
      setCreateError(t("alertRule.saveError"));
    }
  }

  async function handleCreate() {
    setCreateError(null);
    try {
      await createRule.mutateAsync({
        title: name,
        owner,
        alert: {
          datasetItemId,
          query: buildQuery(),
          condition: { expr },
          refreshPolicy: refreshPolicy ?? { enabled: true, cron: "*/15 * * * *" },
          channels: [channel],
          messageTemplate: "Alert {ruleName}: value={value} ({state})",
        },
      });
      resetForm();
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
        <AlertRuleRow
          key={rule.itemId}
          rule={rule}
          onEdit={(r) => void loadForEdit(r.itemId, r.title)}
        />
      ))}
      <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
        <label className="flex flex-col gap-1">
          {t("alertRule.nameLabel")}
          <input
            className="h-9 rounded border border-control bg-surface px-2 text-ink"
            value={name}
            disabled={editing !== null}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("alertRule.conditionLabel")}
          <input
            className="h-9 rounded border border-control bg-surface px-2 font-mono text-ink"
            placeholder="value > 100"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("alertRule.channelLabel")}
          <select
            className="h-9 rounded border border-control bg-surface px-2 text-ink"
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
          <>
            <label className="flex flex-col gap-1">
              {t("alertRule.webhookUrlLabel")}
              <input
                className="h-9 rounded border border-control bg-surface px-2 text-ink"
                value={channel.url}
                onChange={(e) => setChannel({ ...channel, url: e.target.value })}
              />
            </label>
            <span>{t("alertRule.signingSecretLabel")}</span>
            <SecretParamSelect
              ariaLabel={t("alertRule.signingSecretLabel")}
              kindFilter="bearer_token"
              value={channel.signingSecretName ?? ""}
              onChange={(v) => {
                const { signingSecretName: _drop, ...rest } = channel;
                setChannel(v ? { ...rest, signingSecretName: v } : rest);
              }}
            />
          </>
        )}
        {channel.kind === "email" && (
          <>
            <label className="flex flex-col gap-1">
              {t("alertRule.recipientLabel")}
              <input
                className="h-9 rounded border border-control bg-surface px-2 text-ink"
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
            className="h-9 rounded border border-control bg-surface px-2 text-ink"
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
              className="h-9 rounded border border-control bg-surface px-2 text-ink"
              value={field}
              onChange={(e) => setField(e.target.value)}
            />
          </label>
        )}
        {aggregateNeedsP(agg) && (
          <PercentileInput
            label={t("alertRule.percentileLabel")}
            value={p}
            className="h-9 rounded border border-control bg-surface px-2 text-xs text-ink"
            onCommit={setP}
          />
        )}
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        {conflict && (
          <SaveConflictNotice onReload={() => editing && void loadForEdit(editing.itemId, name)} />
        )}
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => void (editing ? handleUpdate() : handleCreate())}
            disabled={createRule.isPending || saveRule.isPending}
          >
            {editing ? t("alertRule.updateButton") : t("alertRule.createButton")}
          </Button>
          {editing && (
            <Button type="button" variant="outline" size="sm" onClick={resetForm}>
              {t("alertRule.cancelEditButton")}
            </Button>
          )}
        </div>
        {createError && (
          <p role="alert" className="text-danger">
            {createError}
          </p>
        )}
      </div>
    </div>
  );
}
