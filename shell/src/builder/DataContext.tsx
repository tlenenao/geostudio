import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { DataSource, DataSourceState } from "../api/types";

type SetFilter = (sourceId: string, query: Record<string, unknown>) => void;

const DataStatesContext = createContext<Record<string, DataSourceState>>({});
const SetFilterContext = createContext<SetFilter>(() => {});

export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
  const [filters, setFilters] = useState<Record<string, Record<string, unknown>>>({});
  const setFilter = useCallback<SetFilter>((sourceId, query) => {
    setFilters((prev) => ({ ...prev, [sourceId]: query }));
  }, []);

  const results = useQueries({
    queries: sources.map((s) => {
      const merged = { ...s, query: { ...s.query, ...(filters[s.id] ?? {}) } };
      return {
        queryKey: ["datasource", s.id, merged.query],
        queryFn: () => client.queryDataSource(merged),
      };
    }),
  });

  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    const merged = { ...s, query: { ...s.query, ...(filters[s.id] ?? {}) } };
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      layer: s.layer,
      url: s.type === "features" ? client.featuresUrl(merged) : undefined,
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
