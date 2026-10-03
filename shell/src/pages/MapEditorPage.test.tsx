// SPDX-License-Identifier: Apache-2.0
import { ApiError } from "../api/ApiError";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Item, ItemClient, MapConfig } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS, READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { ToastProvider } from "../ui/kit/ToastProvider";
import { mapInstances } from "../test/MockMaplibreMap";
import { overlayInstances } from "../test/MockDeckgl";
import { t } from "../i18n";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});
vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});
vi.mock("@deck.gl/aggregation-layers", async () => {
  const { HeatmapLayer, HexagonLayer } = await import("../test/MockDeckgl");
  return { HeatmapLayer, HexagonLayer };
});
vi.mock("@deck.gl/layers", async () => {
  const { ColumnLayer } = await import("../test/MockDeckgl");
  return { ColumnLayer };
});
vi.mock("@deck.gl/geo-layers", async () => {
  const { Tile3DLayer } = await import("../test/MockDeckgl");
  return { Tile3DLayer };
});
vi.mock("@loaders.gl/3d-tiles", async () => {
  const { Tiles3DLoader } = await import("../test/MockLoadersGl");
  return { Tiles3DLoader };
});

const { MapEditorPage } = await import("./MapEditorPage");

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local au fichier, jamais dans
// shell/src/test/setup.ts. matches: false => le layout "large" (3 volets
// simultanés), pas les onglets — la valeur par défaut de la plupart des
// tests existants de ce fichier, qui n'affirment pas sur la largeur.
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
  mapInstances.length = 0;
  overlayInstances.length = 0;
  // La couche "feature" de `config` (ci-dessous) déclenche désormais un
  // fetch de son `url` au montage de LayersPanel (Task 2, SP-28) — MSW
  // (onUnhandledRequest: "error") ferait échouer ces tests sans ce repli.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});

afterEach(() => {
  delete document.body.dataset.exportReady;
  vi.unstubAllGlobals();
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.4, 46.6], zoom: 5 },
  layers: [{ id: "a", title: "Couche A", visible: true, kind: "feature", url: "u" }],
};

