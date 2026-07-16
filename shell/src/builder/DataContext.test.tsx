// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DataProvider, useDataStates, useSetFilter } from "./DataContext";

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} },
];

function Probe() {
  const states = useDataStates();
  const s = states["ds1"];
  if (!s || s.loading) return <p>loading</p>;
  return <p>records:{s.records.length} url:{s.url} layer:{s.layer}</p>;
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
  expect(screen.getByText(/layer:parcs/)).toBeInTheDocument();
});

test("setFilter merges into a source query and refetches", async () => {
  const queryDataSource = vi.fn()
    .mockResolvedValueOnce([{ id: 1, properties: {} }, { id: 2, properties: {} }])
    .mockResolvedValueOnce([{ id: 1, properties: {} }]);
  const client = {
    queryDataSource,
    featuresUrl: vi.fn().mockReturnValue("https://fs/x/items.json"),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", query: {} }];

  function Probe() {
    const states = useDataStates();
    const setFilter = useSetFilter();
    const s = states["ds1"];
    return (
      <div>
        <button onClick={() => setFilter("ds1", { nom: "A" })}>filter</button>
        <p>count:{s?.records.length ?? -1}</p>
      </div>
    );
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={src}><Probe /></DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText("count:2")).toBeInTheDocument());
  await userEvent.click(screen.getByText("filter"));
  await waitFor(() => expect(screen.getByText("count:1")).toBeInTheDocument());
  expect(queryDataSource).toHaveBeenLastCalledWith(expect.objectContaining({ id: "ds1", query: { nom: "A" } }));
});
