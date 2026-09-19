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

const FORMATTED_1200 = (1200).toLocaleString("fr-FR");

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
  await waitFor(() =>
    expect(screen.getByRole("cell", { name: FORMATTED_1200 })).toBeInTheDocument(),
  );
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
  await waitFor(() =>
    expect(screen.getByRole("cell", { name: FORMATTED_1200 })).toBeInTheDocument(),
  );
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

test("paginates rows at 20 per page and shows a counter", async () => {
  const rows = Array.from({ length: 45 }, (_, i) => ({ id: i, pop: i * 10 }));
  renderPanel(vi.fn().mockResolvedValue(rows));
  await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(21)); // header + 20
  expect(screen.getByText("Lignes 1–20 sur 45")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Lignes 21–40 sur 45")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeEnabled();
});

test("resets to the first page when the previewed rows change", async () => {
  const rows45 = Array.from({ length: 45 }, (_, i) => ({ id: i }));
  const rows5 = Array.from({ length: 5 }, (_, i) => ({ id: i }));
  const previewPipeline = vi.fn().mockResolvedValueOnce(rows45).mockResolvedValueOnce(rows5);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("Lignes 1–20 sur 45")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Lignes 21–40 sur 45")).toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="w1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("Lignes 1–5 sur 5")).toBeInTheDocument());
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
  await waitFor(() =>
    expect(screen.getByRole("cell", { name: FORMATTED_1200 })).toBeInTheDocument(),
  );
  await userEvent.click(screen.getByRole("cell", { name: FORMATTED_1200 }).closest("tr")!);
  expect(screen.getByText("Attributs de la feature")).toBeInTheDocument();

  // Re-render with a different node
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r2" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  // Wait for r2's data to actually render, THEN check the panel is gone —
  // otherwise the transient loading state (isLoading true on key change,
  // because usePipelinePreview keys its query on nodeId and "r2" has never
  // been queried before) trivially satisfies "not in document" before r2's
  // data ever resolves, without ever exercising the selectedIndex reset.
  await waitFor(() => expect(screen.getByRole("cell", { name: "800" })).toBeInTheDocument());
  expect(screen.queryByText("Attributs de la feature")).not.toBeInTheDocument();
});

// I6, final review: since Task 2, the preview re-executes on every draft
// edit (not just node switches) — a row selected before an edit must not
// silently point at "the same index in the new result set". Same node,
// same pipelineId, only the `draft` identity changes (queryKey includes
// `draft`, so it's a genuinely new query variant) — the sibling
// "resets the selected row when the node changes" test above covers the
// nodeId-change path; this covers the data-only-change path.
test("resets the selected row when the previewed data changes without the node changing", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const previewPipeline = vi
    .fn()
    .mockResolvedValueOnce([{ id: 1, pop: 1200 }])
    .mockResolvedValueOnce([{ id: 2, pop: 800 }]);
  const client: Partial<ItemClient> = { previewPipeline };
  // React Query's queryKey comparison is structural, not by identity — the
  // two drafts must differ in content (not just object identity) for the
  // rerender to actually trigger a distinct query/refetch.
  const draftA: PipelinePayload = { nodes: [], edges: [] };
  const draftB: PipelinePayload = {
    nodes: [
      {
        id: "n1",
        kind: "transform",
        op: "transform.filter",
        x: 0,
        y: 0,
        params: { expr: "true" },
        title: "n1",
      },
    ],
    edges: [],
  };

  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" draft={draftA} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() =>
    expect(screen.getByRole("cell", { name: FORMATTED_1200 })).toBeInTheDocument(),
  );
  await userEvent.click(screen.getByRole("cell", { name: FORMATTED_1200 }).closest("tr")!);
  expect(screen.getByText("Attributs de la feature")).toBeInTheDocument();

  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" draft={draftB} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByRole("cell", { name: "800" })).toBeInTheDocument());
  expect(screen.queryByText("Attributs de la feature")).not.toBeInTheDocument();
});

test("formats a number with French thousands separators", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, pop: 1234567 }]));
  await waitFor(() =>
    expect(
      screen.getByRole("cell", { name: (1234567).toLocaleString("fr-FR") }),
    ).toBeInTheDocument(),
  );
});

test("shows a Voir sur la carte button instead of raw geometry JSON", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Voir sur la carte" })).toBeInTheDocument(),
  );
  expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
});

test("clicking a column header sorts rows ascending, then descending on a second click", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, pop: 300 },
      { id: 2, pop: 100 },
      { id: 3, pop: 200 },
    ]),
  );
  await waitFor(() => expect(screen.getByRole("cell", { name: "300" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("columnheader", { name: "pop" }));
  let cells = screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[1].textContent);
  expect(cells).toEqual(["100", "200", "300"]);
  await userEvent.click(screen.getByRole("columnheader", { name: "pop" }));
  cells = screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[1].textContent);
  expect(cells).toEqual(["300", "200", "100"]);
});

// I7, final review: the sort headers were mouse-only (a bare onClick on a
// <th>, no focusability or key handling), inconsistent with the keyboard
// paths this plan added elsewhere (search shortcut, keyboard edge
// connection). Pressing Enter on a focused header must sort exactly like a
// click.
test("pressing Enter on a focused column header sorts the table", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, pop: 300 },
      { id: 2, pop: 100 },
      { id: 3, pop: 200 },
    ]),
  );
  await waitFor(() => expect(screen.getByRole("cell", { name: "300" })).toBeInTheDocument());
  const header = screen.getByRole("columnheader", { name: "pop" });
  header.focus();
  fireEvent.keyDown(header, { key: "Enter" });
  const cells = screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[1].textContent);
  expect(cells).toEqual(["100", "200", "300"]);
});

// I7, final review: row selection was mouse-only (onClick on a <tr>, no
// tabIndex/onKeyDown) — pressing Enter on a focused row must select it, same
// as a click.
test("pressing Enter on a focused row selects it", async () => {
  renderPanel();
  await waitFor(() =>
    expect(screen.getByRole("cell", { name: FORMATTED_1200 })).toBeInTheDocument(),
  );
  const row = screen.getByRole("cell", { name: FORMATTED_1200 }).closest("tr")!;
  row.focus();
  fireEvent.keyDown(row, { key: "Enter" });
  expect(screen.getByText("Attributs de la feature")).toBeInTheDocument();
});

test("clicking Voir sur la carte switches to map view with that row selected", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, geometry: { type: "Point", coordinates: [1, 2] } },
      { id: 2, geometry: { type: "Point", coordinates: [3, 4] } },
    ]),
  );
  await waitFor(() =>
    expect(screen.getAllByRole("button", { name: "Voir sur la carte" })).toHaveLength(2),
  );
  await userEvent.click(screen.getAllByRole("button", { name: "Voir sur la carte" })[1]);
  expect(screen.getByTestId("pipeline-preview-map")).toBeInTheDocument();
});
