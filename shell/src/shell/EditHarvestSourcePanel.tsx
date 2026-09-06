// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useUpdateHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

export function EditHarvestSourcePanel({
  source,
  onClose,
}: {
  source: HarvestSource;
  onClose: () => void;
}) {
  const updateSource = useUpdateHarvestSource(source.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState(source.url);
  const [enabled, setEnabled] = useState(source.enabled);
  const [intervalMinutes, setIntervalMinutes] = useState(
    source.intervalMinutes != null ? String(source.intervalMinutes) : "",
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateSource.mutateAsync({
        url,
        enabled,
        ...(intervalMinutes ? { intervalMinutes: Number(intervalMinutes) } : {}),
      });
      onClose();
    } catch {
      // surfaced via updateSource.isError
    }
  }

  return (
    <section aria-label={`Éditer ${source.url}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {source.url}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Actif"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Actif
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
        {updateSource.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
