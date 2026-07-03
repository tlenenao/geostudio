import { createContext, useContext, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { DataSource, DataSourceState } from "../api/types";

const DataStatesContext = createContext<Record<string, DataSourceState>>({});

export function DataProvider({ sources, children }: { sources: DataSource[]; children: ReactNode }) {
  const client = useItemClient();
  const results = useQueries({
    queries: sources.map((s) => ({
      queryKey: ["datasource", s.id, s.query],
      queryFn: () => client.queryDataSource(s),
    })),
  });
  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      url: s.type === "features" ? client.featuresUrl(s) : undefined,
    };
  });
  return <DataStatesContext.Provider value={states}>{children}</DataStatesContext.Provider>;
}

export function useDataStates(): Record<string, DataSourceState> {
  return useContext(DataStatesContext);
}
