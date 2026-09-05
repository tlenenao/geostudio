// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useCreateReportSchedule,
  useItem,
  useReportScheduleConfig,
  useSaveReportSchedule,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import type { ReportSchedulePayload } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { hasPermission } from "../auth/permissions";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { ReportScheduleEditor } from "../builder/report/ReportScheduleEditor";
import { ReportRunPanel } from "../builder/report/ReportRunPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

function defaultPayload(bookmarkItemId: string): ReportSchedulePayload {
  return {
    bookmarkItemId,
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
}

// pk === null : brouillon local (/reports/new) — reproduit exactement la
// séparation création/édition à pk nullable de PipelineBuilderPage (la
// justification de SP-15b §2.2 s'applique ici mot pour mot : rien n'est
// persisté avant le premier « Enregistrer »).
export function ReportEditPage({
  pk,
  initialBookmarkItemId,
}: {
  pk: string | null;
  initialBookmarkItemId?: string;
}) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const itemQuery = useItem(pk ?? "", { enabled: pk !== null });
  const configQuery = useReportScheduleConfig(pk ?? "", { enabled: pk !== null });
  const createReport = useCreateReportSchedule();
  const saveReport = useSaveReportSchedule(pk ?? "");
  // SP-42/F-shell-pages-04 : cf. commentaire jumeau sur DatasetEditPage.tsx —
  // même doctrine, même résidu documenté. `pk === null` = brouillon jamais
  // encore créé, rien à verrouiller.
  const readOnly = pk !== null && !hasPermission(itemQuery.data, "write");

  const [draft, setDraft] = useState<ReportSchedulePayload>(
    defaultPayload(initialBookmarkItemId ?? ""),
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createReport.mutateAsync({
          title: "Rapport planifié",
          owner: username ?? "",
          report: draft,
        });
        navigate(`/reports/${item.pk}/edit`, { replace: true });
        return;
      }
      await saveReport.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="report"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              {itemQuery.data && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                  <dt>Type</dt>
                  <dd>{RESOURCE_TYPE_LABELS[itemQuery.data.resourceType]}</dd>
                  <dt>Modifié</dt>
                  <dd>{itemQuery.data.date || "—"}</dd>
                </dl>
              )}
            </Panel>
          ),
        }}
        work={{
          id: "report",
          label: "Rapport",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h2 className="text-lg font-semibold text-ink">
                {pk === null ? "Programmer un rapport" : "Modifier le rapport planifié"}
              </h2>
              <ReportScheduleEditor
                value={draft}
                onChange={setDraft}
                bookmarkLabel={draft.bookmarkItemId}
              />
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Réglages",
          content: (
            <div className="flex flex-col gap-4 p-3">
              {pk !== null && <ReportRunPanel reportId={pk} />}
              {pk !== null && (
                <ConfigHistoryPanel
                  pk={pk}
                  currentVersion={null}
                  onRestored={async () => setDraft(await client.getReportScheduleConfig(pk))}
                />
              )}
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={createReport.isPending || saveReport.isPending || readOnly}
                >
                  Enregistrer
                </Button>
                {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
                {saveError && (
                  <p role="alert" className="text-sm text-danger">
                    {saveError}
                  </p>
                )}
              </div>
            </div>
          ),
        }}
      />
    </div>
  );
}
