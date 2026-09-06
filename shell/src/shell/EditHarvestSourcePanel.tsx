// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useUpdateHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";

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
    <section
      aria-label={t("harvest.editHeading", { url: source.url })}
      className="flex flex-col gap-3"
    >
      <h2 className="text-sm font-semibold text-ink">
        {t("harvest.editHeading", { url: source.url })}
      </h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("harvest.columnUrl")}
          <Input
            aria-label={t("harvest.columnUrl")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label={t("harvest.activeLabel")}
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {t("harvest.activeLabel")}
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("harvest.intervalLabel")}
          <Input
            aria-label={t("harvest.intervalLabel")}
            type="number"
            min={1}
            value={intervalMinutes}
            onChange={(e) => setIntervalMinutes(e.target.value)}
          />
        </label>
        {updateSource.isError && (
          <p role="alert" className="text-sm text-danger">
            {t("harvest.updateFailed")}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            {t("confirmDialog.cancel")}
          </Button>
          <Button type="submit" size="sm" disabled={updateSource.isPending || readOnly}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </section>
  );
}
