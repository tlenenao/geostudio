// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useImperativeHandle } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ExplorerDrawer } from "./ExplorerDrawer";
import { ExplorerProvider, useOpenExplorer } from "./ExplorerContext";
import { AnalyticsContextProvider, useSetCrossFilter } from "./AnalyticsContext";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { DatasetConfig, DataRecord, ItemClient } from "../api/types";

const highlightSpy = vi.fn();

vi.mock("../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config }: { config: { layers: { url?: string }[] } },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: vi.fn(), highlight: highlightSpy }));
      return <div data-testid="mapview" data-url={config.layers[0]?.url ?? ""} />;
    },
  ),
}));

function Opener({ datasetId, dataSourceId }: { datasetId: string; dataSourceId: string }) {
  const open = useOpenExplorer();
  return <button onClick={() => open({ datasetId, dataSourceId })}>open</button>;
}

function CrossFilterSetter() {
  const setCrossFilter = useSetCrossFilter();
  // originSourceId "src1" matches the dataSourceId used by <Opener> below on
  // purpose — proves the drawer stays filtered even "from" its own origin,
  // since its synthetic query source id is always "__explorer__", never a
  // real widget id (design §4).
  return <button onClick={() => setCrossFilter("ds1", "region", "Nord", "src1")}>set-cf</button>;
}

function renderDrawer(opts: { queryDataSource?: ReturnType<typeof vi.fn> } = {}) {
  const dataset: DatasetConfig = { source: "collection", collectionId: "col-1", columns: { nom: { label: "Nom" } } };
  const getDatasetConfig = vi.fn().mockResolvedValue(dataset);
  const queryDataSource = opts.queryDataSource ?? vi.fn().mockResolvedValue([]);
  const featuresUrl = vi.fn().mockReturnValue("https://core.test/collections/col-1/items?region=Nord");
  const client = { getDatasetConfig, queryDataSource, featuresUrl } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <ExplorerProvider enabled>
            <Opener datasetId="ds1" dataSourceId="src1" />
            <CrossFilterSetter />
            <ExplorerDrawer />
          </ExplorerProvider>
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { queryDataSource, featuresUrl };
}

beforeEach(() => { highlightSpy.mockClear(); });

test("renders nothing when no target is open", () => {
  renderDrawer();
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("opening a target queries the raw dataset features with the analytics context applied, even from its own origin widget", async () => {
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
  ]);
  renderDrawer({ queryDataSource });
  await userEvent.click(screen.getByText("set-cf"));
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc A");
  expect(queryDataSource).toHaveBeenCalledWith(expect.objectContaining({
    id: "__explorer__",
    datasetId: "ds1",
    query: expect.objectContaining({ limit: 200, region: "Nord" }),
  }));
});

test("table column headers use the dataset's business labels when available", async () => {
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "Parc A" } }]) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText("Nom")).toBeInTheDocument();
});

test("shows the 200-row cap message when the limit is reached", async () => {
  const records: DataRecord[] = Array.from({ length: 200 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  expect(await screen.findByText(/200 premières affichées/)).toBeInTheDocument();
});

test("paginates 20 rows at a time", async () => {
  const records: DataRecord[] = Array.from({ length: 25 }, (_, i) => ({ id: i, properties: { nom: `Parc ${i}` } }));
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue(records) });
  await userEvent.click(screen.getByText("open"));
  await screen.findByText("Parc 0");
  expect(screen.queryByText("Parc 20")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(await screen.findByText("Parc 20")).toBeInTheDocument();
  expect(screen.queryByText("Parc 0")).not.toBeInTheDocument();
});

test("clicking a row highlights it on the drawer's own map without touching the analytics context", async () => {
  const record = { id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } };
  renderDrawer({ queryDataSource: vi.fn().mockResolvedValue([record]) });
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByText("Parc A"));
  expect(highlightSpy).toHaveBeenCalledWith(record.geometry);
});

test("closing via the close button clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await userEvent.click(await screen.findByRole("button", { name: "Fermer le panneau" }));
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});

test("closing via Escape clears the target", async () => {
  renderDrawer();
  await userEvent.click(screen.getByText("open"));
  await screen.findByRole("button", { name: "Fermer le panneau" });
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("button", { name: "Fermer le panneau" })).not.toBeInTheDocument();
});
