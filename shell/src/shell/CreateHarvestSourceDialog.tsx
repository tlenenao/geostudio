// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import type { HarvestSourceType } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function CreateHarvestSourceDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const createSource = useCreateHarvestSource();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [type, setType] = useState<HarvestSourceType>("stac");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"reference" | "copy">("reference");
  const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs", "ckan"];
  const copyAllowed = COPY_TYPES.includes(type);

  function close() {
    setType("stac");
    setUrl("");
    setMode("reference");
    createSource.reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url) return;
    try {
      await createSource.mutateAsync({ type, url, mode, enabled: true });
      close();
    } catch {
      // surfaced via createSource.isError
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Ajouter une source">
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={type}
            onChange={(e) => {
              const next = e.target.value as HarvestSourceType;
              setType(next);
              if (!COPY_TYPES.includes(next)) setMode("reference");
            }}
          >
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
            <option value="wmts">WMTS</option>
            <option value="csw">CSW</option>
            <option value="ogc-records">OGC API - Records</option>
            <option value="ckan">CKAN</option>
          </select>
        </label>
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
            <option value="copy" disabled={!copyAllowed}>
              Copie
            </option>
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
