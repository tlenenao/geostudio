// SPDX-License-Identifier: Apache-2.0
import type { AdminToolName } from "../api/types";
import {
  useInstanceInfo,
  useInstanceStatus,
  useLaunchAdminTool,
  useQuotaUsage,
} from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

const PROTECTED_TOOLS: { tool: AdminToolName; label: string }[] = [
  { tool: "martin", label: "Martin" },
  { tool: "titiler", label: "Titiler" },
  { tool: "grafana", label: "Grafana" },
];

function Probe({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <li>
      {label} : {ok ? t("infrastructure.statusOk") : t("infrastructure.statusDown")}
      {detail ? ` (${detail})` : ""}
    </li>
  );
}

function minioUrl(): string {
  return `${window.location.protocol}//${window.location.hostname}:9001`;
}

export function AdminInfrastructurePage() {
  const instanceQuery = useInstanceInfo();
  const launch = useLaunchAdminTool();
  const adminToolsEnabled = instanceQuery.data?.adminToolsEnabled === true;
  const usageQuery = useQuotaUsage();
  const statusQuery = useInstanceStatus();
  const status = statusQuery.data;
  const backlog = (status?.jobs.queues ?? [])
    .filter((q) => q.status === "todo" || q.status === "doing")
    .reduce((n, q) => n + q.count, 0);
  const usage = usageQuery.data;

  function formatBytes(bytes: number): string {
    const mb = bytes / (1024 * 1024);
    return mb >= 1024 ? `${(mb / 1024).toFixed(1)} Go` : `${mb.toFixed(1)} Mo`;
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "infrastructure",
          label: t("infrastructure.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">{t("infrastructure.heading")}</h1>
              {!adminToolsEnabled && (
                <p className="text-sm text-ink-2">{t("infrastructure.disabled")}</p>
              )}
              {adminToolsEnabled && (
                <div className="flex flex-wrap gap-2">
                  {PROTECTED_TOOLS.map(({ tool, label }) => (
                    <Button
                      key={tool}
                      variant="outline"
                      disabled={launch.isPending}
                      title={t("infrastructure.newTab")}
                      onClick={() => {
                        launch.mutateAsync(tool).then(
                          ({ url }) => {
                            window.open(url, "_blank", "noopener");
                          },
                          () => {},
                        );
                      }}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              )}
              {status && (
                <div className="flex flex-col gap-1 text-sm text-ink-2">
                  <p className="font-medium text-ink">{t("infrastructure.statusHeading")}</p>
                  <ul>
                    <Probe label="PostgreSQL" ok={status.postgres.ok} />
                    <Probe label="S3" ok={status.s3.ok} />
                    <Probe label="CDC" ok={status.cdc.ok && status.cdc.slotActive === true} />
                    <Probe
                      label={t("infrastructure.statusJobs")}
                      ok={status.jobs.ok && !status.jobs.stalled}
                      detail={
                        status.jobs.ok
                          ? t("infrastructure.statusJobsDetail", {
                              pending: backlog,
                              stalled: status.jobs.stalled ?? 0,
                            })
                          : undefined
                      }
                    />
                  </ul>
                </div>
              )}
              {status?.minioConsolePublished && (
                <p className="text-sm text-ink-2">
                  <a
                    href={minioUrl()}
                    target="_blank"
                    rel="noopener noreferrer"
                    // Lien intégré dans une phrase (`link-in-text-block`,
                    // trouvé par l'échantillon a11y élargi REV-178) :
                    // `hover:underline` seul ne distingue le lien du texte
                    // environnant qu'au survol, et le contraste de
                    // `text-accent` sur ce fond est insuffisant (1.49:1) pour
                    // s'en remettre à la seule couleur. Soulignement
                    // permanent, même patron que ReportRunPanel.tsx.
                    className="text-accent underline"
                  >
                    {t("infrastructure.minioConsole")}
                    <span className="sr-only"> {t("infrastructure.newTab")}</span>
                  </a>{" "}
                  {t("infrastructure.minioNote")}
                </p>
              )}
              {usage && (
                <div className="flex flex-col gap-1 text-sm text-ink-2">
                  <p className="font-medium text-ink">{t("infrastructure.usageHeading")}</p>
                  <p>
                    {usage.maxItems === null
                      ? t("infrastructure.usageItems", { count: usage.itemCount })
                      : t("infrastructure.usageItemsWithLimit", {
                          count: usage.itemCount,
                          limit: usage.maxItems,
                        })}
                  </p>
                  <p>
                    {usage.maxCollections === null
                      ? t("infrastructure.usageCollections", { count: usage.collectionCount })
                      : t("infrastructure.usageCollectionsWithLimit", {
                          count: usage.collectionCount,
                          limit: usage.maxCollections,
                        })}
                  </p>
                  <p>
                    {usage.maxStorageBytes === null
                      ? `${t("infrastructure.usageStorage", { size: formatBytes(usage.storageBytes) })} (${t("infrastructure.usageNoLimit")})`
                      : t("infrastructure.usageStorageWithLimit", {
                          size: formatBytes(usage.storageBytes),
                          limitSize: formatBytes(usage.maxStorageBytes),
                        })}
                  </p>
                </div>
              )}
              {launch.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("infrastructure.launchError")}
                </p>
              )}
            </div>
          ),
        }}
        inspect={{ id: "detail", label: t("infrastructure.detail"), content: null }}
      />
    </div>
  );
}
