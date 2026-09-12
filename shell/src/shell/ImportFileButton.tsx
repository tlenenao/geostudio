// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient, useMe } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { t } from "../i18n";

type Phase = "form" | "uploading" | "selecting-layer" | "selecting-geometry" | "polling" | "error";
type LayerInfo = { name: string; featureCount: number; geometryType: string };
type GeometryChoice = "latlon" | "wkt" | "none";
type GeometryOverride = {
  latField?: string;
  lonField?: string;
  wktField?: string;
  geometryMode?: GeometryChoice;
};

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

// Formats "couches natives" : la géométrie est déjà portée par le format
// lui-même (GDAL/pyogrio) — un choix de couche (s'il y en a plusieurs)
// suffit, jamais de second appel d'inspection après ce choix.
function isLayeredFormat(filename: string): boolean {
  const lower = filename.toLowerCase();
  return (
    lower.endsWith(".gpkg") ||
    lower.endsWith(".zip") ||
    lower.endsWith(".kml") ||
    lower.endsWith(".kmz") ||
    lower.endsWith(".gml")
  );
}

// XLSX est le seul format "à feuilles" qui n'est PAS géométrie-natif : une
// feuille est une table quelconque, pas une couche GDAL. Un classeur
// mono-feuille renvoie déjà layers=[]/fields=[...] en un seul appel
// (core/app/ingestion/routes.py::inspect_upload) ; un classeur
// multi-feuilles renvoie d'abord layers=[...]/fields=null (choix de
// feuille), PUIS exige un second appel POST /uploads/inspect avec
// layerName pour obtenir les champs de la feuille choisie.
function isTabularSheetFormat(filename: string): boolean {
  return filename.toLowerCase().endsWith(".xlsx");
}

