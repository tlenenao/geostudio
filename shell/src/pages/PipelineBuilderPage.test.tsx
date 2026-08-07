// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, PipelineOpsCatalog, PipelinePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { PipelineBuilderPage } from "./PipelineBuilderPage";

// PipelineBuilderPage renders PipelineNodeInspector -> PipelinePreviewPanel, which can mount
// PipelinePreviewMap (SP-15g Task 16) -> maplibre-gl. jsdom lacks URL.createObjectURL, which
// maplibre-gl calls at import time; same stub as PipelinePreviewPanel.test.tsx/
// PipelinePreviewMap.test.tsx.
vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

// PipelineBuilderPage calls useAuth() for `username` on save — same mock as
// shell/src/shell/NewItemButton.test.tsx, needed because the real hook calls
// react-oidc-context's useAuth(), which throws without an AuthProvider.
vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false, isAuthenticated: true, username: "alice",
    getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(), error: null,
  }),
}));

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", vi.fn().mockImplementation(() => ({
    observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn(),
  })));
});
afterEach(() => vi.unstubAllGlobals());

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

function renderPage(pk: string | null, overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <PipelineBuilderPage pk={pk} initialTitle="Nettoyer villes" />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { client };
}

test("unsaved mode: Enregistrer is disabled on an empty graph", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
});

test("unsaved mode: Aperçu and Exécuter are absent (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Exécuter" })).not.toBeInTheDocument();
});

test("persisted mode: loads the existing graph and shows Exécuter", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload) });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Exécuter" })).toBeInTheDocument();
});

test("persisted mode: a completed run's node stats reach the canvas as a badge", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-1", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null,
        nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 7 } } },
    ]),
  });
  await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
});

test("persisted mode: Enregistrer calls savePipelineConfig with the current graph", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledWith("p-1", payload));
});
