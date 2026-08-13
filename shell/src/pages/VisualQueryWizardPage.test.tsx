// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { CollectionAdmin, ItemClient, PipelinePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { VisualQueryWizardPage } from "./VisualQueryWizardPage";
import { compileVisualQueryToPipeline, VisualQueryState } from "../builder/visualQuery/compilePipeline";

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
    savePipelineConfig: vi.fn().mockResolvedValue(undefined),
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

// Pipeline existant tel que produit par compileVisualQueryToPipeline à la
// création (forme reconnue simple : collection de base seule, pas de
// filtre/jointure/résumé) — réutilisé tel quel comme fixture de
// décompilation, cf. brief fix I3.
const EXISTING_STATE: VisualQueryState = {
  title: "Ma requête", baseCollectionId: "incidents",
  filters: [], join: null, summary: null, refreshPolicy: null,
};
const EXISTING_PIPELINE: PipelinePayload = compileVisualQueryToPipeline(
  EXISTING_STATE, BASE_SCHEMA, null, "query_out", "dataset-1",
);

function renderWizardEdit(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listCollections: () => Promise.resolve(COLLECTIONS),
    getCollectionSchema: () => Promise.resolve(BASE_SCHEMA),
    getPipelineConfig: vi.fn().mockResolvedValue(EXISTING_PIPELINE),
    createEmptyCollection: vi.fn().mockResolvedValue({ id: "should-not-be-created" }),
    createDatasetItem: vi.fn().mockResolvedValue({ pk: "should-not-be-created", resourceType: "dataset", title: "x", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-x", isPublished: false }),
    createPipelineItem: vi.fn().mockResolvedValue({ pk: "should-not-be-created", resourceType: "pipeline", title: "x", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-y", isPublished: false }),
    savePipelineConfig: vi.fn().mockResolvedValue(undefined),
    saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([{ id: "run-1", status: "succeeded", startedAt: null, finishedAt: null, error: null, nodeStats: {} }]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/datasets/visual-query/pipeline-1/edit"]}>
          <Routes>
            <Route path="/datasets/visual-query/:pipelinePk/edit" element={<VisualQueryWizardPage pipelinePk="pipeline-1" />} />
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
    // Régression I3 : le mode création n'appelle jamais la primitive de mise
    // à jour en place — seul le mode édition (pipelinePk !== null) le fait.
    expect(client.savePipelineConfig).not.toHaveBeenCalled();
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

  test("attend le run par son propre poll (sans clic manuel), même si le premier statut est \"running\"", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let call = 0;
    const client = renderWizard({
      getPipelineRuns: vi.fn().mockImplementation(() => {
        call += 1;
        const status = call < 2 ? "running" : "succeeded";
        return Promise.resolve([{ id: "run-1", status, startedAt: null, finishedAt: null, error: null, nodeStats: {} }]);
      }),
    });
    await userEvent.selectOptions(await screen.findByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(client.runPipeline).toHaveBeenCalledTimes(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    await waitFor(() => expect(screen.getByText("dataset-edit-page")).toBeInTheDocument());
    // runPipeline n'a été appelé qu'une fois : aucun clic manuel n'a redéclenché un run redondant.
    expect(client.runPipeline).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  test("le bouton Créer est désactivé tant que la jointure ou le résumé sont incomplets", async () => {
    renderWizard();
    // Cf. le premier test de ce fichier : attendre l'option avant de
    // sélectionner, sinon selectOptions échoue en course avec listCollections().
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");

    await userEvent.click(screen.getByRole("button", { name: "Ajouter une jointure" }));
    expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Ajouter un résumé" }));
    // jointure toujours incomplète (aucune collection choisie) -> reste désactivé
    expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();
  });
});

describe("VisualQueryWizardPage — mode édition (Modifier la requête, fix I3)", () => {
  test("« Mettre à jour » réutilise le pipeline/collection/dataset existants au lieu d'en recréer trois", async () => {
    const client = renderWizardEdit();

    // Le formulaire se pré-remplit de façon asynchrone (getPipelineConfig
    // puis décompilation) : attendre la collection de base avant d'agir,
    // même course que les tests en mode création ci-dessus. Le titre n'est
    // pas restauré par la décompilation (le Pipeline ne le porte pas — seul
    // le dataset/l'item pipeline ont un titre, non lus ici) : on le saisit
    // comme le ferait un utilisateur réel avant de soumettre.
    await screen.findByText("Modifier la requête");
    await waitFor(() => expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"));
    await userEvent.type(screen.getByLabelText("Titre"), "Ma requête modifiée");
    await screen.findByText("Filtrer");

    const button = await screen.findByRole("button", { name: "Mettre à jour" });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() => expect(client.savePipelineConfig).toHaveBeenCalled());
    const [calledPk, calledPayload] = (client.savePipelineConfig as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(calledPk).toBe("pipeline-1");
    const writerNode = calledPayload.nodes.find((n: { op: string }) => n.op === "writer.dataset");
    expect(writerNode.params).toEqual(
      expect.objectContaining({ collectionId: "query_out", datasetId: "dataset-1" }),
    );

    // Preuve directe du fix : aucune re-création d'objets.
    expect(client.createEmptyCollection).not.toHaveBeenCalled();
    expect(client.createDatasetItem).not.toHaveBeenCalled();
    expect(client.createPipelineItem).not.toHaveBeenCalled();
    expect(client.saveDatasetConfig).not.toHaveBeenCalled();

    expect(client.runPipeline).toHaveBeenCalledWith("pipeline-1");
  });
});
