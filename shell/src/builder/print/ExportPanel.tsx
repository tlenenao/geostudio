// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { ExportFormat, ExportJob } from "../../api/types";
import { Button } from "../../ui/button";
import { Dialog } from "../../ui/dialog";

const POLL_INTERVAL_MS = 1500;
// Fix round (finding I7) : ni PipelineRunPanel ni ImportFileButton (les deux
// autres implémentations de ce patron de poll) n'ont de plafond — mais un
// job d'export peut rester bloqué "running" pour de bon si export-worker
// (Chromium) crashe en cours de rendu (OOM notamment), et il n'existe encore
// aucun balayage de reclaim côté serveur pour ce cas précis (cf.
// app/export/repository.py::reclaim_stuck_jobs, TODO périodicité). Sans
// plafond ici, l'onglet du navigateur pollerait toutes les 1.5s pour
// toujours. 200 tentatives × 1.5s = 5 minutes, un budget large pour un rendu
// Playwright réel mais fini.
const MAX_POLL_ATTEMPTS = 200;

// Patron de poll identique à PipelineRunPanel (SP-15a) / ImportFileButton
// (SP-6a) : boucle récursive manuelle via le client, jamais un
// refetchInterval react-query (cf. plan Global Constraints). Garde de
// montage supplémentaire par rapport à ces deux précédents : ce panneau
// peut être démonté pendant qu'un poll est en vol (fermeture de page,
// navigation), donc chaque `setState` après un `await` est gardé par
// `mountedRef`, et le timer en attente est explicitement annulé au
// démontage pour ne rien laisser en suspens.
export function ExportPanel({ itemId }: { itemId: string }) {
  const client = useItemClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  async function poll(jobId: string, attempt = 0): Promise<void> {
    if (!mountedRef.current) return;
    const latest = await client.getExportJob(jobId);
    if (!mountedRef.current) return;
    setJob(latest);
    if (latest.status !== "pending" && latest.status !== "running") return;
    if (attempt + 1 >= MAX_POLL_ATTEMPTS) {
      setError("Export toujours en cours, réessayer plus tard.");
      return;
    }
    await new Promise<void>((resolve) => {
      timerRef.current = setTimeout(resolve, POLL_INTERVAL_MS);
    });
    if (!mountedRef.current) return;
    await poll(jobId, attempt + 1);
  }

  async function onExport(format: ExportFormat) {
    setDialogOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createExport(itemId, format);
      await poll(jobId);
    } catch {
      // Message générique volontaire : ne pas répéter le texte brut d'une
      // erreur réseau/HTTP (potentiellement peu lisible) que ce soit
      // `createExport` ou une itération de `poll` qui a échoué — les deux
      // remontent ici via le même try/catch.
      if (mountedRef.current) setError("Échec de l'export.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" variant="outline" onClick={() => setDialogOpen(true)} disabled={running}>
        Exporter
      </Button>
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="Choisir le format d'export">
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onExport("png")}>
            PNG
          </Button>
          <Button type="button" size="sm" onClick={() => onExport("pdf")}>
            PDF
          </Button>
        </div>
      </Dialog>
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-blue-600 underline">
          Télécharger l&apos;export
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert" className="text-sm text-red-600">
          {error ?? job?.error ?? "Échec de l'export."}
        </p>
      )}
    </div>
  );
}
