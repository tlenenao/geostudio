import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { DataSource, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DataProvider, useDataStates } from "./DataContext";

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} },
];

function Probe() {
  const states = useDataStates();
  const s = states["ds1"];
  if (!s || s.loading) return <p>loading</p>;
  return <p>records:{s.records.length} url:{s.url}</p>;
}

test("resolves sources and exposes their state", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: {} }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={sources}>
          <Probe />
        </DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText(/records:1/)).toBeInTheDocument());
  expect(screen.getByText(/url:https:\/\/fs\/parcs\/items.json/)).toBeInTheDocument();
});
