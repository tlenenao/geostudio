// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useInstanceInfo, useUpdateHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function EditHarvestSourceDialog({
  source,
  open,
  onClose,
}: {
  source: HarvestSource;
  open: boolean;
  onClose: () => void;
}) {
  const updateSource = useUpdateHarvestSource(source.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState(source.url);
  const [enabled, setEnabled] = useState(source.enabled);

  useEffect(() => {
    if (!open) return;
    setUrl(source.url);
    setEnabled(source.enabled);
    updateSource.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateSource.mutateAsync({ url, enabled });
      onClose();
    } catch {
      // surfaced via updateSource.isError
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Éditer ${source.url}`}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Actif"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Actif
        </label>
        {updateSource.isError && (
          <p role="alert" className="text-sm text-red-600">
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
    </Dialog>
  );
}
