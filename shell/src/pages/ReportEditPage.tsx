// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreateReportSchedule,
  useReportScheduleConfig,
  useSaveReportSchedule,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import type { ReportSchedulePayload } from "../api/types";
import { Button } from "../ui/button";
import { ReportScheduleEditor } from "../builder/report/ReportScheduleEditor";
import { ReportRunPanel } from "../builder/report/ReportRunPanel";

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
  const configQuery = useReportScheduleConfig(pk ?? "", { enabled: pk !== null });
  const createReport = useCreateReportSchedule();
  const saveReport = useSaveReportSchedule(pk ?? "");

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
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-medium">
        {pk === null ? "Programmer un rapport" : "Modifier le rapport planifié"}
      </h1>
      <ReportScheduleEditor
        value={draft}
        onChange={setDraft}
        bookmarkLabel={draft.bookmarkItemId}
      />
      <Button
        onClick={() => void onSave()}
        disabled={createReport.isPending || saveReport.isPending}
      >
        Enregistrer
      </Button>
      {saveError && (
        <p role="alert" className="text-sm text-red-600">
          {saveError}
        </p>
      )}
      {pk !== null && <ReportRunPanel reportId={pk} />}
    </div>
  );
}
