// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { PipelineRun } from "../../api/types";
import { Button } from "../../ui/kit/Button";

const STATUS_LABEL: Record<PipelineRun["status"], string> = {
  queued: "En attente",
  running: "En cours",
  succeeded: "succeeded",
  failed: "failed",
};

// Patron de poll identique à shell/src/shell/ImportFileButton.tsx (SP-6a) —
// boucle récursive manuelle via le client, pas un refetchInterval react-query
// (cf. plan Global Constraints).
export function PipelineRunPanel({
  pipelineId,
  onLatestRunChange,
}: {
  pipelineId: string;
  onLatestRunChange?: (run: PipelineRun | null) => void;
}) {
  const client = useItemClient();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Effet de nettoyage dédié (patron ExportPanel.tsx) : distinct de l'effet
  // de chargement initial ci-dessous, pour ne pas courir le risque de
  // ré-exécuter la garde de démontage à chaque changement de `pipelineId`.
  useEffect(
    () => () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  async function loadRuns() {
    try {
      const latest = await client.getPipelineRuns(pipelineId);
      if (!mountedRef.current) return;
      setRuns(latest);
      onLatestRunChange?.(latest[0] ?? null);
    } catch {
      // Un chargement initial en échec restait silencieux (liste vide
      // indiscernable d'un « aucune exécution » légitime) — même défaut que
      // celui corrigé dans ReportRunPanel (SP-17b) ; on réutilise runError,
      // déjà rendu dans ce composant.
      if (!mountedRef.current) return;
      setRunError("Impossible de charger l'historique des exécutions.");
    }
  }

  useEffect(() => {
    void loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  async function poll() {
    for (;;) {
      if (!mountedRef.current) return;
      const latest = await client.getPipelineRuns(pipelineId);
      if (!mountedRef.current) return;
      setRuns(latest);
      onLatestRunChange?.(latest[0] ?? null);
      const status = latest[0]?.status;
      if (status !== "queued" && status !== "running") {
        setRunning(false);
        return;
      }
      await new Promise<void>((resolve) => {
        timerRef.current = setTimeout(resolve, 1500);
      });
      if (!mountedRef.current) return;
    }
  }

  async function onRun() {
    setRunning(true);
    setRunError(null);
    try {
      await client.runPipeline(pipelineId);
      await poll();
    } catch (e) {
      if (!mountedRef.current) return;
      setRunError(e instanceof Error ? e.message : "Échec du lancement du pipeline.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" onClick={() => void onRun()} disabled={running}>
        {running ? "Exécution…" : "Exécuter"}
      </Button>
      {runError && (
        <p role="alert" className="text-xs text-danger">
          {runError}
        </p>
      )}
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <li key={run.id} className="border-t border-rule pt-1">
            <span>{STATUS_LABEL[run.status]}</span>
            {run.startedAt && <span className="ml-2 text-ink-2">{run.startedAt}</span>}
            {run.error && (
              <p role="alert" className="text-danger">
                {run.error}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
