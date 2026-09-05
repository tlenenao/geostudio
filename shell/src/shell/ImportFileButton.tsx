// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient, useMe } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";

type Phase = "form" | "uploading" | "selecting-layer" | "polling" | "error";
type LayerInfo = { name: string; featureCount: number; geometryType: string };

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

function isLayeredFormat(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith(".gpkg") || lower.endsWith(".zip");
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const drawerPanel = usePanelTrigger(open);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [uploadedKey, setUploadedKey] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [layerName, setLayerName] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();
  const navigate = useNavigate();
  // SP-42/F-shell-pages-01 (fusion F-shell-pages-02) : cf. commentaire
  // jumeau sur NewItemButton.tsx — même mécanisme, même TopBar. Un import
  // aboutit toujours à POST /uploads (core/app/ingestion/routes.py),
  // gardé par data.manage — jamais maps.manage, bien que la navigation
  // finale ouvre /maps/{itemId} : la collection PostGIS créée par le
  // worker est la ressource dont l'écriture compte ici, pas l'item Map.
  const meQuery = useMe();
  const privileges = meQuery.data?.privileges;
  const canImport = privileges === undefined || privileges.includes("data.manage");

  if (!canImport) return null;

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setCsvHeaders(null);
    setLatField("");
    setLonField("");
    setUploadedKey(null);
    setLayers([]);
    setLayerName("");
    setPhase("form");
    setError("");
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setCsvHeaders(null);
    if (f && f.name.toLowerCase().endsWith(".csv")) {
      const blob = f.slice(0, 4096);
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => resolve("");
        reader.readAsText(blob);
      });
      const firstLine = text.split(/\r?\n/)[0] ?? "";
      const headers = firstLine.split(",").map((h) => h.trim());
      if (!detectLatLon(headers)) setCsvHeaders(headers);
    }
  }

  const needsManualLatLon = csvHeaders !== null;

  async function poll(jobId: string) {
    for (;;) {
      const job = await client.getIngestionJob(jobId);
      if (job.status === "done" && job.itemId) {
        close();
        navigate(`/maps/${job.itemId}`);
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de l'import.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function startJob(key: string, chosenLayerName: string | undefined) {
    const { jobId } = await client.createIngestionJob({
      key,
      filename: file!.name,
      collectionTitle: title.trim(),
      latField: needsManualLatLon ? latField : undefined,
      lonField: needsManualLatLon ? lonField : undefined,
      layerName: chosenLayerName,
    });
    setPhase("polling");
    await poll(jobId);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    if (needsManualLatLon && (!latField || !lonField)) return;
    setPhase("uploading");
    setError("");
    try {
      const { uploadUrl, key } = await client.presignUpload(
        file.name,
        file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      if (isLayeredFormat(file.name)) {
        const { layers: found } = await client.inspectUpload({ key, filename: file.name });
        if (found.length > 1) {
          setUploadedKey(key);
          setLayers(found);
          setPhase("selecting-layer");
          return;
        }
        await startJob(key, found[0]?.name);
        return;
      }
      await startJob(key, undefined);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  async function confirmLayer(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadedKey || !layerName) return;
    setPhase("uploading");
    setError("");
    try {
      await startJob(uploadedKey, layerName);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        {...drawerPanel.triggerProps}
        onClick={() => setOpen(true)}
      >
        Importer un fichier
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => !next && close()}
        title="Importer un fichier"
        id={drawerPanel.panelId}
      >
        {phase === "selecting-layer" ? (
          <form onSubmit={(e) => void confirmLayer(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Couche à importer
              <select
                aria-label="Couche à importer"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={layerName}
                onChange={(e) => setLayerName(e.target.value)}
              >
                <option value="">—</option>
                {layers.map((l) => (
                  <option key={l.name} value={l.name}>
                    {l.name} ({l.featureCount} entités)
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={!layerName}>
                Continuer
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Fichier à importer
              <input
                aria-label="Fichier à importer"
                type="file"
                accept=".geojson,.json,.csv,.gpkg,.zip"
                onChange={(e) => void onFileChange(e)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-ink">
              Titre de la collection
              <Input
                aria-label="Titre de la collection"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            {needsManualLatLon && (
              <>
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Colonne latitude
                  <select
                    aria-label="Colonne latitude"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={latField}
                    onChange={(e) => setLatField(e.target.value)}
                  >
                    <option value="">—</option>
                    {csvHeaders!.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Colonne longitude
                  <select
                    aria-label="Colonne longitude"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={lonField}
                    onChange={(e) => setLonField(e.target.value)}
                  >
                    <option value="">—</option>
                    {csvHeaders!.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {phase === "error" && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={busy}>
                {phase === "uploading"
                  ? "Envoi…"
                  : phase === "polling"
                    ? "Import en cours…"
                    : "Importer"}
              </Button>
            </div>
          </form>
        )}
      </Drawer>
    </>
  );
}