// Item par défaut de la carte "77" (seul pk utilisé par ce fichier) :
// permissions.write=true, comme avant l'introduction du garde
// SP-42/F-shell-pages-04 (aucun test existant n'affirme sur des permissions
// restreintes — celui qui le fait le surcharge explicitement).
const OWNED_MAP_ITEM: Item = {
  pk: "77",
  resourceType: "map",
  title: "Carte",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-77",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

// SP-B6c : `useDirtyGuard` (Tâche 26) s'appuie sur `useBlocker`, qui exige un
// data router (`createMemoryRouter`/`RouterProvider`) — un `<MemoryRouter>`
// déclaratif (React Router "component router") fait lever `useBlocker` à
// l'exécution. Route unique "/maps/:pk", ignorée par `MapEditorPage` (le
// `pk` réel vient toujours de la prop, comme avant) — seule la query string
// (`?exportRender=1`) compte pour `useIsExportRender`, qui lit
// `location.search`, indépendant du matching de route.
function renderEditor(client: Partial<ItemClient>, initialEntries: string[] = ["/maps/77"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    getItem: vi.fn().mockResolvedValue(OWNED_MAP_ITEM),
    ...client,
  };
  const router = createMemoryRouter([{ path: "/maps/:pk", element: <MapEditorPage pk="77" /> }], {
    initialEntries,
  });
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

// Harnais dédié aux tests de garde de navigation (Tâche 27) : le lien "Retour
// au catalogue" fait normalement partie du chrome (AppLayout/TopBar), hors
// périmètre de ce fichier qui monte `MapEditorPage` isolément — un lien
// factice suffit à prouver que le blocker engage bien la navigation, quelle
// que soit son origine réelle dans l'app.
function renderEditorWithNavigation(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    getItem: vi.fn().mockResolvedValue(OWNED_MAP_ITEM),
    ...client,
  };
  const router = createMemoryRouter(
    [
      {
        path: "/maps/:pk",
        element: (
          <>
            <Link to="/">Retour au catalogue</Link>
            <MapEditorPage pk="77" />
          </>
        ),
      },
      { path: "/", element: <p>Catalogue</p> },
    ],
    { initialEntries: ["/maps/77"] },
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

test("SP-B12c : le repli de chargement de la carte n'a pas de couleur Tailwind codée en dur", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  const fallback = await screen.findByText("Carte…");
  expectTokenizedClasses(fallback.parentElement ?? fallback);
  await waitFor(() => expect(mapInstances[0]).toBeDefined());
});

test("loads the config and saves edits", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Retirer Couche A" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const savedLayers = saveMapConfig.mock.calls[0][1].layers;
  expect(savedLayers).toEqual([]);
});

test("shows an error when loading fails", async () => {
  renderEditor({ getMapConfig: vi.fn().mockRejectedValue(new Error("boom")) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/erreur de chargement/i);
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
});

test("saving after only changing a layer keeps the previously loaded printLayout", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue({
      ...config,
      printLayout: { pageSize: "a3", orientation: "landscape" },
    }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await screen.findByText(/A3/i); // le panneau reflète bien le printLayout chargé
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const savedConfig = saveMapConfig.mock.calls[0][1];
  expect(savedConfig.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
});

test("edits terrain and camera, then saves both", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");

  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  await userEvent.type(
    screen.getByLabelText("URL de tuiles terrain"),
    "https://example.test/dem/{{z}/{{x}/{{y}.png",
  );
  fireEvent.change(screen.getByLabelText("Inclinaison de la caméra"), { target: { value: "40" } });
  fireEvent.change(screen.getByLabelText("Orientation de la caméra"), { target: { value: "200" } });

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.terrain).toEqual({
    tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
    encoding: "terrarium",
    exaggeration: 1,
  });
  expect(saved.view.pitch).toBe(40);
  expect(saved.view.bearing).toBe(200);
});

test("the camera reset button zeroes pitch and bearing in the saved view", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValue({ ...config, view: { ...config.view, pitch: 40, bearing: 200 } }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Réinitialiser en 2D" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.view.pitch).toBe(0);
  expect(saved.view.bearing).toBe(0);
});

test("surfaces a save failure", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig: vi.fn().mockRejectedValue(new Error("nope")),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText(/échec de l'enregistrement/i)).toBeInTheDocument();
});

test("REV-271 : envoie la version lue à l'enregistrement puis celle que le cœur renvoie", async () => {
  const saveMapConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...config, baseVersion: 3 })
      .mockResolvedValueOnce({ ...config, baseVersion: 4 })
      .mockResolvedValue({ ...config, baseVersion: 5 }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(1));
  expect(saveMapConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(2));
  expect(saveMapConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : un 412 affiche le conflit ; « Recharger » reprend la dernière version du cœur", async () => {
  const saveMapConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...config, baseVersion: 1 })
      .mockResolvedValue({ ...config, baseVersion: 7 }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await screen.findByText(t("common.saveConflict"));
  expect(screen.queryByText(/échec de l'enregistrement/i)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(2));
  expect(saveMapConfig.mock.calls[1][1].baseVersion).toBe(7);
});

test("exportRender=1 hides the builder chrome (no save button/layer removal controls) and marks the page export-ready once the map idles", async () => {
  renderEditor(
    {
      getMapConfig: vi.fn().mockResolvedValue({
        ...config,
        printLayout: {
          title: "Carte des communes",
          showLegend: true,
          cartouche: "GeoStudio © 2026",
        },
      }),
      listLayerSources: vi.fn().mockResolvedValue([]),
    },
    ["/maps/77?exportRender=1"],
  );
  // Builder chrome must be absent from the capture.
  expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retirer Couche A" })).not.toBeInTheDocument();
  // PrintLayout overlays render from the loaded config.
  expect(await screen.findByText("Carte des communes")).toBeInTheDocument();
  expect(screen.getByText("Couche A")).toBeInTheDocument(); // showLegend
  expect(screen.getByText("GeoStudio © 2026")).toBeInTheDocument();
  // The map fires "idle" synchronously on mount in the MockMap harness — the
  // export-ready DOM signal (Task 6's contract) must follow. But mounting
  // the mocked MapLibre instance still happens inside MapView's effect, one
  // tick after this test's own render/findByText resolve — indexing
  // mapInstances[0] without waiting was a ~25% flake on this branch's merge
  // (I6 de la revue finale SP-25), not caused by SP-25 itself.
  await waitFor(() => expect(mapInstances[0]).toBeDefined());
  mapInstances[0].fire("idle");
  expect(document.body.getAttribute("data-export-ready")).toBe("true");
});

test("les outils de mesure/croquis sont montés en édition (GAP-53)", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  expect(await screen.findByRole("button", { name: "Mesurer" })).toBeInTheDocument();
});

