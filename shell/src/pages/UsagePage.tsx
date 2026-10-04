// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMe, useUsageSummary, useUsageTasks } from "../api/hooks";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import type { UsageTask } from "../api/types";
import { Button } from "../ui/kit/Button";
import { DataTable } from "../ui/kit/DataTable";
import { EmptyState } from "../ui/kit/EmptyState";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import type { MessageKey } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";
import { Banner } from "../ui/kit/Banner";
import { PageTitle } from "../ui/kit/PageTitle";

const PAGE_SIZE = 50;

// Ressource d'une ligne du journal : titre de l'élément (résolu par le cœur,
// REV-285(f), seulement s'il est lisible par ce profil) et son type en
// français ; repli sur « type · début d'identifiant » sinon.
function ResourceLabel({
  objectType,
  objectId,
  objectTitle,
}: {
  objectType: string;
  objectId: string;
  objectTitle?: string | null;
}) {
  const typeLabel =
    (RESOURCE_TYPE_LABELS as Record<string, string | undefined>)[objectType] ?? objectType;
  if (objectTitle) return <>{t("usage.resourceLabel", { title: objectTitle, type: typeLabel })}</>;
  return <>{t("usage.resourceFallback", { type: typeLabel, id: objectId.slice(0, 8) })}</>;
}

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
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  const totalPages = tasksQuery.data
    ? Math.max(1, Math.ceil(tasksQuery.data.total / PAGE_SIZE))
    : 1;

  function handleSortChange(key: string) {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  const sortedTasks = useMemo(() => {
    const rows = tasksQuery.data?.tasks ?? [];
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      let cmp: number;
      switch (sortKey) {
        case "resource":
          cmp = `${a.objectType}/${a.objectId}`.localeCompare(`${b.objectType}/${b.objectId}`);
          break;
        case "actor":
          cmp = (a.actorUsername ?? "").localeCompare(b.actorUsername ?? "");
          break;
        case "date":
          cmp = a.createdAt.localeCompare(b.createdAt);
          break;
        default:
          cmp = actionLabel(a.action).localeCompare(actionLabel(b.action));
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
  }, [tasksQuery.data, sortKey, sortDirection]);

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
                <PageTitle>{sameTenantAll ? t("usage.tenantTasks") : t("usage.myTasks")}</PageTitle>
                {tasksQuery.isLoading && <LoadingState />}
                {tasksQuery.isError && (
                  <Banner variant="danger" onRetry={() => void tasksQuery.refetch()}>
                    {t("usage.loadFailed")}
                  </Banner>
                )}
                {tasksQuery.data && tasksQuery.data.total === 0 && (
                  <EmptyState title={t("usage.noTasks")} />
                )}
                {tasksQuery.data && tasksQuery.data.total > 0 && (
                  <>
                    <DataTable
                      columns={[
                        ...(sameTenantAll
                          ? [
                              {
                                key: "actor",
                                label: t("usage.columnActor"),
                                render: (task: UsageTask) =>
                                  task.actorUsername ?? task.actorId ?? "—",
                              },
                            ]
                          : []),
                        {
                          key: "action",
                          label: t("usage.columnAction"),
                          render: (task: UsageTask) => actionLabel(task.action),
                        },
                        {
                          key: "resource",
                          label: t("usage.columnResource"),
                          render: (task: UsageTask) => (
                            <ResourceLabel
                              objectType={task.objectType}
                              objectId={task.objectId}
                              objectTitle={task.objectTitle}
                            />
                          ),
                        },
                        {
                          key: "date",
                          label: t("usage.columnDate"),
                          render: (task: UsageTask) => (
                            <span className="text-ink-2">{task.createdAt}</span>
                          ),
                        },
                      ]}
                      rows={sortedTasks}
                      getRowId={(task) => String(task.id)}
                      sortKey={sortKey}
                      sortDirection={sortDirection}
                      onSortChange={handleSortChange}
                    />
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
                    <Banner variant="danger" onRetry={() => void summaryQuery.refetch()}>
                      {t("usage.summaryLoadFailed")}
                    </Banner>
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
                              <ResourceLabel
                                objectType={r.objectType}
                                objectId={r.objectId}
                                objectTitle={r.objectTitle}
                              />{" "}
                              — {r.count}
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
