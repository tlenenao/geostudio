// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { CollectionAdmin, ItemClient, PipelinePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { VisualQueryWizardPage } from "./VisualQueryWizardPage";
import {
  compileVisualQueryToPipeline,
  VisualQueryState,
} from "../builder/visualQuery/compilePipeline";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
    username: "alice",
    getAccessToken: () => "t",
    signIn: vi.fn(),
    signOut: vi.fn(),
    error: null,
  }),
}));

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. VisualQueryWizardPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests de ce fichier qui n'affirment pas sur la
// largeur. vi.unstubAllGlobals() en afterEach dès l'introduction du stub.
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => {
  stubMatchMedia(false);
});
afterEach(() => vi.unstubAllGlobals());

const BASE_SCHEMA = {
  collection: "incidents",
  pk: "id",
  geometry: null,
  fields: [{ name: "commune", type: "string" as const, required: true }],
};

// Forme complète de CollectionAdmin (le brief n'en donnait que id/title,
// ce qui échoue tsc --noEmit contre la vraie forme de api/types.ts — même
// convention que CollectionParamSelect.test.tsx).
const COLLECTIONS: CollectionAdmin[] = [
  {
    id: "incidents",
    title: "Incidents",
    description: "",
    tableName: "incidents",
    isPublic: true,
    editable: true,
    geometryType: null,
    srid: null,
    pkColumn: "id",
    permissions: { read: true, write: true, delete: true, share: true },
    featureCount: 10,
    owner: "alice",
    attachmentFields: [],
    license: "",
    licenseUri: "",
    producer: "",
    contact: "",
    updateFrequency: "",
    lineage: "",
    language: "fr",
    version: "",
    temporalStart: null,
    temporalEnd: null,
  },
];

function renderWizard(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listCollections: () => Promise.resolve(COLLECTIONS),
    getCollectionSchema: () => Promise.resolve(BASE_SCHEMA),
    createEmptyCollection: vi.fn().mockResolvedValue({ id: "query_out" }),
    createDatasetItem: vi.fn().mockResolvedValue({
      pk: "dataset-1",
      resourceType: "dataset",
      title: "Ma requête",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-1",
      isPublished: false,
    }),
    createPipelineItem: vi.fn().mockResolvedValue({
      pk: "pipeline-1",
      resourceType: "pipeline",
      title: "Requête — Ma requête",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-2",
      isPublished: false,
    }),
    savePipelineConfig: vi.fn().mockResolvedValue(undefined),
    saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-1",
        status: "succeeded",
        startedAt: null,
        finishedAt: null,
        error: null,
        nodeStats: {},
      },
    ]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/datasets/visual-query/new"]}>
          <Routes>
            <Route
              path="/datasets/visual-query/new"
              element={<VisualQueryWizardPage pipelinePk={null} initialTitle="Ma requête" />}
            />
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
  title: "Ma requête",
  baseCollectionId: "incidents",
  filters: [],
  join: null,
  summary: null,
  refreshPolicy: null,
};
const EXISTING_PIPELINE: PipelinePayload = compileVisualQueryToPipeline(
  EXISTING_STATE,
  BASE_SCHEMA,
  null,
  "query_out",
  "dataset-1",
);

