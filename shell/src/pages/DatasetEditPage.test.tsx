// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { createMemoryRouter, Link, RouterProvider, useParams } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CollectionSchema, DatasetConfig, Item, ItemClient } from "../api/types";
import { ApiError } from "../api/ApiError";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ToastProvider } from "../ui/kit/ToastProvider";
import { DatasetEditPage } from "./DatasetEditPage";
import { OWNER_PERMISSIONS, READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { t } from "../i18n";

const item: Item = {
  pk: "ds-1",
  resourceType: "dataset",
  title: "Parcs",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-ds1",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

const datasetConfig: DatasetConfig = {
  source: "collection",
  collectionId: "parcs",
  columns: {},
};

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

// Route probe : rend le pk de pipeline capturé par la route de l'assistant
// requête visuelle, pour vérifier une navigation réelle (pas seulement un
// href) sans dépendre du vrai VisualQueryWizardPage.
function VisualQueryEditProbe() {
  const { pipelinePk } = useParams();
  return <p>Assistant requête visuelle pour {pipelinePk}</p>;
}

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local au fichier, jamais dans
// shell/src/test/setup.ts. matches: false => le layout "large" (3 volets
// simultanés), pas les onglets — la valeur par défaut de tous les tests
// existants de ce fichier, qui n'affirment pas sur la largeur.
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

// REV-079 : `vi.spyOn` (au lieu de `vi.stubGlobal("URL", { ...URL, ... })`)
// laisse le constructeur `URL` intact — un `{ ...URL }` produit un objet
// simple, non constructible via `new`, qui restait installé pour tous les
// tests suivants du fichier faute de nettoyage.
// REV-093 : `vi.unstubAllGlobals()` nettoie en plus le stub `matchMedia`
// posé par `stubMatchMedia()` ci-dessus, jamais désinstallé sinon.
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// SP-B6d : `useDirtyGuard` (Tâche 26) s'appuie sur `useBlocker`, qui exige un
// data router (`createMemoryRouter`/`RouterProvider`) — un `<MemoryRouter>`
// déclaratif fait lever `useBlocker` à l'exécution (cf. Tâche 27).
function renderPage(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    listAlertRulesForDataset: vi.fn().mockResolvedValue([]),
    ...client,
  };
  const router = createMemoryRouter(
    [
      { path: "/", element: <DatasetEditPage pk="ds-1" /> },
      {
        path: "/datasets/visual-query/:pipelinePk/edit",
        element: <VisualQueryEditProbe />,
      },
    ],
    { initialEntries: ["/"] },
  );
  return render(
    <ToastPrimitive.Provider>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={merged as ItemClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </ItemClientProvider>
      </QueryClientProvider>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

// Harnais dédié aux tests de garde de navigation (SP-B6d, même patron que
// Task 27/MapEditorPage) : un lien factice suffit, le chrome réel
// (AppLayout/TopBar) est hors périmètre de ce fichier.
function renderPageWithNavigation(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    listAlertRulesForDataset: vi.fn().mockResolvedValue([]),
    ...client,
  };
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <>
            <Link to="/autre">Autre page</Link>
            <DatasetEditPage pk="ds-1" />
          </>
        ),
      },
      { path: "/autre", element: <p>Autre page ouverte</p> },
    ],
    { initialEntries: ["/"] },
  );
  return render(
    <ToastPrimitive.Provider>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={merged as ItemClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </ItemClientProvider>
      </QueryClientProvider>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

test("loads the dataset, shows merged columns, and saves an edited label", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.type(screen.getByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.columns.nom.label).toBe("Nom du parc");
});

test("edits the time field and reacts-to-extent flag, and saves them with the columns", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.selectOptions(screen.getByLabelText("Colonne temporelle"), "nom");
  await userEvent.click(screen.getByLabelText("Réagir au déplacement de la carte"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.timeField).toBe("nom");
  expect(savedConfig.reactsToExtent).toBe(true);
});

test("time field defaults to the empty option (no temporal context)", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn(),
  });
  await screen.findByLabelText("Libellé de nom");
  expect(screen.getByLabelText("Colonne temporelle")).toHaveValue("");
  expect(screen.getByLabelText("Réagir au déplacement de la carte")).not.toBeChecked();
});

test("adding a cross-filter link and saving includes it in the saved payload", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [
        {
          pk: "ds-2",
          resourceType: "dataset",
          title: "Incidents",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: null,
          isPublished: false,
        },
      ],
      total: 1,
      page: 1,
      pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un lien" }));
  await userEvent.selectOptions(screen.getByLabelText("Jeu de données cible"), "ds-2");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" },
  ]);
});

