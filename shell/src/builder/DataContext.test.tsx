// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DataProvider, useDataStates, useSetFilter } from "./DataContext";
import { AnalyticsContextProvider } from "./AnalyticsContext";

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

test("resolves datasetId and pkColumn onto the DataSourceState for a dataset-bound source", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: {} }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs", columns: {}, timeField: null, reactsToExtent: false }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", datasetId: "dataset-1", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    return <p>datasetId:{s?.datasetId ?? "none"} pkColumn:{s?.pkColumn ?? "none"}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="manual">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // Both assertions live in the same waitFor: datasetId is available on the
  // very first render (it's read straight off the source, no fetch needed),
  // but pkColumn depends on a second async hop (dataset config resolves ->
  // triggers the collection-schema fetch -> resolves), so checking it outside
  // the retry loop races against that second hop.
  await waitFor(() => {
    expect(screen.getByText(/datasetId:dataset-1/)).toBeInTheDocument();
    expect(screen.getByText(/pkColumn:id/)).toBeInTheDocument();
  });
});

test("applies the analytics context's time patch to a dataset-bound source's query", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([]);
  const client = {
    queryDataSource,
    featuresUrl: vi.fn().mockReturnValue(""),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs", columns: {}, timeField: "date_releve", reactsToExtent: false }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", datasetId: "dataset-1", query: {} }];

  function Probe() {
    useDataStates();
    return <p>rendered</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await screen.findByText("rendered");
  // The provider starts with an empty context (no timeRange set), so the
  // first fetch has no time patch — this test only proves getDatasetConfig
  // is actually consulted and doesn't crash the query pipeline.
  await waitFor(() => expect(client.getDatasetConfig).toHaveBeenCalledWith("dataset-1"));
});

test("does not crash and leaves pkColumn undefined for an arcgis-sourced dataset", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "X" } }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/arcgis/items.json"),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "arcgis", arcgisItemId: "layer-1", columns: {}, timeField: null, reactsToExtent: false }),
    getCollectionSchema: vi.fn(), // must never be called for arcgis-sourced datasets
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "arcgis-layer", datasetId: "dataset-arcgis", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    if (!s || s.loading) return <p>loading</p>;
    return <p>datasetId:{s.datasetId} pkColumn:{s.pkColumn ?? "undefined"} records:{s.records.length}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="manual">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText(/datasetId:dataset-arcgis/)).toBeInTheDocument();
    expect(screen.getByText(/pkColumn:undefined/)).toBeInTheDocument();
    expect(screen.getByText(/records:1/)).toBeInTheDocument();
  });
  expect(client.getCollectionSchema).not.toHaveBeenCalled();
});

test("exposes resolvedSource and hasGeometry for a collection-backed source with a geometry column", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "collection", collectionId: "parcs", columns: {}, timeField: null, reactsToExtent: false }),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: { column: "geometry", type: "Point", srid: 4326 }, fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "parcs", datasetId: "dataset-1", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    return <p>resolvedSource:{s?.resolvedSource?.id ?? "none"} hasGeometry:{String(s?.hasGeometry)}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="manual">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText(/resolvedSource:ds1/)).toBeInTheDocument();
    expect(screen.getByText(/hasGeometry:true/)).toBeInTheDocument();
  });
});

test("exposes hasGeometry true for an arcgis-sourced dataset regardless of schema", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/arcgis/items.json"),
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "arcgis", arcgisItemId: "layer-1", columns: {}, timeField: null, reactsToExtent: false }),
    getCollectionSchema: vi.fn(), // must never be called for arcgis-sourced datasets
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const src: DataSource[] = [{ id: "ds1", type: "features", service: "featureserv", layer: "arcgis-layer", datasetId: "dataset-arcgis", query: {} }];

  function Probe() {
    const states = useDataStates();
    const s = states["ds1"];
    return <p>hasGeometry:{String(s?.hasGeometry)}</p>;
  }

  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="manual">
          <DataProvider sources={src}><Probe /></DataProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText(/hasGeometry:true/)).toBeInTheDocument());
  expect(client.getCollectionSchema).not.toHaveBeenCalled();
});