test("affiche le panneau d'historique", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Couches/Carte/Inspecter avec Carte active par défaut", async () => {
  stubMatchMedia(true);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Couches", "Carte", "Inspecter"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Carte");
});

test("SP-42/F-shell-pages-04 : verrouille Enregistrer quand permissions.write est false", async () => {
  renderEditor({
    getItem: vi.fn().mockResolvedValue({ ...OWNED_MAP_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  const saveButton = await screen.findByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeDisabled();
  expect(
    screen.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeInTheDocument();
});

test("SP-42, revue finale (point 2, Critical) : reste en chargement tant que l'item n'est pas résolu, ne verrouille pas Enregistrer par erreur", async () => {
  let resolveItem!: (item: Item) => void;
  let resolveMapConfig!: (config: MapConfig) => void;
  renderEditor({
    getItem: vi.fn(
      () =>
        new Promise<Item>((resolve) => {
          resolveItem = resolve;
        }),
    ),
    getMapConfig: vi.fn(
      () =>
        new Promise<MapConfig>((resolve) => {
          resolveMapConfig = resolve;
        }),
    ),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });

  // Résout le config de carte SEUL, jamais l'item : avant le correctif, la
  // page rendait déjà l'éditeur complet avec Enregistrer verrouillé
  // (permissions.write lu sur `undefined` => false, cf. hasPermission) dès
  // que `draft` était posé, sans attendre itemQuery — au lieu de rester en
  // "Chargement…" comme son jumeau DatasetEditPage.tsx.
  await act(async () => {
    resolveMapConfig(config);
    // Laisse toutes les micro-tâches en attente se résoudre (react-query
    // doit relire la donnée résolue et l'effet de synchronisation du
    // brouillon doit avoir eu l'occasion de s'exécuter) — même patron que
    // VisualQueryWizardPage.test.tsx.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");

  resolveItem(OWNED_MAP_ITEM);
  const saveButton = await screen.findByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeEnabled();
});

test("SP-42, revue finale (point 2, Critical) : affiche une erreur si l'item ne charge pas, ne verrouille pas silencieusement", async () => {
  renderEditor({
    getItem: vi.fn().mockRejectedValue(new ApiError(404)),
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(/carte introuvable/i);
});

test("ajuste automatiquement la vue à l'emprise des données quand la vue est encore la valeur par défaut (D18)", async () => {
  renderEditor({
    getItem: vi.fn().mockResolvedValue({ ...OWNED_MAP_ITEM, bbox: [1, 10, 3, 20] }),
    getMapConfig: vi.fn().mockResolvedValue(config), // view: { center: [2.4, 46.6], zoom: 5 }
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  // C1 (revue finale) : l'auto-cadrage n'agit plus tant que MapView n'a pas
  // signalé `onReady` (idle) — même patron que le test export-ready
  // ci-dessus (ligne ~241) : sans ce `fire("idle")`, `mapReady` reste faux
  // et l'effet D18 ne s'exécute jamais jusqu'au bout.
  await waitFor(() => expect(mapInstances[0]).toBeDefined());
  mapInstances[0].fire("idle");
  await waitFor(() => expect(mapInstances[0]?.fitBoundsArgs).toHaveLength(1));
  expect(mapInstances[0].fitBoundsArgs[0]).toMatchObject({
    bounds: [
      [1, 10],
      [3, 20],
    ],
  });
});

test("ne réajuste pas la vue quand elle diffère déjà de la valeur par défaut (vue sauvegardée par l'utilisateur, D18)", async () => {
  renderEditor({
    getItem: vi.fn().mockResolvedValue({ ...OWNED_MAP_ITEM, bbox: [1, 10, 3, 20] }),
    getMapConfig: vi.fn().mockResolvedValue({ ...config, view: { center: [5, 5], zoom: 9 } }),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await waitFor(() => expect(mapInstances).toHaveLength(1));
  expect(mapInstances[0].fitBoundsArgs).toHaveLength(0);
});

test("affiche la légende de symbologie de chaque couche vecteur visible (D15)", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue({
      ...config,
      layers: [
        {
          id: "v1",
          title: "Zones",
          visible: true,
          kind: "vector",
          tilesUrl: "https://core/tiles/{z}/{x}/{y}",
          sourceLayer: "zones",
          geometryKind: "polygon",
          symbology: {
            color: {
              field: "type",
              mode: "categorical",
              palette: "categorical-a",
              domain: { kind: "categorical", values: ["Résidentiel", "Commercial"] },
              computedAt: "2026-09-27T10:00:00Z",
            },
          },
        },
      ],
    }),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Résidentiel")).toBeInTheDocument();
});

test("la légende de symbologie ne recouvre pas la légende des noms de couches (revue Tâche 35)", async () => {
  const { container } = renderEditor({
    getMapConfig: vi.fn().mockResolvedValue({
      ...config,
      layers: [
        {
          id: "v1",
          title: "Zones",
          visible: true,
          kind: "vector",
          tilesUrl: "https://core/tiles/{z}/{x}/{y}",
          sourceLayer: "zones",
          geometryKind: "polygon",
          symbology: {
            color: {
              field: "type",
              mode: "categorical",
              palette: "categorical-a",
              domain: { kind: "categorical", values: ["Résidentiel", "Commercial"] },
              computedAt: "2026-09-27T10:00:00Z",
            },
          },
        },
      ],
    }),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findByText("Résidentiel");
  // MapLegend (dans MapView, derrière Suspense) peut monter après la légende
  // de symbologie (rendue par MapEditorPage lui-même, pas de Suspense) — même
  // sync point qu'ailleurs dans ce fichier ("Layer name appears in both
  // LayersPanel and MapLegend; use findAllByText as sync point").
  // `MapView` est chargée en lazy (Suspense) : "Zones" apparaît d'abord dans
  // `LayersPanel` (pas de Suspense), pas une preuve que `MapView`/`MapLegend`
  // ont déjà monté. Sync réel utilisé ailleurs dans ce fichier : attendre
  // l'instance MapLibre mockée créée par `MapView` une fois résolue.
  await waitFor(() => expect(mapInstances).toHaveLength(1));

  // MapView affiche déjà MapLegend (noms de couches) ancrée bottom-2 left-2
  // dans ce même conteneur (MapLegend.tsx) — hideLegend n'est passé que sur
  // le chemin export, pas ici. Le panneau de légendes de symbologie doit donc
  // occuper un coin distinct, pas le même point d'ancrage (défaut trouvé en
  // revue Tâche 35 : les deux se superposaient exactement en bottom-2 left-2).
  const layerNameLegend = container.querySelector("ul.absolute");
  expect(layerNameLegend).not.toBeNull();
  expect(layerNameLegend).toHaveClass("bottom-2", "left-2");

  const symbologyPanel = screen.getByTestId("map-symbology-legend-panel");
  expect(symbologyPanel).not.toHaveClass("left-2");
  expect(symbologyPanel).toHaveClass("bottom-2", "right-2");
});

test("bloque la navigation après une modification non enregistrée de la carte (SP-B6c)", async () => {
  renderEditorWithNavigation({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  await userEvent.click(screen.getByRole("link", { name: "Retour au catalogue" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    t("navigation.unsavedChangesMessage"),
  );
});

test("ne bloque pas la navigation juste après une sauvegarde réussie (SP-B6c)", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditorWithNavigation({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("link", { name: "Retour au catalogue" }));
  expect(await screen.findByText("Catalogue")).toBeInTheDocument();
});
