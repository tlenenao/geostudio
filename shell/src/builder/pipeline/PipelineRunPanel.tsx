// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { PipelineRun } from "../../api/types";
import { Button } from "../../ui/button";

const STATUS_LABEL: Record<PipelineRun["status"], string> = {
  queued: "En attente", running: "En cours", succeeded: "succeeded", failed: "failed",
};

// Patron de poll identique à shell/src/shell/ImportFileButton.tsx (SP-6a) —
// boucle récursive manuelle via le client, pas un refetchInterval react-query
// (cf. plan Global Constraints).
export function PipelineRunPanel({ pipelineId }: { pipelineId: string }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function loadRuns() {
    setRuns(await client.getPipelineRuns(pipelineId));
  }

  useEffect(() => {
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  async function poll() {
    for (;;) {
      const latest = await client.getPipelineRuns(pipelineId);
      setRuns(latest);
      const status = latest[0]?.status;
      if (status !== "queued" && status !== "running") {
        setRunning(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function onRun() {
    setRunning(true);
    setRunError(null);
    try {
      await client.runPipeline(pipelineId);
      await poll();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Échec du lancement du pipeline.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" onClick={onRun} disabled={running}>
        {running ? "Exécution…" : "Exécuter"}
      </Button>
      {runError && <p role="alert" className="text-red-600 text-xs">{runError}</p>}
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <li key={run.id} className="border-t border-slate-200 pt-1">
            <span>{STATUS_LABEL[run.status]}</span>
            {run.startedAt && <span className="ml-2 text-slate-500">{run.startedAt}</span>}
            {run.error && <p role="alert" className="text-red-600">{run.error}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
