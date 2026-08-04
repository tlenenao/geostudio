// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { DataSource, DataSourceState, DatasetConfig } from "../api/types";
import { useAnalyticsContext } from "./AnalyticsContext";
import { derivePatch } from "../lib/analyticsPatch";

type SetFilter = (sourceId: string, query: Record<string, unknown>) => void;

const DataStatesContext = createContext<Record<string, DataSourceState>>({});
const SetFilterContext = createContext<SetFilter>(() => {});

export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
  const analyticsCtx = useAnalyticsContext();
  const [filters, setFilters] = useState<Record<string, Record<string, unknown>>>({});
  const setFilter = useCallback<SetFilter>((sourceId, query) => {
    setFilters((prev) => ({ ...prev, [sourceId]: query }));
  }, []);

  // Resolve DatasetConfig for every distinct datasetId referenced by `sources`
  // — same queryKey ("dataset", pk) as useDatasetConfig() elsewhere, so React
  // Query dedups the fetch, and getDatasetConfig() itself dedups further via
  // itemClient's internal resolveDataset cache.
  const datasetIds = [...new Set(sources.map((s) => s.datasetId).filter((id): id is string => Boolean(id)))];
  const datasetResults = useQueries({
    queries: datasetIds.map((id) => ({ queryKey: ["dataset", id], queryFn: () => client.getDatasetConfig(id) })),
  });
  const datasets: Record<string, DatasetConfig> = {};
  datasetIds.forEach((id, i) => {
    const data = datasetResults[i].data;
    if (data) datasets[id] = data;
  });

  // Resolve the primary-key column name for every distinct collection behind
  // those datasets, so table/map widgets can cross-filter by pk without
  // fetching a schema themselves (they only read ctx.data.pkColumn).
  const collectionIds = [...new Set(Object.values(datasets).filter((d) => d.source === "collection").map((d) => d.source === "collection" ? d.collectionId : ""))].filter(Boolean);
  const schemaResults = useQueries({
    queries: collectionIds.map((id) => ({ queryKey: ["collection-schema", id], queryFn: () => client.getCollectionSchema(id) })),
  });
  const pkByCollection: Record<string, string> = {};
  collectionIds.forEach((id, i) => {
    const data = schemaResults[i].data;
    if (data) pkByCollection[id] = data.pk;
  });

  function mergedQueryFor(s: DataSource): DataSource {
    const contextPatch = derivePatch(s, analyticsCtx, datasets);
    return { ...s, query: { ...s.query, ...contextPatch, ...(filters[s.id] ?? {}) } };
  }

  const results = useQueries({
    queries: sources.map((s) => {
      const merged = mergedQueryFor(s);
      return {
        queryKey: ["datasource", s.id, merged.query],
        queryFn: () => client.queryDataSource(merged),
      };
    }),
  });

  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    const merged = mergedQueryFor(s);
    const dataset = s.datasetId ? datasets[s.datasetId] : undefined;
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      layer: s.layer,
      url: s.type === "features" ? client.featuresUrl(merged) : undefined,
      datasetId: s.datasetId,
      pkColumn: dataset && dataset.source === "collection" ? pkByCollection[dataset.collectionId] : undefined,
    };
  });

  return (
    <SetFilterContext.Provider value={setFilter}>
      <DataStatesContext.Provider value={states}>{children}</DataStatesContext.Provider>
    </SetFilterContext.Provider>
  );
}

export function useDataStates(): Record<string, DataSourceState> {
  return useContext(DataStatesContext);
}

export function useSetFilter(): SetFilter {
  return useContext(SetFilterContext);
}
