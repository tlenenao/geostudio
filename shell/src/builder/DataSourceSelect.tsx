// SPDX-License-Identifier: Apache-2.0
import { useItems } from "../api/hooks";
import type { DataSource } from "../api/types";
import { t } from "../i18n";
import { useAddDataSource } from "./DataSourcesEditContext";
import { useSourceLabel } from "./useSourceLabel";

export function DataSourceSelect({
  value,
  dataSources,
  onChange,
}: {
  value: string;
  dataSources: DataSource[];
  onChange: (id: string) => void;
}) {
  const addDataSource = useAddDataSource();
  const sourceLabel = useSourceLabel(Boolean(addDataSource));
  const datasetsQuery = useItems(
    { type: "dataset", pageSize: 100 },
    { enabled: Boolean(addDataSource) },
  );
  const boundDatasetIds = new Set(
    dataSources.map((s) => s.datasetId).filter((id): id is string => Boolean(id)),
  );
  const sharedDatasets = (datasetsQuery.data?.items ?? []).filter(
    (d) => !boundDatasetIds.has(d.pk),
  );

  function handleChange(raw: string) {
    if (raw.startsWith("dataset:")) {
      const pk = raw.slice("dataset:".length);
      const source: DataSource = {
        id: crypto.randomUUID(),
        type: "features",
        service: "core",
        layer: "",
        datasetId: pk,
        query: {},
      };
      addDataSource?.(source);
      onChange(source.id);
      return;
    }
    onChange(raw);
  }

  return (
    <label className="flex flex-col gap-1 text-sm">
      {t("dataSourceSelect.label")}
      <select
        aria-label={t("dataSourceSelect.label")}
        className="h-9 rounded-md border border-control bg-surface px-2 text-sm"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
      >
        <option value="">{t("dataSourceSelect.noneOption")}</option>
        {dataSources.map((s) => (
          <option key={s.id} value={s.id}>
            {sourceLabel(s)}
          </option>
        ))}
        {sharedDatasets.length > 0 && (
          <optgroup label={t("dataSourceSelect.sharedGroupLabel")}>
            {sharedDatasets.map((d) => (
              <option key={d.pk} value={`dataset:${d.pk}`}>
                {d.title}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  );
}
