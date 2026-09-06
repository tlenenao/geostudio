// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMe, useUsageSummary, useUsageTasks } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { EmptyState } from "../ui/kit/EmptyState";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import type { MessageKey } from "../i18n";

const PAGE_SIZE = 50;

// Libellé français par action de JOB_AUDIT_ACTIONS (core/app/usage/service.py)
// — tenu synchronisé manuellement, comme BUILT_IN_ROLE_PRIVILEGES/CREATOR_ME
// (même classe de duplication assumée que les fixtures de rôle, cf. SP-47
// Task 2). Cette page n'est pas un tableau de bord de supervision temps réel
// des jobs (Grafana/OTel) — c'est un journal d'activité fondé sur audit_log
// (SP-47 §7) : une action "déclenchée", pas nécessairement son statut final.
const ACTION_LABELS: Partial<Record<string, MessageKey>> = {
  "ingestion.job_create": "usageAction.ingestionJobCreate",
  "pipeline.run": "usageAction.pipelineRun",
  "export.create": "usageAction.exportCreate",
  "export.run": "usageAction.exportRun",
  "appexport.create": "usageAction.appexportCreate",
  "report.run": "usageAction.reportRun",
  "report.notify": "usageAction.reportNotify",
  "alert.evaluate": "usageAction.alertEvaluate",
  "alert.notify": "usageAction.alertNotify",
  "harvest_source.run": "usageAction.harvestSourceRun",
  "tileset3d.job_create": "usageAction.tileset3dJobCreate",
  "terrain3d.job_create": "usageAction.terrain3dJobCreate",
};

function actionLabel(action: string): string {
  const key = ACTION_LABELS[action];
  return key ? t(key) : action;
}

export function UsagePage() {
  const [page, setPage] = useState(1);
  const meQuery = useMe();
  const tasksQuery = useUsageTasks({ page, pageSize: PAGE_SIZE });
  const sameTenantAll = meQuery.data?.privileges.includes("tasks.view_all") === true;
  const summaryQuery = useUsageSummary({}, { enabled: sameTenantAll });

  const totalPages = tasksQuery.data
    ? Math.max(1, Math.ceil(tasksQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← {t("domain.catalog")}
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "tasks",
          label: t("domain.tasks"),
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <section className="flex flex-col gap-3">
                <h1 className="text-lg font-bold text-ink">{t("usage.myTasks")}</h1>
                {tasksQuery.isLoading && <p role="status">{t("common.loading")}</p>}
                {tasksQuery.isError && (
                  <p role="alert" className="text-sm text-danger">
                    {t("usage.loadFailed")}
                  </p>
                )}
                {tasksQuery.data && tasksQuery.data.total === 0 && (
                  <EmptyState title={t("usage.noTasks")} />
                )}
                {tasksQuery.data && tasksQuery.data.total > 0 && (
                  <>
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-rule">
                          <th className="py-2 text-ink">{t("usage.columnAction")}</th>
                          <th className="py-2 text-ink">{t("usage.columnResource")}</th>
                          <th className="py-2 text-ink">{t("usage.columnDate")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tasksQuery.data.tasks.map((task) => (
                          <tr key={task.id} className="border-b border-rule-2">
                            <td className="py-2 text-ink">{actionLabel(task.action)}</td>
                            <td className="py-2 text-ink">
                              {task.objectType}/{task.objectId}
                            </td>
                            <td className="py-2 text-ink-2">{task.createdAt}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="flex items-center gap-3">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={page <= 1}
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                      >
                        {t("usage.previous")}
                      </Button>
                      <span className="text-sm text-ink-2">
                        {t("usage.pageOf", { page, totalPages })}
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={page >= totalPages}
                        onClick={() => setPage((p) => p + 1)}
                      >
                        {t("usage.next")}
                      </Button>
                    </div>
                  </>
                )}
              </section>
              {sameTenantAll && (
                <section className="flex flex-col gap-3">
                  <h2 className="text-lg font-semibold text-ink">{t("usage.platformUsage")}</h2>
                  {summaryQuery.isError && (
                    <p role="alert" className="text-sm text-danger">
                      {t("usage.summaryLoadFailed")}
                    </p>
                  )}
                  {summaryQuery.data && (
                    <div className="flex gap-8">
                      <div>
                        <h3 className="font-medium text-ink">{t("usage.byActor")}</h3>
                        <ol className="list-inside list-decimal text-sm text-ink-2">
                          {summaryQuery.data.byActor.map((a) => (
                            <li key={a.actorId ?? "?"}>
                              {a.actorUsername ?? a.actorId ?? "?"} — {a.count}
                            </li>
                          ))}
                        </ol>
                      </div>
                      <div>
                        <h3 className="font-medium text-ink">{t("usage.byResource")}</h3>
                        <ol className="list-inside list-decimal text-sm text-ink-2">
                          {summaryQuery.data.byResource.map((r) => (
                            <li key={`${r.objectType}/${r.objectId}`}>
                              {r.objectType}/{r.objectId} — {r.count}
                            </li>
                          ))}
                        </ol>
                      </div>
                    </div>
                  )}
                </section>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("usage.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("usage.helpText")}</p>
            </div>
          ),
        }}
      />
    </div>
  );
}
