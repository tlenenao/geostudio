// shell/src/builder/report/ReportRunPanel.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ReportRunStatus } from "../../api/types";

const STATUS_LABEL: Record<ReportRunStatus["status"], string> = {
  pending: "En attente",
  running: "En cours",
  done: "Terminé",
  error: "Échec",
  unknown: "Inconnu",
};

// Rythmes de sondage. PipelineRunPanel s'arrête net dès que le run quitte
// queued/running ; ici un run peut apparaître à tout moment (le cron de
// sweep_report_schedules_task balaie toutes les 5 minutes), donc plutôt que
// de s'arrêter définitivement on repasse en rythme lent quand plus rien ne
// rend — la boucle ne martèle plus le serveur toutes les 1,5 s pendant des
// heures d'onglet ouvert (revue finale SP-17b, I5).
const ACTIVE_POLL_MS = 1500;
const IDLE_POLL_MS = 30000;

function isRendering(runs: ReportRunStatus[]): boolean {
  const latest = runs[0]?.status;
  return latest === "pending" || latest === "running";
}

// Historique en lecture seule — reproduit la boucle de sondage de
// PipelineRunPanel (même motif 1500ms qu'ImportFileButton) sans le bouton
// « Exécuter » : un ReportSchedule n'est jamais déclenché que par le cron de
// sweep_report_schedules_task, jamais manuellement, donc il n'y a rien ici
// qu'un bouton pourrait déférer.
export function ReportRunPanel({ reportId }: { reportId: string }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<ReportRunStatus[]>([]);
  const [hasError, setHasError] = useState(false);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    async function poll() {
      if (stopped.current) return;
      let delay = IDLE_POLL_MS;
      try {
        const next = await client.getReportRuns(reportId);
        if (stopped.current) return;
        setRuns(next);
        setHasError(false);
        delay = isRendering(next) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
      } catch {
        // Un échec persistant doit être visible : sans cet état, une liste
        // vide pour cause de panne réseau était indiscernable d'un « aucune
        // exécution » légitime (même défaut corrigé en revue sur l'UI
        // d'alertes SP-16b).
        if (stopped.current) return;
        setHasError(true);
      }
      if (!stopped.current) setTimeout(() => void poll(), delay);
    }
    void poll();
    return () => {
      stopped.current = true;
    };
  }, [client, reportId]);

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Historique des exécutions</h3>
      {hasError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de charger l'historique des exécutions.
        </p>
      )}
      {!hasError && runs.length === 0 && (
        <p className="text-sm text-slate-500">Aucune exécution pour l'instant.</p>
      )}
      <ul className="flex flex-col gap-1">
        {runs.map((run) => (
          <li key={run.id} className="flex items-center gap-2 text-sm">
            <span>{STATUS_LABEL[run.status]}</span>
            <span className="text-slate-400">{new Date(run.createdAt).toLocaleString()}</span>
            {run.resultUrl && (
              <a
                href={run.resultUrl}
                className="text-blue-600 underline"
                target="_blank"
                rel="noreferrer"
              >
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
