// shell/src/pages/VisualQueryWizardPage.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { CollectionAdmin, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { VisualQueryWizardPage } from "./VisualQueryWizardPage";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false, isAuthenticated: true, username: "alice",
    getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(), error: null,
  }),
}));

const BASE_SCHEMA = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string" as const, required: true }],
};

// Forme complète de CollectionAdmin (le brief n'en donnait que id/title,
// ce qui échoue tsc --noEmit contre la vraie forme de api/types.ts — même
// convention que CollectionParamSelect.test.tsx).
const COLLECTIONS: CollectionAdmin[] = [
  {
    id: "incidents", title: "Incidents", description: "", tableName: "incidents",
    isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id",
    canWrite: true, featureCount: 10, owner: "alice",
  },
];

function renderWizard(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listCollections: () => Promise.resolve(COLLECTIONS),
    getCollectionSchema: () => Promise.resolve(BASE_SCHEMA),
    createEmptyCollection: vi.fn().mockResolvedValue({ id: "query_out" }),
    createDatasetItem: vi.fn().mockResolvedValue({ pk: "dataset-1", resourceType: "dataset", title: "Ma requête", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-1", isPublished: false }),
    createPipelineItem: vi.fn().mockResolvedValue({ pk: "pipeline-1", resourceType: "pipeline", title: "Requête — Ma requête", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-2", isPublished: false }),
    saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([{ id: "run-1", status: "succeeded", startedAt: null, finishedAt: null, error: null, nodeStats: {} }]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/datasets/visual-query/new"]}>
          <Routes>
            <Route path="/datasets/visual-query/new" element={<VisualQueryWizardPage pipelinePk={null} initialTitle="Ma requête" />} />
            <Route path="/datasets/:pk/edit" element={<div>dataset-edit-page</div>} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

describe("VisualQueryWizardPage", () => {
  test("crée la collection de sortie, le dataset, le pipeline, les relie, lance le run, puis redirige", async () => {
    const client = renderWizard();
    // Le <select> est rendu immédiatement mais ses <option> dépendent de
    // listCollections() (async) : on attend que "Incidents" apparaisse
    // avant de sélectionner, sinon selectOptions échoue en "value not found"
    // (le <select> ne contient encore que "Choisir…").
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    // Même course que ci-dessus mais pour le schéma de la collection de base
    // (baseSchemaQuery) : handleCreate no-op silencieusement tant que
    // baseSchema n'a pas chargé. La section "Filtrer" n'apparaît qu'une fois
    // baseSchema disponible, donc l'attendre borne la course.
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(client.createEmptyCollection).toHaveBeenCalled());
    expect(client.createDatasetItem).toHaveBeenCalledWith(
      expect.objectContaining({ source: "collection", collectionId: "query_out" }),
    );
    expect(client.createPipelineItem).toHaveBeenCalledWith(
      expect.objectContaining({ owner: "alice" }),
    );
    expect(client.saveDatasetConfig).toHaveBeenCalledWith(
      "dataset-1", expect.objectContaining({ sourcePipelineId: "pipeline-1" }),
    );
    expect(client.runPipeline).toHaveBeenCalledWith("pipeline-1");
    await waitFor(() => expect(screen.getByText("dataset-edit-page")).toBeInTheDocument());
  });

  test("affiche une erreur si le provisionnement échoue, sans créer le dataset ni le pipeline", async () => {
    const client = renderWizard({ createEmptyCollection: vi.fn().mockRejectedValue(new Error("quota dépassé")) });
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quota dépassé");
    expect(client.createDatasetItem).not.toHaveBeenCalled();
  });
});
