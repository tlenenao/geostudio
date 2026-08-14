// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

// S3 multipart accepts a single part of any size — the same chunking code
// path serves a tiny test fixture and a multi-GB tileset (design §4,
// Global Constraints). 100 MB keeps individual PUTs reasonable over a
// typical connection without adding meaningful per-part overhead.
const PART_SIZE_BYTES = 100 * 1024 * 1024;

type Phase = "form" | "uploading" | "finalizing" | "error";

export function Tileset3DUploadButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
    setProgress(null);
  }

  async function poll(jobId: string) {
    for (;;) {
      const job = await client.getTileset3DUploadJob(jobId);
      if (job.status === "done") {
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la validation du tileset.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      const { jobId } = await client.createTileset3DUpload({ filename: file.name, title: title.trim() });
      const partCount = Math.max(1, Math.ceil(file.size / PART_SIZE_BYTES));
      setProgress({ done: 0, total: partCount });
      const parts: { partNumber: number; etag: string }[] = [];
      for (let i = 0; i < partCount; i++) {
        const partNumber = i + 1;
        const chunk = file.slice(i * PART_SIZE_BYTES, (i + 1) * PART_SIZE_BYTES);
        const { uploadUrl } = await client.presignTileset3DUploadPart(jobId, partNumber);
        const res = await fetch(uploadUrl, { method: "PUT", body: chunk });
        if (!res.ok) throw new Error(`Échec de l'envoi de la partie ${partNumber}.`);
        const etag = res.headers.get("ETag") ?? "";
        parts.push({ partNumber, etag });
        setProgress({ done: partNumber, total: partCount });
      }
      setPhase("finalizing");
      await client.completeTileset3DUpload(jobId, parts);
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du tileset.");
    }
  }

  const busy = phase === "uploading" || phase === "finalizing";

  // Closing mid-upload would leave the background submit()/poll() chain
  // running unabandoned: it would eventually call close() again (silently
  // discarding whatever the user started in a since-reopened dialog) or
  // setPhase("error") (overwriting that session's state). Block Escape,
  // backdrop click, and the Annuler button alike while busy — Dialog's
  // onClose is the single funnel for all three.
  function requestClose() {
    if (busy) return;
    close();
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Nouveau tileset 3D
      </Button>
      <Dialog open={open} onClose={requestClose} title="Nouveau tileset 3D">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Archive du tileset (.zip)
            <input
              aria-label="Archive du tileset (.zip)"
              type="file"
              accept=".zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {progress && (
            <p className="text-sm text-slate-500">
              Envoi de la partie {progress.done}/{progress.total}…
            </p>
          )}
          {phase === "finalizing" && (
            <p className="text-sm text-slate-500">Validation du tileset…</p>
          )}
          {phase === "error" && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
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
      </Dialog>
    </>
  );
}
