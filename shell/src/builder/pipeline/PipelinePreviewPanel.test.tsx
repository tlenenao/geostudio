// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelinePreviewPanel } from "./PipelinePreviewPanel";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

function renderPanel(previewPipeline = vi.fn().mockResolvedValue([{ id: 1, pop: 1200 }])) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { previewPipeline };
}

test("fetches the preview for the given node and renders it as a table", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  expect(previewPipeline).toHaveBeenCalledWith("p-1", "r1");
});

test("shows nothing when no node is selected", () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline: vi.fn() };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId={null} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("surfaces a fetch error", async () => {
  renderPanel(vi.fn().mockRejectedValue(new Error("bad expr")));
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
});

test("shows a Tableau/Carte toggle when rows carry a geometry column, and defaults to Tableau", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]));
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  expect(screen.getByRole("table")).toBeInTheDocument();
});

test("hides the toggle and always shows the table when no row has a geometry column", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(previewPipeline).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Carte" })).not.toBeInTheDocument();
});

test("clicking Carte swaps the table for the map view", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]));
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Carte" }));
  expect(screen.getByTestId("pipeline-preview-map")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
