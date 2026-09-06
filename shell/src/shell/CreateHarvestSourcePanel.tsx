// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import type { HarvestSourceType } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs", "ckan"];

export function CreateHarvestSourcePanel({ onClose }: { onClose: () => void }) {
  const createSource = useCreateHarvestSource();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [type, setType] = useState<HarvestSourceType>("stac");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"reference" | "copy">("reference");
  const [intervalMinutes, setIntervalMinutes] = useState("");
  const copyAllowed = COPY_TYPES.includes(type);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url) return;
    try {
      await createSource.mutateAsync({
        type,
        url,
        mode,
        enabled: true,
        ...(intervalMinutes ? { intervalMinutes: Number(intervalMinutes) } : {}),
      });
      onClose();
    } catch {
      // surfaced via createSource.isError
    }
  }

  return (
    <section aria-label="Ajouter une source" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Ajouter une source</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
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
        <label className="flex flex-col gap-1 text-sm text-ink">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          Mode
          <select
            aria-label="Mode"
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">Référence</option>
            <option value="copy" disabled={!copyAllowed}>
              Copie
            </option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          Intervalle de rafraîchissement (minutes)
          <Input
            aria-label="Intervalle de rafraîchissement (minutes)"
            type="number"
            min={1}
            value={intervalMinutes}
            onChange={(e) => setIntervalMinutes(e.target.value)}
          />
        </label>
        {createSource.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!url || createSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
