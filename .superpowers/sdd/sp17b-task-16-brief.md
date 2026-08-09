## Task 16: `ReportRunPanel.tsx`

**Files:**
- Create: `shell/src/builder/report/ReportRunPanel.tsx`

**Interfaces:**
- Consumes: `useItemClient()` (existing), `client.getReportRuns(pk)` (Task 14).
- Produces: `ReportRunPanel({ reportId }: { reportId: string })` — read-only poll panel, no "Exécuter" button (reports are sweep-triggered only, never manually run).

- [ ] **Step 1: Write the component**

```tsx
// shell/src/builder/report/ReportRunPanel.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ReportRunStatus } from "../../api/types";

const STATUS_LABEL: Record<ReportRunStatus["status"], string> = {
  pending: "En attente", running: "En cours", done: "Terminé",
  error: "Échec", unknown: "Inconnu",
};

// Read-only history — mirrors PipelineRunPanel's poll loop (same 1500ms
// pattern as ImportFileButton) minus the "Exécuter" button: a ReportSchedule
// is only ever triggered by sweep_report_schedules_task's cron, never
// manually, so there is nothing for a button here to defer.
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
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/builder/report/ReportRunPanel.tsx
git commit -m "feat(shell): ReportRunPanel — read-only run history poll (SP-17b)"
```

---

