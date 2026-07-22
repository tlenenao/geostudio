// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function CreateHarvestSourceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createSource = useCreateHarvestSource();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"reference" | "copy">("reference");

  function close() {
    setUrl("");
    setMode("reference");
    createSource.reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url) return;
    try {
      await createSource.mutateAsync({ type: "stac", url, mode, enabled: true });
      close();
    } catch {
      // surfaced via createSource.isError
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Ajouter une source">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Mode
          <select
            aria-label="Mode"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">Référence</option>
            <option value="copy">Copie</option>
          </select>
        </label>
        {createSource.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={close}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!url || createSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
