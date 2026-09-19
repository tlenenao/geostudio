// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, PipelinePayload } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { mapInstances } from "../../test/MockMaplibreMap";
import { PipelinePreviewPanel } from "./PipelinePreviewPanel";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});

beforeEach(() => {
  mapInstances.length = 0;
});

function renderPanel(
  previewPipeline = vi.fn().mockResolvedValue([{ id: 1, pop: 1200 }]),
  extraProps: { draft?: PipelinePayload; isDraftStale?: boolean } = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" {...extraProps} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { previewPipeline };
}

test("fetches the preview for the given node and renders it as a table", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  expect(previewPipeline).toHaveBeenCalledWith("p-1", "r1", undefined);
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
  renderPanel(
    vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]),
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  expect(screen.getByRole("table")).toBeInTheDocument();
});

test("hides the toggle and always shows the table when no row has a geometry column", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(previewPipeline).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Carte" })).not.toBeInTheDocument();
});

test("clicking Carte swaps the table for the map view", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]),
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Carte" }));
  expect(screen.getByTestId("pipeline-preview-map")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("forwards the draft to previewPipeline when provided", async () => {
  const draft: PipelinePayload = { nodes: [], edges: [] };
  const { previewPipeline } = renderPanel(undefined, { draft });
  await waitFor(() => expect(previewPipeline).toHaveBeenCalledWith("p-1", "r1", draft));
});

test("shows a staleness hint when isDraftStale is true", async () => {
  renderPanel(undefined, { isDraftStale: true });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Aperçu à régénérer"));
});

test("shows no staleness hint by default", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(previewPipeline).toHaveBeenCalled());
  expect(screen.queryByText("Aperçu à régénérer", { exact: false })).not.toBeInTheDocument();
});

test("clicking a table row shows its attributes below the table", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, pop: 1200 },
      { id: 2, pop: 800 },
    ]),
  );
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("cell", { name: "800" }).closest("tr")!);
  const heading = screen.getByText("Attributs de la feature");
  // "800" also appears in the table cell for the same row: scope the
  // assertion to the attributes panel to avoid an ambiguous multi-match.
  expect(within(heading.closest("div")!).getByText("800")).toBeInTheDocument();
});

test("selecting a feature on the map is reflected when switching back to the table", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, geometry: { type: "Point", coordinates: [1, 1] } },
      { id: 2, geometry: { type: "Point", coordinates: [2, 2] } },
    ]),
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Carte" }));
  const map = mapInstances[0];
  map.fireOnLayer("click", "pipeline-preview-circle", {
    features: [{ properties: { __rowIndex: 1 } }],
  });
  await userEvent.click(screen.getByRole("button", { name: "Tableau" }));
  const rows = screen.getAllByRole("row");
  expect(rows[2]).toHaveClass("bg-sunken"); // header row + row 0 + selected row 1
});

test("resets the selected row when the node changes", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const previewPipeline = vi
    .fn()
    .mockResolvedValueOnce([{ id: 1, pop: 1200 }])
    .mockResolvedValueOnce([{ id: 2, pop: 800 }]);
  const client: Partial<ItemClient> = { previewPipeline };

  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // Select a row in node r1
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("cell", { name: "1200" }).closest("tr")!);
  expect(screen.getByText("Attributs de la feature")).toBeInTheDocument();

  // Re-render with a different node
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r2" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // The attributes panel should be gone (selectedIndex reset to null)
  await waitFor(() =>
    expect(screen.queryByText("Attributs de la feature")).not.toBeInTheDocument(),
  );
});
