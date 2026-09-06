// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { ExportFormat, ExportJob } from "../../api/types";
import { t } from "../../i18n";
import { Button } from "../../ui/kit/Button";
import { Panel } from "../../ui/kit/Panel";
import { usePanelTrigger } from "../../ui/kit/usePanelTrigger";

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
  const [pickerOpen, setPickerOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exportPanel = usePanelTrigger(pickerOpen);

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
      setError(t("exportPanel.stillRunning"));
      return;
    }
    await new Promise<void>((resolve) => {
      timerRef.current = setTimeout(resolve, POLL_INTERVAL_MS);
    });
    if (!mountedRef.current) return;
    await poll(jobId, attempt + 1);
  }

  async function onExport(format: ExportFormat) {
    setPickerOpen(false);
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
      if (mountedRef.current) setError(t("exportPanel.exportFailed"));
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        size="sm"
        variant="outline"
        {...exportPanel.triggerProps}
        onClick={() => setPickerOpen((open) => !open)}
        disabled={running}
      >
        {t("exportPanel.exportButton")}
      </Button>
      {pickerOpen && (
        // Panneau en ligne, pas une fenêtre modale (spec §2.1, ConfirmDialog
        // seul survit) : pas d'Escape/backdrop à intercepter, Annuler ferme
        // explicitement sans exporter.
        // Panel (ui/kit) ne transmet ni id ni role (props non déclarées) —
        // le wrapper neutre porte seulement id (pas role="region" du hook) :
        // ce wrapper n'a pas de nom accessible (revue finale SP-43, Minor
        // M1) — un role="region" sans étiquette est pire qu'une absence de
        // région pour un lecteur d'écran ; même patron que les 5 autres
        // sites corrigés par la Tâche 7 pour la même raison.
        <div id={exportPanel.panelId}>
          <Panel className="flex flex-col gap-2">
            <p className="text-sm font-medium text-ink">{t("exportPanel.chooseFormatHeading")}</p>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPickerOpen(false)}
              >
                {t("exportPanel.cancel")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void onExport("png")}
              >
                PNG
              </Button>
              <Button type="button" size="sm" onClick={() => void onExport("pdf")}>
                PDF
              </Button>
            </div>
          </Panel>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-accent underline">
          {t("exportPanel.downloadExport")}
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert" className="text-sm text-danger">
          {error ?? job?.error ?? t("exportPanel.exportFailed")}
        </p>
      )}
    </div>
  );
}