function renderWizardEdit(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listCollections: () => Promise.resolve(COLLECTIONS),
    getCollectionSchema: () => Promise.resolve(BASE_SCHEMA),
    getPipelineConfig: vi.fn().mockResolvedValue(EXISTING_PIPELINE),
    getItem: vi.fn().mockResolvedValue({
      pk: "dataset-1",
      resourceType: "dataset",
      title: "Ma requête existante",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-1",
      isPublished: false,
    }),
    createEmptyCollection: vi.fn().mockResolvedValue({ id: "should-not-be-created" }),
    createDatasetItem: vi.fn().mockResolvedValue({
      pk: "should-not-be-created",
      resourceType: "dataset",
      title: "x",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-x",
      isPublished: false,
    }),
    createPipelineItem: vi.fn().mockResolvedValue({
      pk: "should-not-be-created",
      resourceType: "pipeline",
      title: "x",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-y",
      isPublished: false,
    }),
    savePipelineConfig: vi.fn().mockResolvedValue(undefined),
    saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    updateItem: vi.fn().mockResolvedValue({
      pk: "dataset-1",
      resourceType: "dataset",
      title: "x",
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: "cfg-1",
      isPublished: false,
    }),
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-1",
        status: "succeeded",
        startedAt: null,
        finishedAt: null,
        error: null,
        nodeStats: {},
      },
    ]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/datasets/visual-query/pipeline-1/edit"]}>
          <Routes>
            <Route
              path="/datasets/visual-query/:pipelinePk/edit"
              element={<VisualQueryWizardPage pipelinePk="pipeline-1" />}
            />
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
      "dataset-1",
      expect.objectContaining({ sourcePipelineId: "pipeline-1" }),
    );
    expect(client.runPipeline).toHaveBeenCalledWith("pipeline-1");
    await waitFor(() => expect(screen.getByText("dataset-edit-page")).toBeInTheDocument());
    // Régression I3 : le mode création n'appelle jamais la primitive de mise
    // à jour en place — seul le mode édition (pipelinePk !== null) le fait.
    expect(client.savePipelineConfig).not.toHaveBeenCalled();
  });

  test("Filtrer ne propose jamais un champ attachment comme colonne (revue finale SP-40, I3)", async () => {
    renderWizard({
      getCollectionSchema: () =>
        Promise.resolve({
          ...BASE_SCHEMA,
          fields: [...BASE_SCHEMA.fields, { name: "photos", type: "attachment", required: false }],
        }),
    });
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un filtre" }));
    const columnSelect = await screen.findByLabelText("Colonne du filtre 1");
    expect(screen.getByRole("option", { name: "commune" })).toBeInTheDocument();
    expect(within(columnSelect).queryByRole("option", { name: "photos" })).not.toBeInTheDocument();
  });

  test("affiche une erreur si le provisionnement échoue, sans créer le dataset ni le pipeline", async () => {
    const client = renderWizard({
      createEmptyCollection: vi.fn().mockRejectedValue(new Error("quota dépassé")),
    });
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quota dépassé");
    expect(client.createDatasetItem).not.toHaveBeenCalled();
  });

  test('attend le run par son propre poll (sans clic manuel), même si le premier statut est "running"', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let call = 0;
    const client = renderWizard({
      getPipelineRuns: vi.fn().mockImplementation(() => {
        call += 1;
        const status = call < 2 ? "running" : "succeeded";
        return Promise.resolve([
          { id: "run-1", status, startedAt: null, finishedAt: null, error: null, nodeStats: {} },
        ]);
      }),
    });
    await userEvent.selectOptions(await screen.findByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(client.runPipeline).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
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

  test("revue finale #2, Important 2 : un run en échec réaffiche le formulaire avec un message d'erreur, au lieu de rester bloqué", async () => {
    const client = renderWizard({
      getPipelineRuns: vi.fn().mockResolvedValue([
        {
          id: "run-1",
          status: "failed",
          startedAt: null,
          finishedAt: null,
          error: "message d'échec explicite",
          nodeStats: {},
        },
      ]),
    });
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(client.runPipeline).toHaveBeenCalled());
    // L'écran de run laisse place au formulaire (Titre à nouveau visible) et
    // le message d'erreur du run s'affiche, au lieu de rester bloqué sur
    // "Exécution de la requête…" indéfiniment.
    expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("message d'échec explicite");
  });
});

