// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useAlertEvaluations, useAlertRulesForDataset, useCreateAlertRule } from "../api/hooks";
import type { AlertRuleSummary } from "../api/types";
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import type { PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/kit/Button";

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
  const [webhookUrl, setWebhookUrl] = useState("");
  const [refreshPolicy, setRefreshPolicy] = useState<PipelineRefreshPolicy | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  async function handleCreate() {
    setCreateError(null);
    try {
      await createRule.mutateAsync({
        title: name,
        owner,
        alert: {
          datasetItemId,
          query: { agg: "count" },
          condition: { expr },
          refreshPolicy: refreshPolicy ?? { enabled: true, cron: "*/15 * * * *" },
          channels: [{ kind: "webhook", url: webhookUrl }],
          messageTemplate: "Alert {ruleName}: value={value} ({state})",
        },
      });
      setName("");
      setExpr("");
      setWebhookUrl("");
      setRefreshPolicy(null);
    } catch {
      setCreateError("Échec de la création de la règle.");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-ink-2">Alertes</p>
      {rulesQuery.isError && (
        <p role="alert" className="text-sm text-danger">
          Impossible de charger les règles d'alerte.
        </p>
      )}
      {(rulesQuery.data ?? []).map((rule) => (
        <AlertRuleRow key={rule.itemId} rule={rule} />
      ))}
      <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
        <label className="flex flex-col gap-1">
          Nom de la règle
          <input
            aria-label="Nom de la règle"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Condition (expression)
          <input
            aria-label="Condition (expression)"
            className="h-8 rounded border border-rule bg-surface px-2 font-mono text-ink"
            placeholder="value > 100"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          URL du webhook
          <input
            aria-label="URL du webhook"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
          />
        </label>
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => void handleCreate()}
          disabled={createRule.isPending}
        >
          Créer la règle
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
