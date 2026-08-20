// SPDX-License-Identifier: Apache-2.0
import { useItems } from "../api/hooks";
import type { DataSource } from "../api/types";
import { useAddDataSource } from "./DataSourcesEditContext";

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
      Source de données
      <select
        aria-label="Source de données"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
      >
        <option value="">Aucune</option>
        {dataSources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.layer || s.id}
          </option>
        ))}
        {sharedDatasets.length > 0 && (
          <optgroup label="Datasets partagés">
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
