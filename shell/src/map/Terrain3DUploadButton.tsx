// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";

const DEFAULT_POLL_INTERVAL_MS = 1500;
// Un job de conversion qui n'atteint jamais un état terminal ne doit pas
// laisser le panneau définitivement infermable — même garde-fou que
// Tileset3DUploadButton (design tileset3d hosting, leçon Task 12/I3).
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

type Phase = "form" | "uploading" | "converting" | "error";

// pollIntervalMs is injectable for tests only (this file's suite is
// MSW-based with real timers, where fake timers would fight userEvent's
// own scheduler) — mirrors Tileset3DUploadButton's pollTimeoutMs param.
export function Terrain3DUploadButton({
  onUploaded,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: {
  onUploaded: (itemId: string) => void;
  pollIntervalMs?: number;
}) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
  }

  async function poll(jobId: string) {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    for (;;) {
      const job = await client.getTerrain3DUploadJob(jobId);
      if (job.status === "done" && job.itemId) {
        onUploaded(job.itemId);
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la conversion du DEM.");
        return;
      }
      if (Date.now() >= deadline) {
        setPhase("error");
        setError("La conversion du DEM prend trop de temps. Réessayez plus tard.");
        return;
      }
      await new Promise((r) => setTimeout(r, pollIntervalMs));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      // Route dédiée (jamais presignUpload générique) : elle signe dans le
      // bucket terrain3d, le seul que le worker de conversion lit. Le type
      // est celui que le navigateur enverra réellement — fetch(PUT, body:
      // File) envoie File.type, et un type signé différent fait échouer S3
      // en 403 SignatureDoesNotMatch (même traitement qu'ImportFileButton).
      const { uploadUrl, key } = await client.presignTerrain3DUpload(
        file.name,
        file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      setPhase("converting");
      const { jobId } = await client.createTerrain3DUpload({
        key,
        filename: file.name,
        title: title.trim(),
      });
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du DEM.");
    }
  }

  const busy = phase === "uploading" || phase === "converting";

  // Le déclencheur ouvre/ferme le même panneau que le bouton Annuler, avec
  // les mêmes garanties (finding I1, revue finale SP-30c) : désactivé
  // pendant l'envoi/la conversion (sinon un clic masquerait le panneau
  // pendant que submit()/poll() tournent encore en arrière-plan, sans rien
  // pour refléter leur succès ou leur échec) et, à la fermeture, réinitialise
  // intégralement l'état (comme close()) plutôt qu'un simple setOpen(false)
  // qui laisserait une erreur ou un brouillon périmés visibles à la
  // réouverture.
  function toggle() {
    if (busy) return;
    if (open) {
      close();
    } else {
      setOpen(true);
    }
  }

  // Panneau en ligne, pas une fenêtre modale (spec §2.1) : plus d'Escape ni
  // de backdrop à intercepter. Le bouton Annuler ferme lui aussi, et reste
  // désactivé pendant l'envoi/la conversion — fermer laisserait submit()/
  // poll() tourner en arrière-plan sans rien pour le refléter.
  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" variant="outline" className="w-fit" onClick={toggle} disabled={busy}>
        Nouveau DEM
      </Button>
      {open && (
        <Panel className="flex flex-col gap-3">
          <h4 className="text-sm font-semibold text-ink">Nouveau DEM</h4>
          <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Fichier DEM (GeoTIFF)
              <input
                aria-label="Fichier DEM (GeoTIFF)"
                type="file"
                accept=".tif,.tiff"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-ink">
              Titre
              <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            {phase === "uploading" && <p className="text-sm text-ink-2">Envoi du fichier…</p>}
            {phase === "converting" && <p className="text-sm text-ink-2">Conversion en COG…</p>}
            {phase === "error" && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close} disabled={busy}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={busy || !file || !title.trim()}>
                {busy ? "Envoi…" : "Importer"}
              </Button>
            </div>
          </form>
        </Panel>
      )}
    </div>
  );
}
