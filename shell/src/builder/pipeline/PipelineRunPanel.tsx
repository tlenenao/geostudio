// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import { ApiError } from "../../api/ApiError";
import type { PipelineRun } from "../../api/types";
import { t } from "../../i18n";
import { jobStatusLabel } from "../../lib/jobStatusLabel";
import { Button } from "../../ui/kit/Button";
import { usePanelTrigger } from "../../ui/kit/usePanelTrigger";
import { formatDateTime } from "../../lib/format";
import "../../i18n/domains/automation";

// GET /pipelines/{id}/runs pagine déjà côté cœur (limit/offset, SP-50) mais ce
// panneau tronquait silencieusement l'historique à la limite par défaut du
// cœur (100) sans jamais l'envoyer ni exposer de contrôle.
const RUNS_PAGE_SIZE = 100;

function formatDuration(startedAt: string | null, finishedAt: string | null): string | null {
  if (!startedAt || !finishedAt) return null;
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds} s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} min ${seconds} s`;
}

// SP-B10d : pas de champ completed_nodes/total_nodes exposé par le cœur sur
// l'objet de run (RunStatus, core/app/pipelines/routes.py) — nodeStats est en
// revanche déjà rempli nœud par nœud PENDANT l'exécution (append_node_stat,
// core/app/pipelines/repository.py, commentaire SP-15g §3.5), donc
// Object.keys(run.nodeStats).length est un décompte réel de nœuds terminés,
// pas une valeur inventée. Le total (M) n'existe que côté définition du
// pipeline (PipelinePayload.nodes), jamais sur le run : `totalNodes` est donc
// une prop optionnelle fournie par l'appelant qui connaît cette définition
// (PipelineBuilderPage, via `draft.nodes.length`) plutôt qu'un champ lu sur
// `run`.
function RunRow({
  run,
  totalNodes,
  onCancel,
}: {
  run: PipelineRun;
  totalNodes?: number;
  onCancel?: (runId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const detail = usePanelTrigger(open);
  const nodeEntries = Object.values(run.nodeStats);
  const showNodeProgress = run.status === "running" && totalNodes !== undefined && totalNodes > 0;
  const active = run.status === "queued" || run.status === "running";
  // t03b-009 : l'écrivain publie sa progression par lot dans nodeStats.
  const lastStat = nodeEntries[nodeEntries.length - 1];
  return (
    <li className="border-t border-rule pt-1">
      <div className="flex items-center gap-2">
        <span>{jobStatusLabel(run.status)}</span>
        {showNodeProgress && (
          <span className="text-ink-2">
            {t("pipelineRun.nodeProgress", { completed: nodeEntries.length, total: totalNodes })}
          </span>
        )}
        {(active || run.status === "cancel_requested") && lastStat?.rowCount != null && (
          <span className="text-ink-2">
            {t("pipelineRun.rowsProgress", { rows: lastStat.rowCount })}
          </span>
        )}
        {active && onCancel && (
          <button type="button" className="text-danger underline" onClick={() => onCancel(run.id)}>
            {t("pipelineRun.cancelButton")}
          </button>
        )}
        {run.startedAt && <span className="text-ink-2">{formatDateTime(run.startedAt)}</span>}
        {formatDuration(run.startedAt, run.finishedAt) && (
          <span className="text-ink-2">{formatDuration(run.startedAt, run.finishedAt)}</span>
        )}
        {nodeEntries.length > 0 && (
          <button
            type="button"
            aria-label={t("pipelineRun.detailAria", { id: run.id })}
            aria-expanded={detail.triggerProps["aria-expanded"]}
            aria-controls={detail.triggerProps["aria-controls"]}
            className="text-accent underline"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? t("pipelineRun.hideDetail") : t("pipelineRun.showDetail")}
          </button>
        )}
      </div>
      {run.error && (
        <p role="alert" className="text-danger">
          {run.error}
        </p>
      )}
      {open && nodeEntries.length > 0 && (
        <ul {...detail.panelProps} className="ml-4 mt-1 flex flex-col gap-0.5 text-ink-2">
          {nodeEntries.map((stat) => (
            <li key={stat.nodeId}>
              {stat.op} : {stat.rowCount ?? "—"}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// Patron de poll identique à shell/src/shell/ImportFileButton.tsx (SP-6a) —
// boucle récursive manuelle via le client, pas un refetchInterval react-query
// (cf. plan Global Constraints).
export function PipelineRunPanel({
  pipelineId,
  onLatestRunChange,
  totalNodes,
}: {
  pipelineId: string;
  onLatestRunChange?: (run: PipelineRun | null) => void;
  // Nombre de nœuds de la définition courante du pipeline (cf. commentaire
  // sur RunRow) : optionnel, omis par les appelants qui ne l'ont pas sous la
  // main (ex. VisualQueryWizardPage) — la progression N/M ne s'affiche
  // simplement pas dans ce cas, additif.
  totalNodes?: number;
}) {
  const client = useItemClient();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [limit, setLimit] = useState(RUNS_PAGE_SIZE);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Lu par poll() (lancé une seule fois par exécution) pour refléter la
  // limite la plus récente sans reconstruire toute la boucle de sondage à
  // chaque clic sur "Charger plus".
  const limitRef = useRef(limit);
  limitRef.current = limit;

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
      const latest = await client.getPipelineRuns(pipelineId, { limit });
      if (!mountedRef.current) return;
      setRuns(latest);
      onLatestRunChange?.(latest[0] ?? null);
    } catch {
      // Un chargement initial en échec restait silencieux (liste vide
      // indiscernable d'un « aucune exécution » légitime) — même défaut que
      // celui corrigé dans ReportRunPanel (SP-17b) ; on réutilise runError,
      // déjà rendu dans ce composant.
      if (!mountedRef.current) return;
      setRunError(t("pipelineRun.loadRunsFailed"));
    }
  }

  useEffect(() => {
    void loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId, limit]);

  async function poll() {
    for (;;) {
      if (!mountedRef.current) return;
      const latest = await client.getPipelineRuns(pipelineId, { limit: limitRef.current });
      if (!mountedRef.current) return;
      setRuns(latest);
      onLatestRunChange?.(latest[0] ?? null);
      const status = latest[0]?.status;
      if (status !== "queued" && status !== "running" && status !== "cancel_requested") {
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
      if (e instanceof ApiError && e.status === 409) {
        // REV-310 : un run est déjà actif — on le suit au lieu de laisser l'écran figé.
        setRunError(t("pipelineRun.alreadyRunning"));
        await poll();
        return;
      }
      setRunError(e instanceof Error ? e.message : t("pipelineRun.runFailed"));
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  async function onCancel(runId: string) {
    setRunError(null);
    try {
      await client.cancelPipelineRun?.(pipelineId, runId);
      await loadRuns();
    } catch {
      if (mountedRef.current) setRunError(t("pipelineRun.cancelFailed"));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" onClick={() => void onRun()} disabled={running}>
        {running ? t("pipelineRun.running") : t("pipelineRun.runButton")}
      </Button>
      {runError && (
        <p role="alert" className="text-xs text-danger">
          {runError}
        </p>
      )}
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <RunRow
            key={run.id}
            run={run}
            totalNodes={totalNodes}
            onCancel={client.cancelPipelineRun ? (id) => void onCancel(id) : undefined}
          />
        ))}
      </ul>
      {runs.length >= limit && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => setLimit((l) => l + RUNS_PAGE_SIZE)}
        >
          {t("pipelineRun.loadMore")}
        </Button>
      )}
    </div>
  );
}
