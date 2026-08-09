// shell/src/builder/report/ReportRunPanel.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ReportRunStatus } from "../../api/types";

const STATUS_LABEL: Record<ReportRunStatus["status"], string> = {
  pending: "En attente", running: "En cours", done: "Terminé",
  error: "Échec", unknown: "Inconnu",
};

// Historique en lecture seule — reproduit la boucle de sondage de
// PipelineRunPanel (même motif 1500ms qu'ImportFileButton) sans le bouton
// « Exécuter » : un ReportSchedule n'est jamais déclenché que par le cron de
// sweep_report_schedules_task, jamais manuellement, donc il n'y a rien ici
// qu'un bouton pourrait déférer.
export function ReportRunPanel({ reportId }: { reportId: string }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<ReportRunStatus[]>([]);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    async function poll() {
      if (stopped.current) return;
      try {
        const next = await client.getReportRuns(reportId);
        if (!stopped.current) setRuns(next);
      } catch {
        /* transient poll failure — retry on next tick */
      }
      if (!stopped.current) setTimeout(poll, 1500);
    }
    poll();
    return () => {
      stopped.current = true;
    };
  }, [client, reportId]);

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Historique des exécutions</h3>
      {runs.length === 0 && <p className="text-sm text-slate-500">Aucune exécution pour l'instant.</p>}
      <ul className="flex flex-col gap-1">
        {runs.map((run) => (
          <li key={run.id} className="flex items-center gap-2 text-sm">
            <span>{STATUS_LABEL[run.status]}</span>
            <span className="text-slate-400">{new Date(run.createdAt).toLocaleString()}</span>
            {run.resultUrl && (
              <a href={run.resultUrl} className="text-blue-600 underline" target="_blank" rel="noreferrer">
                Télécharger
              </a>
            )}
            {run.error && <span className="text-red-600">{run.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