describe("VisualQueryWizardPage — mode édition (Modifier la requête, fix I3)", () => {
  test("« Mettre à jour » réutilise le pipeline/collection/dataset existants au lieu d'en recréer trois", async () => {
    const client = renderWizardEdit();

    // Le formulaire se pré-remplit de façon asynchrone (getPipelineConfig
    // puis décompilation, puis un fetch séparé de l'item dataset pour son
    // titre — le Pipeline lui-même ne le porte pas) : attendre la collection
    // de base avant d'agir, même course que les tests en mode création
    // ci-dessus.
    await screen.findByText("Modifier la requête");
    await waitFor(() =>
      expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"),
    );
    // Suivi fix I3 : le Titre se pré-remplit depuis l'item dataset, avant
    // toute interaction utilisateur.
    await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue("Ma requête existante"));
    // L'utilisateur reste libre de modifier ce titre pré-rempli ensuite ; on
    // simule cette édition comme le ferait un utilisateur réel avant de
    // soumettre.
    await userEvent.clear(screen.getByLabelText("Titre"));
    await userEvent.type(screen.getByLabelText("Titre"), "Ma requête modifiée");
    await screen.findByText("Filtrer");

    const button = await screen.findByRole("button", { name: "Mettre à jour" });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() => expect(client.savePipelineConfig).toHaveBeenCalled());
    const [calledPk, calledPayload] = (client.savePipelineConfig as ReturnType<typeof vi.fn>).mock
      .calls[0];
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

    // Round 2, Important 2 : le renommage tapé par l'utilisateur doit être
    // persisté sur l'item dataset (le Pipeline lui-même ne porte pas de titre).
    expect(client.updateItem).toHaveBeenCalledWith("dataset-1", { title: "Ma requête modifiée" });
  });

  test("revue finale #2, Important 1 : bloque la soumission si le schéma recompilé ne correspond plus à la sortie déjà provisionnée", async () => {
    // "query_out" (la collection de sortie décompilée depuis EXISTING_PIPELINE)
    // renvoie un schéma cohérent avec la sortie de EXISTING_STATE non modifiée
    // (une seule colonne "commune") — pour que la régression "pas de
    // changement -> pas de blocage" soit vérifiable dans le même test.
    const getCollectionSchema = vi.fn().mockImplementation((collectionId: string) =>
      Promise.resolve(
        collectionId === "query_out"
          ? {
              collection: "query_out",
              pk: "id",
              geometry: null,
              fields: [{ name: "commune", type: "string" as const, required: true }],
            }
          : BASE_SCHEMA,
      ),
    );
    renderWizardEdit({ getCollectionSchema });

    await screen.findByText("Modifier la requête");
    await waitFor(() =>
      expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"),
    );
    await screen.findByText("Filtrer");

    // Pas de changement de la requête : pas de faux positif de blocage.
    const button = await screen.findByRole("button", { name: "Mettre à jour" });
    await waitFor(() => expect(button).not.toBeDisabled());
    expect(screen.queryByText(/La structure de sortie a changé/)).not.toBeInTheDocument();

    // Ajouter un résumé (métrique "count") change les colonnes projetées
    // ("commune" -> "metrique_1") : le schéma recompilé ne correspond plus à
    // la collection de sortie déjà provisionnée.
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un résumé" }));
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une métrique" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mettre à jour" })).toBeDisabled(),
    );
    expect(screen.getByText(/La structure de sortie a changé/)).toBeInTheDocument();
  });

  test("revue finale #2, Important 3 : changer la collection de base réinitialise filtre/jointure/résumé", async () => {
    const collections: CollectionAdmin[] = [
      ...COLLECTIONS,
      {
        id: "other",
        title: "Autre collection",
        description: "",
        tableName: "other",
        isPublic: true,
        editable: true,
        geometryType: null,
        srid: null,
        pkColumn: "id",
        permissions: { read: true, write: true, delete: true, share: true },
        featureCount: 5,
        owner: "alice",
        attachmentFields: [],
        license: "",
        licenseUri: "",
        producer: "",
        contact: "",
        updateFrequency: "",
        lineage: "",
        language: "fr",
        version: "",
        temporalStart: null,
        temporalEnd: null,
      },
    ];
    const client = renderWizard({ listCollections: () => Promise.resolve(collections) });
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");

    await userEvent.click(screen.getByRole("button", { name: "Ajouter une jointure" }));
    expect(screen.getByText("Supprimer la jointure")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "other");
    // La jointure posée sur l'ancienne collection de base a disparu : le
    // bouton "Ajouter une jointure" doit réapparaître (au lieu du picker).
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ajouter une jointure" })).toBeInTheDocument(),
    );
    expect(screen.queryByText("Supprimer la jointure")).not.toBeInTheDocument();
    expect(client.getCollectionSchema).toBeDefined();
  });

  test('revue finale #2, Important 4 : "Ajouter une jointure"/"Ajouter un résumé" sont réversibles', async () => {
    renderWizard();
    await screen.findByRole("option", { name: "Incidents" });
    await userEvent.selectOptions(screen.getByLabelText("Collection de base"), "incidents");
    await screen.findByText("Filtrer");

    await userEvent.click(screen.getByRole("button", { name: "Ajouter une jointure" }));
    expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Supprimer la jointure" }));
    expect(screen.getByRole("button", { name: "Ajouter une jointure" })).toBeInTheDocument();
    // Plus de jointure incomplète en attente : le bouton redevient activable.
    expect(screen.getByRole("button", { name: "Créer" })).not.toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Ajouter un résumé" }));
    // Un résumé vide (ni groupBy ni métrique) est lui aussi incomplet.
    expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le résumé" }));
    expect(screen.getByRole("button", { name: "Ajouter un résumé" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Créer" })).not.toBeDisabled();
  });

  test("round 2, Important 1 : un titre tapé avant que le fetch de l'item dataset ne résolve n'est pas écrasé", async () => {
    let resolveGetItem!: (value: {
      pk: string;
      resourceType: "dataset";
      title: string;
      abstract: string;
      owner: string;
      thumbnailUrl: null;
      date: string;
      configId: string;
      isPublished: boolean;
    }) => void;
    const delayedGetItem = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveGetItem = resolve;
        }),
    );
    const client = renderWizardEdit({ getItem: delayedGetItem });

    // La "Collection de base" apparaît dès la décompilation du pipeline
    // (premier aller-retour) — avant que getItem (second aller-retour) ne
    // résolve. C'est exactement la fenêtre décrite par le finding : on tape
    // un titre pendant cette fenêtre, sans attendre le second fetch — on
    // vérifie juste que la requête est partie (invoquée), pas qu'elle a
    // résolu.
    await waitFor(() =>
      expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"),
    );
    await waitFor(() => expect(client.getItem).toHaveBeenCalled());
    await userEvent.clear(screen.getByLabelText("Titre"));
    await userEvent.type(screen.getByLabelText("Titre"), "Titre tapé par l'utilisateur");

    // Le second fetch résout seulement maintenant, avec un titre serveur
    // différent : il ne doit pas écraser la saisie utilisateur.
    await act(async () => {
      resolveGetItem({
        pk: "dataset-1",
        resourceType: "dataset",
        title: "Titre serveur (ne doit pas apparaître)",
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "",
        configId: "cfg-1",
        isPublished: false,
      });
      // Laisser toutes les promesses/microtâches en attente se résoudre
      // (react-query doit relire la donnée résolue et l'effet de
      // pré-remplissage doit avoir eu l'occasion de s'exécuter).
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByLabelText("Titre")).toHaveValue("Titre tapé par l'utilisateur");
  });

  test("le volet Catalogue affiche la fiche Type/Modifié une fois l'item dataset résolu", async () => {
    renderWizardEdit();
    await screen.findByText("Modifier la requête");
    await waitFor(() =>
      expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"),
    );
    expect(await screen.findByText("Dataset")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Retour au catalogue" })).toBeInTheDocument();
  });
});

describe("VisualQueryWizardPage — volet Catalogue et dégradation d'affichage", () => {
  test("mode création : le volet Catalogue ne montre aucune fiche d'item avant le premier Créer", async () => {
    renderWizard();
    expect(await screen.findByRole("link", { name: "← Retour au catalogue" })).toBeInTheDocument();
    expect(screen.queryByText("Dataset")).not.toBeInTheDocument();
  });

  test("sous viewport étroit, affiche trois onglets Catalogue/Requête/Réglages avec Requête actif par défaut", async () => {
    stubMatchMedia(true);
    renderWizard();
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Requête", "Réglages"]);
    const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect(activeTab).toHaveTextContent("Requête");
  });
});
