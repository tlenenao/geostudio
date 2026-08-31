// SPDX-License-Identifier: Apache-2.0
// Même patron de poll que shell/src/builder/print/ExportPanel.tsx (SP-17a) :
// boucle récursive manuelle via le client, jamais un refetchInterval
// react-query — cf. plan Global Constraints (superpowers writing-plans).
// Même patron de panneau en ligne qu'ExportPanel/Terrain3DUploadButton
// (SP-30c) : pas de fenêtre modale, bouton déclencheur désactivé pendant
// l'envoi (busy guard — SP-30c a trouvé cette garde absente sur l'un des
// deux composants convertis, revue finale de branche, fix vérifié depuis).
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AppConfig, AppExportJobStatus, AppExportMode } from "../../api/types";
import { Button } from "../../ui/kit/Button";
import { Panel } from "../../ui/kit/Panel";
import { collectWidgetTypes, WRITE_CAPABLE_WIDGET_TYPES } from "./collectWidgetTypes";

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 200;

export function AppExportPanel({ itemId, config }: { itemId: string; config: AppConfig }) {
  const client = useItemClient();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [job, setJob] = useState<AppExportJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [pendingWarningMode, setPendingWarningMode] = useState<AppExportMode | null>(null);
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
    const latest = await client.getAppExportJob(itemId, jobId);
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

  async function runExport(mode: AppExportMode) {
    setPendingWarningMode(null);
    setPickerOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createAppExport(itemId, mode);
      await poll(jobId);
    } catch {
      if (mountedRef.current) setError("Échec de l'export.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  // Le choix de mode ne déclenche l'export réel que si la config ne
  // contient aucun widget d'écriture (formulaire) — sinon on bloque sur un
  // avertissement explicite, franchissable seulement par un second clic
  // conscient ("Exporter quand même").
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) =>
      WRITE_CAPABLE_WIDGET_TYPES.has(t),
    );
    if (hasWriteWidget) {
      setPickerOpen(false);
      setPendingWarningMode(mode);
      return;
    }
    void runExport(mode);
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        size="sm"
        variant="outline"
        onClick={() => setPickerOpen((open) => !open)}
        disabled={running}
      >
        Exporter
      </Button>
      {pickerOpen && (
        // Panneau en ligne, pas une fenêtre modale (spec §2.1, ConfirmDialog
        // seul survit) : pas d'Escape/backdrop à intercepter, Fermer ferme
        // explicitement sans exporter.
        <Panel className="flex flex-col gap-2">
          <p className="text-sm font-medium text-ink">Choisir le mode d'export</p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(false)}>
              Fermer
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
              Statique
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
              Connecté
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("standalone")}>
              Autoporté
            </Button>
          </div>
        </Panel>
      )}
      {pendingWarningMode && (
        <div
          role="alert"
          className="rounded border border-warn-soft bg-warn-soft p-2 text-sm text-warn"
        >
          <p>
            Cette app contient un widget Formulaire — toute écriture sera désactivée dans
            l&apos;export faute de session authentifiée.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => void runExport(pendingWarningMode)}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPendingWarningMode(null)}>
              Ne pas exporter
            </Button>
          </div>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-accent underline">
          Télécharger le bundle
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert" className="text-sm text-danger">
          {error ?? job?.error ?? "Échec de l'export."}
        </p>
      )}
    </div>
  );
}
