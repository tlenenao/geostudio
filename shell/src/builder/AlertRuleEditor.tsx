// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useAlertEvaluations, useAlertRulesForDataset, useCreateAlertRule } from "../api/hooks";
import type { AlertRuleSummary } from "../api/types";
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import type { PipelineRefreshPolicy } from "../api/types";

function AlertRuleRow({ rule }: { rule: AlertRuleSummary }) {
  const evaluationsQuery = useAlertEvaluations(rule.itemId);
  const latest = evaluationsQuery.data?.[0];
  return (
    <div className="flex items-center justify-between border-t border-slate-200 py-1 text-xs">
      <span>{rule.title}</span>
      <span className={latest?.state === "firing" ? "font-semibold text-red-600" : "text-slate-500"}>
        {latest ? latest.state : "—"}
      </span>
    </div>
  );
}

export function AlertRuleEditor({ datasetItemId, owner }: { datasetItemId: string; owner: string }) {
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
        title: name, owner,
        alert: {
          datasetItemId, query: { agg: "count" }, condition: { expr },
          refreshPolicy: refreshPolicy ?? { enabled: true, cron: "*/15 * * * *" },
          channels: [{ kind: "webhook", url: webhookUrl }],
          messageTemplate: "Alert {ruleName}: value={value} ({state})",
        },
      });
      setName(""); setExpr(""); setWebhookUrl(""); setRefreshPolicy(null);
    } catch {
      setCreateError("Échec de la création de la règle.");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-slate-500">Alertes</p>
      {(rulesQuery.data ?? []).map((rule) => <AlertRuleRow key={rule.itemId} rule={rule} />)}
      <div className="flex flex-col gap-2 border-t border-slate-200 pt-2 text-xs">
        <label className="flex flex-col gap-1">
          Nom de la règle
          <input aria-label="Nom de la règle" className="h-8 rounded border border-slate-300 px-2"
            value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          Condition (expression)
          <input aria-label="Condition (expression)" className="h-8 rounded border border-slate-300 px-2 font-mono"
            placeholder="value > 100" value={expr} onChange={(e) => setExpr(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          URL du webhook
          <input aria-label="URL du webhook" className="h-8 rounded border border-slate-300 px-2"
            value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} />
        </label>
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        <button type="button"
          className="self-start rounded border border-slate-300 px-2 py-1 hover:bg-slate-100"
          onClick={handleCreate} disabled={createRule.isPending}>
          Créer la règle
        </button>
        {createError && <p role="alert" className="text-red-600">{createError}</p>}
      </div>
    </div>
  );
}