// Ces formats sont binaires (parquet) ou n'ont pas d'en-tête sniffable côté
// navigateur comme le CSV (FileReader.readAsText) — l'inspection passe par
// POST /uploads/inspect (InspectResponse.fields), après upload. GeoParquet
// déjà géo-référencé renvoie fields=null (sentinelle) : voir
// inspectFieldsThenProceed().
function needsFieldInspection(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith(".jsonl") || lower.endsWith(".xml") || lower.endsWith(".parquet");
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const drawerPanel = usePanelTrigger(open);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [geometryChoice, setGeometryChoice] = useState<GeometryChoice>("latlon");
  const [wktField, setWktField] = useState("");
  const [uploadedKey, setUploadedKey] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [layerName, setLayerName] = useState("");
  // La feuille XLSX choisie en selecting-layer doit survivre jusqu'au job
  // final si la feuille exige elle-même un choix de géométrie (selecting-
  // geometry) — startJob()/confirmGeometry() en ont besoin, pas seulement
  // confirmLayer().
  const [pendingLayerName, setPendingLayerName] = useState<string | undefined>(undefined);
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
    setGeometryChoice("latlon");
    setWktField("");
    setUploadedKey(null);
    setLayers([]);
    setLayerName("");
    setPendingLayerName(undefined);
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
      if (job.status === "done") {
        close();
        // GAP-29 : une collection sans géométrie (geometryMode="none") n'a
        // pas de Map associée (core/app/ingestion/importer.py) — itemId
        // est alors null, il n'y a rien à ouvrir sous /maps/{itemId}.
        navigate(job.itemId ? `/maps/${job.itemId}` : "/admin/collections");
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

  async function startJob(
    key: string,
    chosenLayerName: string | undefined,
    geometryOverride?: GeometryOverride,
  ) {
    const geometryPayload: GeometryOverride =
      geometryOverride ?? (needsManualLatLon ? { latField, lonField } : {});
    const { jobId } = await client.createIngestionJob({
      key,
      filename: file!.name,
      collectionTitle: title.trim(),
      layerName: chosenLayerName,
      ...geometryPayload,
    });
    setPhase("polling");
    await poll(jobId);
  }

  // GAP-29 : point de passage commun entre le flux mono-appel (JSON
  // Lines/XML/GeoParquet/XLSX mono-feuille) et le second appel du flux
  // XLSX multi-feuilles (confirmLayer) — décide, à partir des champs
  // inspectés, s'il faut ouvrir le sélecteur de géométrie à 3 options ou
  // démarrer le job directement.
  async function inspectFieldsThenProceed(
    key: string,
    chosenLayerName: string | undefined,
    fields: string[] | null,
  ) {
    // GeoParquet déjà géo-référencé : fields=null est une sentinelle
    // distincte de "en-têtes vides", posée par le cœur
    // (_is_geoparquet_from_bytes) — jamais d'étape de géométrie dans ce cas.
    if (fields === null) {
      await startJob(key, chosenLayerName);
      return;
    }
    if (!detectLatLon(fields)) {
      setUploadedKey(key);
      setCsvHeaders(fields);
      setGeometryChoice("latlon");
      setWktField("");
      setPendingLayerName(chosenLayerName);
      setPhase("selecting-geometry");
      return;
    }
    await startJob(key, chosenLayerName);
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
      if (isTabularSheetFormat(file.name)) {
        const { layers: found, fields } = await client.inspectUpload({ key, filename: file.name });
        if (found.length > 1) {
          setUploadedKey(key);
          setLayers(found);
          setPhase("selecting-layer");
          return;
        }
        await inspectFieldsThenProceed(key, undefined, fields ?? null);
        return;
      }
      if (needsFieldInspection(file.name)) {
        const { fields } = await client.inspectUpload({ key, filename: file.name });
        await inspectFieldsThenProceed(key, undefined, fields ?? null);
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
      // XLSX : la géométrie n'est jamais native à la feuille — un second
      // appel d'inspection, scopé à la feuille choisie, est nécessaire pour
      // savoir si ses colonnes portent une géométrie exploitable. Les
      // formats "couches natives" (gpkg/kml/kmz/gml) n'en ont jamais besoin.
      if (isTabularSheetFormat(file!.name)) {
        const { fields } = await client.inspectUpload({
          key: uploadedKey,
          filename: file!.name,
          layerName,
        });
        await inspectFieldsThenProceed(uploadedKey, layerName, fields ?? null);
        return;
      }
      await startJob(uploadedKey, layerName);
    } catch {
      if (!mountedRef.current) return;
      setPhase("error");
      setError(t("importFile.genericError"));
    }
  }

  async function confirmGeometry(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadedKey) return;
    if (geometryChoice === "latlon" && (!latField || !lonField)) return;
    if (geometryChoice === "wkt" && !wktField) return;
    setPhase("uploading");
    setError("");
    try {
      const geometryOverride: GeometryOverride =
        geometryChoice === "wkt"
          ? { wktField, geometryMode: "wkt" }
          : geometryChoice === "none"
            ? { geometryMode: "none" }
            : { latField, lonField };
      await startJob(uploadedKey, pendingLayerName, geometryOverride);
    } catch {
      if (!mountedRef.current) return;
      setPhase("error");
      setError(t("importFile.genericError"));
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  // Fermer pendant un upload/un balayage en vol laisserait la chaîne async
  // (submit()/confirmLayer()/confirmGeometry()/poll()) tourner en
  // arrière-plan — même patron que Tileset3DUploadButton.requestClose() :
  // ignore Échap et le pointerdown extérieur (les deux passent par
  // onOpenChange de Drawer) tant que busy, en plus du disabled={busy}
  // explicite sur Annuler.
  function requestClose() {
    if (busy) return;
    close();
  }

  const continueDisabledForGeometry =
    geometryChoice === "latlon"
      ? !latField || !lonField
      : geometryChoice === "wkt"
        ? !wktField
        : false;

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
        {phase === "selecting-geometry" ? (
          <form onSubmit={(e) => void confirmGeometry(e)} className="flex flex-col gap-3">
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm text-ink">{t("importFile.geometryModeLegend")}</legend>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="geometryChoice"
                  checked={geometryChoice === "latlon"}
                  onChange={() => setGeometryChoice("latlon")}
                />
                {t("importFile.geometryModeLatLon")}
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="geometryChoice"
                  checked={geometryChoice === "wkt"}
                  onChange={() => setGeometryChoice("wkt")}
                />
                {t("importFile.geometryModeWkt")}
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="geometryChoice"
                  checked={geometryChoice === "none"}
                  onChange={() => setGeometryChoice("none")}
                />
                {t("importFile.geometryModeNone")}
              </label>
            </fieldset>
            {geometryChoice === "latlon" && (
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
            {geometryChoice === "wkt" && (
              <label className="flex flex-col gap-1 text-sm text-ink">
                {t("importFile.wktColumn")}
                <select
                  aria-label={t("importFile.wktColumn")}
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={wktField}
                  onChange={(e) => setWktField(e.target.value)}
                >
                  <option value="">—</option>
                  {csvHeaders!.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                {t("confirmDialog.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={continueDisabledForGeometry}>
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
                accept=".geojson,.json,.csv,.xlsx,.kml,.kmz,.gpkg,.zip,.parquet,.jsonl,.gml,.xml"
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
