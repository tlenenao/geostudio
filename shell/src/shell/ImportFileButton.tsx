// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient, useMe } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { t } from "../i18n";

type Phase = "form" | "uploading" | "selecting-layer" | "selecting-latlon" | "polling" | "error";
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
  return (
    lower.endsWith(".gpkg") ||
    lower.endsWith(".zip") ||
    lower.endsWith(".kml") ||
    lower.endsWith(".kmz")
  );
}

// XLSX est un format binaire (zip) : impossible de sniffer les en-têtes
// côté navigateur comme pour le CSV (FileReader.readAsText) — l'inspection
// passe par POST /uploads/inspect (InspectResponse.fields), après upload,
// comme le flux "couches" ci-dessus, mais avec une forme de réponse et une
// suite différentes (colonnes lat/lon, pas un choix de couche).
function needsFieldInspection(filename: string): boolean {
  return filename.toLowerCase().endsWith(".xlsx");
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
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );
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
      if (!mountedRef.current) return;
      const job = await client.getIngestionJob(jobId);
      if (!mountedRef.current) return;
      if (job.status === "done" && job.itemId) {
        close();
        navigate(`/maps/${job.itemId}`);
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? t("importFile.genericError"));
        return;
      }
      await new Promise<void>((resolve) => {
        timerRef.current = setTimeout(resolve, 1500);
      });
      if (!mountedRef.current) return;
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
      if (needsFieldInspection(file.name)) {
        const { fields } = await client.inspectUpload({ key, filename: file.name });
        if (!detectLatLon(fields ?? [])) {
          setUploadedKey(key);
          setCsvHeaders(fields ?? []);
          setPhase("selecting-latlon");
          return;
        }
        await startJob(key, undefined);
        return;
      }
      await startJob(key, undefined);
    } catch {
      if (!mountedRef.current) return;
      setPhase("error");
      setError(t("importFile.genericError"));
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
      if (!mountedRef.current) return;
      setPhase("error");
      setError(t("importFile.genericError"));
    }
  }

  async function confirmLatLon(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadedKey || !latField || !lonField) return;
    setPhase("uploading");
    setError("");
    try {
      // needsManualLatLon (csvHeaders !== null) est vrai ici : startJob lit
      // latField/lonField depuis l'état, pas un paramètre dédié — même
      // mécanique que le formulaire CSV manuel (Fichier déjà uploadé, pas
      // de layerName pour ce format).
      await startJob(uploadedKey, undefined);
    } catch {
      if (!mountedRef.current) return;
      setPhase("error");
      setError(t("importFile.genericError"));
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  // Fermer pendant un upload/un balayage en vol laisserait la chaîne async
  // (submit()/confirmLayer()/confirmLatLon()/poll()) tourner en arrière-plan
  // — même patron que Tileset3DUploadButton.requestClose() : ignore Échap et
  // le pointerdown extérieur (les deux passent par onOpenChange de Drawer)
  // tant que busy, en plus du disabled={busy} explicite sur Annuler.
  function requestClose() {
    if (busy) return;
    close();
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        {...drawerPanel.triggerProps}
        onClick={() => setOpen(true)}
      >
        {t("importFile.button")}
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => !next && requestClose()}
        title={t("importFile.button")}
        id={drawerPanel.panelId}
      >
        {phase === "selecting-latlon" ? (
          <form onSubmit={(e) => void confirmLatLon(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("importFile.latColumn")}
              <select
                aria-label={t("importFile.latColumn")}
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
              {t("importFile.lonColumn")}
              <select
                aria-label={t("importFile.lonColumn")}
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
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                {t("confirmDialog.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={!latField || !lonField}>
                {t("importFile.continueButton")}
              </Button>
            </div>
          </form>
        ) : phase === "selecting-layer" ? (
          <form onSubmit={(e) => void confirmLayer(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("importFile.layerColumn")}
              <select
                aria-label={t("importFile.layerColumn")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={layerName}
                onChange={(e) => setLayerName(e.target.value)}
              >
                <option value="">—</option>
                {layers.map((l) => (
                  <option key={l.name} value={l.name}>
                    {t("importFile.layerOptionTemplate", { name: l.name, count: l.featureCount })}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                {t("confirmDialog.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={!layerName}>
                {t("importFile.continueButton")}
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("importFile.fileToImport")}
              <input
                aria-label={t("importFile.fileToImport")}
                type="file"
                accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet"
                onChange={(e) => void onFileChange(e)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("importFile.collectionTitleLabel")}
              <Input
                aria-label={t("importFile.collectionTitleLabel")}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            {needsManualLatLon && (
              <>
                <label className="flex flex-col gap-1 text-sm text-ink">
                  {t("importFile.latColumn")}
                  <select
                    aria-label={t("importFile.latColumn")}
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
                  {t("importFile.lonColumn")}
                  <select
                    aria-label={t("importFile.lonColumn")}
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
              <Button type="button" variant="outline" size="sm" onClick={close} disabled={busy}>
                {t("confirmDialog.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={busy}>
                {phase === "uploading"
                  ? t("importFile.uploading")
                  : phase === "polling"
                    ? t("importFile.importing")
                    : t("importFile.submit")}
              </Button>
            </div>
          </form>
        )}
      </Drawer>
    </>
  );
}
