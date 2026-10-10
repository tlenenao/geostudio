// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import {
  useCreateReportSchedule,
  useItem,
  useReportScheduleConfig,
  useSaveReportSchedule,
} from "../api/hooks";
import { isConflictError } from "../api/ApiError";
import { SaveConflictNotice } from "../builder/SaveConflictNotice";
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
import { useDirtyGuard } from "../lib/useDirtyGuard";
import { t } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";
import { QueryErrorState } from "../ui/kit/QueryErrorState";
import { PageTitle } from "../ui/kit/PageTitle";
import "../i18n/domains/admin";
import "../i18n/domains/automation";
import "../i18n/domains/misc";

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
  //
  // SP-42, revue finale (point 2, Critical) : quand `pk !== null`,
  // `itemQuery.data` est `undefined` pendant tout le chargement ET en cas
  // d'erreur — hasPermission renvoie alors `false`, verrouillant Enregistrer
  // pour la mauvaise raison. Le garde de rendu plus bas inclut désormais
  // itemQuery.isLoading/isError (même patron que DatasetEditPage.tsx:52-58).
  const readOnly = pk !== null && !hasPermission(itemQuery.data, "write");

  const [draft, setDraft] = useState<ReportSchedulePayload>(
    defaultPayload(initialBookmarkItemId ?? ""),
  );
  const [saveError, setSaveError] = useState<string | null>(null);
  const baseVersionRef = useRef<number | undefined>(undefined);
  const versionSeededRef = useRef(false);
  const [conflict, setConflict] = useState(false);
  // SP-B6d : même patron que MapEditorPage (Tâche 27) — `updateDraft`
  // centralise toute mutation du brouillon issue d'une action utilisateur ;
  // l'effet de synchronisation initiale ci-dessous passe volontairement par
  // le `setDraft` brut pour ne pas marquer le brouillon sale au chargement
  // (ni pour la valeur initiale de useState, brouillon vierge d'un rapport
  // pas encore créé).
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const updateDraft: typeof setDraft = (next) => {
    setHasUnsavedChanges(true);
    setDraft(next);
  };
  const { ConfirmLeaveDialog } = useDirtyGuard(hasUnsavedChanges);

  useEffect(() => {
    // Seed unique (REV-271) : un refetch ne remplace ni brouillon ni version.
    if (pk !== null && configQuery.data && !versionSeededRef.current) {
      versionSeededRef.current = true;
      setDraft(configQuery.data);
      baseVersionRef.current = configQuery.data.baseVersion;
    }
  }, [pk, configQuery.data]);

  if (pk !== null && (configQuery.isLoading || itemQuery.isLoading)) return <LoadingState />;
  // SP-42 F-shell-pages-05 : même garde que PipelineBuilderPage.tsx — sans
  // elle, un rapport existant dont le chargement échoue s'affichait comme un
  // brouillon vide avec Enregistrer actif (422 opaque à la sauvegarde).
  //
  // SP-42, revue finale (point 2, Critical) : itemQuery.isError/!itemQuery.data
  // ajoutés pour la même raison que configQuery.isError — sans eux,
  // `readOnly` se calculait sur `itemQuery.data === undefined` (=> verrouillé
  // à tort) sans jamais bloquer le rendu complet.
  if (pk !== null && (configQuery.isError || itemQuery.isError || !itemQuery.data))
    return (
      <QueryErrorState
        queries={[configQuery, itemQuery]}
        notFoundMessage={t("reportEdit.notFound")}
      />
    );

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createReport.mutateAsync({
          title: t("reportEdit.defaultTitle"),
          owner: username ?? "",
          report: draft,
        });
        // SP-B6d : même précaution que PipelineBuilderPage.tsx (vérifiée
        // empiriquement là-bas) — la redirection vers /reports/{pk}/edit
        // qui suit est une navigation interne réelle (pathname différent).
        // Un simple `setHasUnsavedChanges(false)` synchrone ne suffit pas :
        // le blocker de react-router-dom est ré-enregistré via un effet
        // passif (`useEffect`), pas encore exécuté au moment où `navigate()`
        // s'exécute dans la continuation synchrone du même callback async.
        // `flushSync` force le rendu ET les effets en attente avant l'appel
        // à `navigate()`.
        flushSync(() => setHasUnsavedChanges(false));
        navigate(`/reports/${item.pk}/edit`, { replace: true });
        return;
      }
      const version = await saveReport.mutateAsync({
        ...draft,
        baseVersion: baseVersionRef.current,
      });
      baseVersionRef.current = version;
      setConflict(false);
      setHasUnsavedChanges(false);
    } catch (e) {
      if (isConflictError(e)) {
        setConflict(true);
        return;
      }
      setSaveError(e instanceof Error ? e.message : t("actions.saveFailed"));
    }
  }

  async function reloadLatest() {
    if (pk === null) return;
    const latest = await client.getReportScheduleConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setConflict(false);
    setHasUnsavedChanges(false);
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="report"
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
              {itemQuery.data && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                  <dt>{t("catalog.typeLabel")}</dt>
                  <dd>{RESOURCE_TYPE_LABELS[itemQuery.data.resourceType]}</dd>
                  <dt>{t("datasetEdit.modifiedLabel")}</dt>
                  <dd>{itemQuery.data.updatedAt || "—"}</dd>
                </dl>
              )}
            </Panel>
          ),
        }}
        work={{
          id: "report",
          label: t("reportEdit.reportLabel"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <PageTitle>
                {pk === null ? t("actions.scheduleReport") : t("reportEdit.editHeading")}
              </PageTitle>
              <ReportScheduleEditor
                value={draft}
                onChange={updateDraft}
                bookmarkLabel={draft.bookmarkItemId}
              />
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: t("datasetEdit.settingsLabel"),
          content: (
            <div className="flex flex-col gap-4 p-3">
              {pk !== null && <ReportRunPanel reportId={pk} />}
              {pk !== null && (
                <ConfigHistoryPanel
                  pk={pk}
                  currentVersion={null}
                  onRestored={async () => {
                    const restored = await client.getReportScheduleConfig(pk);
                    updateDraft(restored);
                    baseVersionRef.current = restored.baseVersion;
                  }}
                />
              )}
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={createReport.isPending || saveReport.isPending || readOnly}
                >
                  {t("common.save")}
                </Button>
                {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
                {saveError && (
                  <p role="alert" className="text-sm text-danger">
                    {saveError}
                  </p>
                )}
                {conflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}
              </div>
            </div>
          ),
        }}
      />
      <ConfirmLeaveDialog />
    </div>
  );
}
