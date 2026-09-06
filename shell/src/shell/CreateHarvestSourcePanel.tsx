// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import type { HarvestSourceType } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";

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
    <section aria-label={t("harvest.addSource")} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">{t("harvest.addSource")}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("catalog.typeLabel")}
          <select
            aria-label={t("catalog.typeLabel")}
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
            value={type}
            onChange={(e) => {
              const next = e.target.value as HarvestSourceType;
              setType(next);
              if (!COPY_TYPES.includes(next)) setMode("reference");
            }}
          >
            <option value="stac">{t("harvest.typeStac")}</option>
            <option value="arcgis">{t("harvest.typeArcgis")}</option>
            <option value="wms">{t("harvest.typeWms")}</option>
            <option value="wfs">{t("harvest.typeWfs")}</option>
            <option value="wmts">{t("harvest.typeWmts")}</option>
            <option value="csw">{t("harvest.typeCsw")}</option>
            <option value="ogc-records">{t("harvest.typeOgcRecords")}</option>
            <option value="ckan">{t("harvest.typeCkan")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("harvest.columnUrl")}
          <Input
            aria-label={t("harvest.columnUrl")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("harvest.columnMode")}
          <select
            aria-label={t("harvest.columnMode")}
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">{t("harvest.modeReference")}</option>
            <option value="copy" disabled={!copyAllowed}>
              {t("harvest.modeCopy")}
            </option>
          </select>
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
        {createSource.isError && (
          <p role="alert" className="text-sm text-danger">
            {t("harvest.createFailed")}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            {t("confirmDialog.cancel")}
          </Button>
          <Button type="submit" size="sm" disabled={!url || createSource.isPending || readOnly}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </section>
  );
}
