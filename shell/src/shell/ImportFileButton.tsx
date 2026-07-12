import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

type Phase = "form" | "uploading" | "polling" | "error";

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();
  const navigate = useNavigate();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setCsvHeaders(null);
    setLatField("");
    setLonField("");
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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    if (needsManualLatLon && (!latField || !lonField)) return;
    setPhase("uploading");
    setError("");
    try {
      const { uploadUrl, key } = await client.presignUpload(
        file.name, file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      const { jobId } = await client.createIngestionJob({
        key, filename: file.name, collectionTitle: title.trim(),
        latField: needsManualLatLon ? latField : undefined,
        lonField: needsManualLatLon ? lonField : undefined,
      });
      setPhase("polling");
      await poll(jobId);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Importer un fichier
      </Button>
      <Dialog open={open} onClose={close} title="Importer un fichier">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Fichier à importer
            <input
              aria-label="Fichier à importer"
              type="file"
              accept=".geojson,.json,.csv"
              onChange={onFileChange}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre de la collection
            <Input
              aria-label="Titre de la collection"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {needsManualLatLon && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                Colonne latitude
                <select
                  aria-label="Colonne latitude"
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={latField}
                  onChange={(e) => setLatField(e.target.value)}
                >
                  <option value="">—</option>
                  {csvHeaders!.map((h) => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Colonne longitude
                <select
                  aria-label="Colonne longitude"
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={lonField}
                  onChange={(e) => setLonField(e.target.value)}
                >
                  <option value="">—</option>
                  {csvHeaders!.map((h) => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
            </>
          )}
          {phase === "error" && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={busy}>
              {phase === "uploading" ? "Envoi…" : phase === "polling" ? "Import en cours…" : "Importer"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