test("removing a cross-filter link drops it from the draft before saving", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue({
      ...datasetConfig,
      crossFilterLinks: [
        {
          targetDatasetId: "ds-2",
          mode: "attribute" as const,
          sourceField: "nom",
          targetField: "nom",
        },
      ],
    }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [
        {
          pk: "ds-2",
          resourceType: "dataset",
          title: "Incidents",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: null,
          isPublished: false,
        },
      ],
      total: 1,
      page: 1,
      pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer le lien" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([]);
});

test("offers CSV/XLSX/GeoJSON/GPKG export when the collection has geometry, and downloads on click", async () => {
  const blob = new Blob(["a,b\n1,2\n"], { type: "text/csv" });
  const exportDataSource = vi.fn().mockResolvedValue({ blob, filename: "villes.csv" });
  const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue({
      ...schema,
      geometry: { column: "geometry", type: "Point", srid: 4326 },
    }),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
    exportDataSource,
  });

  await screen.findByText(/Jeu de données partagé/);
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(
    expect.objectContaining({ type: "features", datasetId: "ds-1", query: {} }),
    "csv",
    expect.any(AbortSignal),
  );
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("a failed export surfaces an inline error message instead of failing silently", async () => {
  const exportDataSource = vi
    .fn()
    .mockRejectedValue(new Error("Request failed: 413 GET /collections/parcs/export/items"));

  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue({
      ...schema,
      geometry: { column: "geometry", type: "Point", srid: 4326 },
    }),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
    exportDataSource,
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });

  await screen.findByText(/Jeu de données partagé/);
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));

  expect(await screen.findByRole("alert")).toHaveTextContent("413");
});

test("only offers CSV/XLSX when the collection has no geometry", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema), // schema.geometry is already null
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
  });
  await screen.findByText(/Jeu de données partagé/);
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});

test("shows a « Modifier la requête » button when sourcePipelineId is set, linking to the wizard's edit route", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi
      .fn()
      .mockResolvedValue({ ...datasetConfig, sourcePipelineId: "pipeline-1" }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
  });

  const button = await screen.findByRole("button", { name: "Modifier la requête" });
  await userEvent.click(button);

  expect(await screen.findByText("Assistant requête visuelle pour pipeline-1")).toBeInTheDocument();
});

test("hides the button when sourcePipelineId is absent (dataset created by hand)", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
  });
  await screen.findByText(/Jeu de données partagé/);
  expect(screen.queryByRole("button", { name: "Modifier la requête" })).not.toBeInTheDocument();
});

test("affiche le LoadingState partagé (role=status, spinner) pendant la résolution du schéma", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn(() => new Promise<CollectionSchema>(() => {})),
  });
  await screen.findByText("Colonnes");
  const status = screen.getByRole("status");
  expect(status).toHaveTextContent("Chargement du schéma…");
  expect(status.querySelector('[aria-hidden="true"]')).not.toBeNull();
});

test("affiche le panneau d'historique", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Jeu de données/Réglages avec Jeu de données actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
  });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Jeu de données", "Réglages"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Jeu de données");
});

test("SP-42/F-shell-pages-04 : verrouille Enregistrer quand permissions.write est false", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue({ ...item, permissions: READ_ONLY_PERMISSIONS }),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
  });
  const saveButton = await screen.findByRole("button", { name: "Enregistrer les colonnes" });
  expect(saveButton).toBeDisabled();
  expect(
    screen.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeInTheDocument();
});

test("bloque la navigation après une modification non enregistrée des colonnes (SP-B6d)", async () => {
  renderPageWithNavigation({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
  });

  await userEvent.type(await screen.findByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    t("navigation.unsavedChangesMessage"),
  );
});

test("ne bloque pas la navigation juste après une sauvegarde réussie des colonnes (SP-B6d)", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPageWithNavigation({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
  });

  await userEvent.type(await screen.findByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());

  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));
  expect(await screen.findByText("Autre page ouverte")).toBeInTheDocument();
});

test("REV-271 : envoie la version lue puis celle que le cœur renvoie", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue({ ...datasetConfig, baseVersion: 3 }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
  });
  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(1));
  expect(saveDatasetConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(2));
  expect(saveDatasetConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : un 412 affiche le conflit ; « Recharger » invalide le cache dataset et reprend la version du cœur", async () => {
  const saveDatasetConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  const invalidateDatasetCache = vi.fn();
  const getDatasetConfig = vi
    .fn()
    .mockResolvedValueOnce({ ...datasetConfig, baseVersion: 1 })
    .mockResolvedValue({ ...datasetConfig, baseVersion: 7 });
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig,
    invalidateDatasetCache,
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
  });
  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await screen.findByText(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  expect(invalidateDatasetCache).toHaveBeenCalledWith("ds-1");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(2));
  expect(saveDatasetConfig.mock.calls[1][1].baseVersion).toBe(7);
});
