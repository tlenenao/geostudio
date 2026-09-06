// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import type { AdminToolName } from "../api/types";
import { useInstanceInfo, useLaunchAdminTool } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

const PROTECTED_TOOLS: { tool: AdminToolName; label: string }[] = [
  { tool: "martin", label: "Martin" },
  { tool: "titiler", label: "Titiler" },
  { tool: "grafana", label: "Grafana" },
];

function minioUrl(): string {
  return `${window.location.protocol}//${window.location.hostname}:9001`;
}

export function AdminInfrastructurePage() {
  const instanceQuery = useInstanceInfo();
  const launch = useLaunchAdminTool();
  const adminToolsEnabled = instanceQuery.data?.adminToolsEnabled === true;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
            </Panel>
          ),
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
              <p className="text-sm text-ink-2">
                <a
                  href={minioUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  {t("infrastructure.minioConsole")}
                </a>{" "}
                {t("infrastructure.minioNote")}
              </p>
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
