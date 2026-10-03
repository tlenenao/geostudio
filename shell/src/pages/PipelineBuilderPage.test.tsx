// SPDX-License-Identifier: Apache-2.0
import { ApiError } from "../api/ApiError";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider, useParams } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import * as ToastPrimitive from "@radix-ui/react-toast";
import type {
  InstanceInfo,
  Item,
  ItemClient,
  PipelineOpsCatalog,
  PipelinePayload,
} from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ToastProvider } from "../ui/kit/ToastProvider";
import { OWNER_PERMISSIONS, READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { PipelineBuilderPage, decideUndoRedoShortcut } from "./PipelineBuilderPage";
import { t } from "../i18n";

// PipelineBuilderPage renders PipelineNodeInspector -> PipelinePreviewPanel, which can mount
// PipelinePreviewMap (SP-15g Task 16) -> maplibre-gl. jsdom lacks URL.createObjectURL, which
// maplibre-gl calls at import time; same stub as PipelinePreviewPanel.test.tsx/
// PipelinePreviewMap.test.tsx.
vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});

// PipelineBuilderPage calls useAuth() for `username` on save — same mock as
// shell/src/shell/NewItemButton.test.tsx, needed because the real hook calls
// react-oidc-context's useAuth(), which throws without an AuthProvider.
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

// A `class`, not `vi.fn().mockImplementation(() => ({...}))`: an arrow
// function can never be a valid constructor, and `new ResizeObserver(...)`
// now throws under it (silently tolerated before a vitest major bump) —
// same fix as EChart.test.tsx.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. PipelineBuilderPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests existants de ce fichier, qui n'affirment pas
// sur la largeur. vi.unstubAllGlobals() en afterEach existait déjà ici
// avant ce plan (contrairement à MapEditorPage.test.tsx/
// DatasetEditPage.test.tsx/AppBuilderPage.test.tsx) — préservé tel quel.
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
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  stubMatchMedia(false);
});
afterEach(() => vi.unstubAllGlobals());

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": {
    kind: "reader",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  },
  "transform.filter": {
    kind: "transform",
    paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] },
  },
  "writer.collection": {
    kind: "writer",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  },
};

// Item par défaut d'un pipeline persisté (`pk="p-1"`, seul utilisé par les
// tests "persisted mode" de ce fichier) : permissions.write=true, comme
// avant l'introduction du garde SP-42/F-shell-pages-04 (aucun de ces tests
// n'affirme sur des permissions restreintes — celui qui le fait le
// surcharge explicitement via `overrides`).
const OWNED_PIPELINE_ITEM: Item = {
  pk: "p-1",
  resourceType: "pipeline",
  title: "Nettoyer villes",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-p1",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

// `route` : chemin (avec éventuelle chaîne de requête) que voit
// useUrlSyncedState via useSearchParams (SP-B9c, même patron que la Tâche
// 17 sur AppBuilderPage.test.tsx) — défaut "/" sans paramètre, donc tous
// les tests existants de ce fichier (écrits avant SP-B9c) restent inchangés.
function renderPage(pk: string | null, overrides: Partial<ItemClient> = {}, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    getItem: vi.fn().mockResolvedValue(OWNED_PIPELINE_ITEM),
    // D09 : la garde ajoutée sur PipelineBuilderPage lit useInstanceInfo(),
    // dont le repli par défaut (ItemClient de test sans getInstanceInfo)
    // est etlEnabled: false (cf. useInstanceInfo() dans items.hooks.ts) —
    // sans ce mock par défaut, TOUS les tests existants de ce fichier
    // afficheraient désormais le message de désactivation au lieu du
    // builder. Seul le test D09 ci-dessous le surcharge à etlEnabled: false.
    getInstanceInfo: () =>
      Promise.resolve({
        readOnly: false,
        etlEnabled: true,
        exportEnabled: false,
        appExportEnabled: false,
        tileset3dEnabled: false,
        terrain3dEnabled: false,
        copilotEnabled: false,
        adminToolsEnabled: false,
        quotasEnabled: false,
      }),
    ...overrides,
  };
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <QueryClientProvider client={qc}>
            <ItemClientProvider client={client as ItemClient}>
              <ToastProvider>
                <PipelineBuilderPage pk={pk} initialTitle="Nettoyer villes" />
              </ToastProvider>
            </ItemClientProvider>
          </QueryClientProvider>
        ),
      },
    ],
    { initialEntries: [route] },
  );
  const { unmount } = render(
    <ToastPrimitive.Provider>
      <RouterProvider router={router} />
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
  return { client, unmount };
}

// Harnais dédié aux tests de garde de navigation (SP-B6d, même patron que
// Task 27/MapEditorPage) : un lien factice vers une autre page suffit, le
// chrome réel (AppLayout/TopBar) est hors périmètre de ce fichier.
function renderPageWithNavigation(
  pk: string | null,
  overrides: Partial<ItemClient> = {},
  route = "/",
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    getItem: vi.fn().mockResolvedValue(OWNED_PIPELINE_ITEM),
    getInstanceInfo: () =>
      Promise.resolve({
        readOnly: false,
        etlEnabled: true,
        exportEnabled: false,
        appExportEnabled: false,
        tileset3dEnabled: false,
        terrain3dEnabled: false,
        copilotEnabled: false,
        adminToolsEnabled: false,
        quotasEnabled: false,
      }),
    ...overrides,
  };
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <QueryClientProvider client={qc}>
            <ItemClientProvider client={client as ItemClient}>
              <ToastProvider>
                <Link to="/autre">Autre page</Link>
                <PipelineBuilderPage pk={pk} initialTitle="Nettoyer villes" />
              </ToastProvider>
            </ItemClientProvider>
          </QueryClientProvider>
        ),
      },
      { path: "/autre", element: <p>Autre page ouverte</p> },
    ],
    { initialEntries: [route] },
  );
  return render(
    <ToastPrimitive.Provider>
      <RouterProvider router={router} />
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

// Harnais pour le round-trip réel de création (SP-B6d) : mêmes routes que
// shell/src/shell/routes.tsx (`/pipelines/new` -> pk=null,
// `/pipelines/:pk/edit` -> pk réel) pour vérifier que la redirection interne
// post-création (onSave, pk === null) n'est pas bloquée par la garde.
function renderNewPipelineRoutes(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    getItem: vi.fn().mockResolvedValue(OWNED_PIPELINE_ITEM),
    getInstanceInfo: () =>
      Promise.resolve({
        readOnly: false,
        etlEnabled: true,
        exportEnabled: false,
        appExportEnabled: false,
        tileset3dEnabled: false,
        terrain3dEnabled: false,
        copilotEnabled: false,
        adminToolsEnabled: false,
        quotasEnabled: false,
      }),
    ...overrides,
  };
  function EditRoute() {
    const { pk } = useParams();
    return <PipelineBuilderPage pk={pk!} />;
  }
  const router = createMemoryRouter(
    [
      { path: "/pipelines/new", element: <PipelineBuilderPage pk={null} /> },
      { path: "/pipelines/:pk/edit", element: <EditRoute /> },
    ],
    { initialEntries: ["/pipelines/new"] },
  );
  return render(
    <ToastPrimitive.Provider>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </ItemClientProvider>
      </QueryClientProvider>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

test("unsaved mode: Enregistrer is disabled on an empty graph", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
});

// D09 : sans la garde ajoutée sur useInstanceInfo(), opsQuery termine en
// erreur (404, routes non montées par core/app/pipelines/routes.py quand
// CORE_ETL_ENABLED=false) et `!opsQuery.data` reste vrai pour toujours —
// spinner infini sur `t("common.loading")` (piège trouvé par lecture du
// code, pas seulement en le lançant contre une vraie instance désactivée).
test("unsaved mode: affiche un message de désactivation au lieu du spinner infini quand CORE_ETL_ENABLED est faux (D09)", async () => {
  renderPage(null, {
    getInstanceInfo: () =>
      Promise.resolve({
        readOnly: false,
        etlEnabled: false,
        exportEnabled: false,
        appExportEnabled: false,
        tileset3dEnabled: false,
        terrain3dEnabled: false,
        copilotEnabled: false,
        adminToolsEnabled: false,
        quotasEnabled: false,
      }),
    // Simule des routes pipeline non montées côté cœur : jamais résolu,
    // pour prouver que la garde D09 n'attend pas opsQuery.
    getPipelineOps: () => new Promise(() => {}),
  });
  expect(
    await screen.findByText(
      "Fonction indisponible sur cette instance, contactez votre administrateur.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Chargement…")).not.toBeInTheDocument();
});

// D09, revue finale (Important) : la garde ci-dessus ne masque le message de
// désactivation QUE tant que instanceQuery charge — elle ne masque pas le
// BUILDER complet pendant ce même intervalle. instanceQuery (/v1/instance) et
// opsQuery (/v1/pipelines/ops) sont deux requêtes indépendantes sans garantie
// d'ordre : si opsQuery résout avant instanceQuery, les deux gardes
// s'esquivent (`!instanceQuery.isLoading && !etlEnabled` est faux tant que
// isLoading est vrai ; `opsQuery.isLoading || !opsQuery.data` est faux car
// les données sont déjà là) et le builder interactif s'affiche sur une
// instance où ETL est en réalité désactivé — avant de basculer vers le
// message de désactivation une fois instanceQuery résolu. Ce test résout
// opsQuery immédiatement mais retient la résolution de getInstanceInfo pour
// prouver que rien d'interactif (ni le builder, ni son spinner générique)
// n'apparaît avant qu'instanceQuery ait résolu.
test("unsaved mode: n'affiche jamais le builder tant que /v1/instance n'a pas résolu, même si opsQuery a déjà résolu (D09 race)", async () => {
  let resolveInstance!: (info: InstanceInfo) => void;
  let opsSettled = false;
  renderPage(null, {
    getPipelineOps: () => Promise.resolve(CATALOG).then((v) => ((opsSettled = true), v)),
    getInstanceInfo: () =>
      new Promise<InstanceInfo>((resolve) => {
        resolveInstance = resolve;
      }),
  });

  // On attend l'état réel de la promesse de getPipelineOps (opsSettled),
  // jamais un nombre de ticks arbitraire : getInstanceInfo reste
  // délibérément non résolue, donc opsSettled passant à true prouve que
  // opsQuery a bel et bien résolu avant instanceQuery — la course que ce
  // test vise à reproduire, constatée plutôt que supposée.
  await waitFor(() => expect(opsSettled).toBe(true));
  expect(screen.queryByText("reader.collection")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Fonction indisponible sur cette instance, contactez votre administrateur."),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");

  await act(async () => {
    resolveInstance({
      readOnly: false,
      etlEnabled: false,
      exportEnabled: false,
      appExportEnabled: false,
      tileset3dEnabled: false,
      terrain3dEnabled: false,
      copilotEnabled: false,
      adminToolsEnabled: false,
      quotasEnabled: false,
    });
  });
  expect(
    await screen.findByText(
      "Fonction indisponible sur cette instance, contactez votre administrateur.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("reader.collection")).not.toBeInTheDocument();
});

test("unsaved mode: Aperçu and Exécuter are absent (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Exécuter" })).not.toBeInTheDocument();
});

// REV-060 : clicking a palette entry must add a node to the canvas — the
// keyboard/click fallback to drag-and-drop. Before this fix, PipelinePalette
// rendered a non-interactive <div draggable>, so this click was a no-op and
// the op text appeared exactly once (the palette entry itself).
//
// I5, final review: Task 12 ("recently used ops") made the same click
// handler also call recordUse(op), which renders a second static copy of
// "reader.collection" in "Récemment utilisés" regardless of whether the node
// was actually added to the canvas — `length > 1` no longer falsifies a
// broken onAdd/onDropOnCanvas wiring, since recordUse alone already gets to
// 2. The canvas-added node (title === op, PipelineBuilderPage.onDropOnCanvas)
// renders TWO further matches — its title div and its op-label div
// (PipelineCanvas.tsx's PipelineNodeBox renders both `node.title ?? node.op`
// and `node.op`, and here they're the same string) — so exactly 4 total
// (palette entry + recent-ops entry + node title + node op label) proves the
// node was truly added; a no-op onAdd would stall at 2.
test("unsaved mode: clicking a palette entry adds a node to the canvas", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getAllByText("reader.collection")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  await waitFor(() => expect(screen.getAllByText("reader.collection")).toHaveLength(4));
});

test("unsaved mode: Annuler reverts the last palette-added node", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  await waitFor(() => expect(screen.getAllByText("reader.collection").length).toBeGreaterThan(1));
  // useUndoableDraft's 400ms coalescing window means canUndo only flips
  // true once it elapses after setDraft — poll for it instead of asserting
  // immediately (brief's plan assumed the preceding waitFor already
  // outlasted the window; measured, it resolves as soon as the node
  // renders, well under 400ms).
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  // After undo, there are still 2 instances: one in Sources, one in Récemment utilisés
  // (the recent ops list persists independently of the canvas).
  await waitFor(() => expect(screen.getAllByText("reader.collection")).toHaveLength(2));
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeEnabled();
});

test("unsaved mode: Annuler and Rétablir start disabled", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
});

test("persisted mode: loads the existing graph and shows Exécuter", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
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
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-1",
        status: "succeeded",
        startedAt: "2026-08-06T10:00:00Z",
        finishedAt: "2026-08-06T10:00:02Z",
        error: null,
        nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 7 } },
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
});

test("persisted mode: Enregistrer calls savePipelineConfig with the current graph", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledWith("p-1", payload));
});

test("persisted mode: toggling planification then saving includes refreshPolicy in the saved payload", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() =>
    expect(screen.getByLabelText("Planification automatique")).toBeInTheDocument(),
  );

  await userEvent.click(screen.getByLabelText("Planification automatique"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(savePipelineConfig).toHaveBeenCalledWith("p-1", {
      ...payload,
      refreshPolicy: { enabled: true, cron: "*/15 * * * *" },
    }),
  );
});

test("persisted mode: loads an existing refreshPolicy pre-filled into the editor", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
    refreshPolicy: { enabled: true, cron: "0 2 * * *" },
  };
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload) });
  await waitFor(() => expect(screen.getByLabelText("Planification automatique")).toBeChecked());
  expect(screen.getByLabelText("Mode de planification")).toHaveValue("daily");
  expect(screen.getByLabelText("Heure d'exécution")).toHaveValue("02:00");
});

test("unsaved mode: no schedule editor before the first save (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByLabelText("Planification automatique")).not.toBeInTheDocument();
});

test("persisted mode: a rejected save shows the server error message", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi
    .fn()
    .mockRejectedValue(new Error("invalid cron expression: 'nope'"));
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    savePipelineConfig,
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("invalid cron expression"),
  );
});

test("persisted mode: affiche le panneau d'historique", async () => {
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve({ nodes: [], edges: [] }),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});

test("unsaved mode: no history panel before the first save (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByText("Historique")).not.toBeInTheDocument();
});

test("unsaved mode: graph-level errors are shown in a banner", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByText("Le pipeline doit contenir au moins une source.")).toBeInTheDocument();
  expect(screen.getByText("Le pipeline doit contenir au moins une écriture.")).toBeInTheDocument();
});

test("unsaved mode: shows a reason why Enregistrer is disabled", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(
    screen.getByText("Le graphe contient des erreurs à corriger avant l'enregistrement."),
  ).toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Étapes/Canevas/Propriétés avec Canevas actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage(null);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Étapes", "Canevas", "Propriétés"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Canevas");
});

test("persisted mode: verrouille Enregistrer quand permissions.write est false (SP-42/F-shell-pages-04)", async () => {
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    // Sans ce mock, getPipelineConfig est absent du client partiel : l'appel
    // lève synchronement, configQuery devient isError, et le nouveau garde
    // SP-42/F-shell-pages-05 masquerait la palette que ce test vérifie —
    // sans rapport avec ce que ce test veut exercer (permissions.write).
    getPipelineConfig: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
  });
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  const saveButton = screen.getByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeDisabled();
  expect(
    screen.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeInTheDocument();
});

// I1, final review: preview now requires action="write" server-side (Task 2 —
// the route accepts an arbitrary draft graph body and connector secrets are
// tenant-scoped, not pipeline-scoped), but the panel was still rendered
// unconditionally whenever a node was selected, regardless of `readOnly`. A
// read-only-shared user selecting any node got a permanent "Aperçu
// indisponible" alert and fired a 403 POST on every keystroke (the preview
// query key includes the live draft). The test above uses an empty graph, so
// no node can ever be selected there — this variant seeds a real node so it
// can be clicked, then proves the panel (and its underlying query) is absent.
test("persisted mode: n'affiche pas l'aperçu pour un utilisateur en lecture seule, même nœud sélectionné (I1)", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const previewPipeline = vi.fn().mockResolvedValue([{ id: 1 }]);
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getPipelineConfig: vi.fn().mockResolvedValue(payload),
    previewPipeline,
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  fireEvent.click(screen.getByText("Villes"));
  await waitFor(() => expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument());
  expect(screen.queryByText("Aperçu indisponible.")).not.toBeInTheDocument();
  expect(screen.queryByText("Chargement de l'aperçu…")).not.toBeInTheDocument();
  expect(previewPipeline).not.toHaveBeenCalled();
});

test("persisted mode: reste en chargement tant que l'item n'est pas résolu, ne verrouille pas Enregistrer par erreur (SP-42, revue finale, point 2, Critical)", async () => {
  // Graphe valide (reader -> writer) : un graphe vide désactiverait
  // Enregistrer pour une tout autre raison (isPipelineValid), confondant ce
  // test avec la validation locale plutôt qu'avec permissions.write.
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  let resolveItem!: (item: Item) => void;
  let resolvePipelineConfig!: (payload: PipelinePayload) => void;
  renderPage("p-1", {
    getItem: vi.fn(
      () =>
        new Promise<Item>((resolve) => {
          resolveItem = resolve;
        }),
    ),
    getPipelineConfig: vi.fn(
      () =>
        new Promise<PipelinePayload>((resolve) => {
          resolvePipelineConfig = resolve;
        }),
    ),
  });

  // Résout le config de pipeline SEUL, jamais l'item : avant le correctif,
  // la page rendait déjà le builder complet avec Enregistrer verrouillé
  // (permissions.write lu sur `undefined` => false) au lieu de rester en
  // "Chargement…" comme son jumeau DatasetEditPage.tsx.
  await act(async () => {
    resolvePipelineConfig(payload);
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");

  await act(async () => {
    resolveItem(OWNED_PIPELINE_ITEM);
  });
  const saveButton = await screen.findByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeEnabled();
});

test("persisted mode: une config qui échoue à charger affiche une alerte et n'écrase pas l'existant (SP-42/F-shell-pages-05)", async () => {
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", {
    getPipelineConfig: vi.fn().mockRejectedValue(new ApiError(403)),
    savePipelineConfig,
    // Isole le défaut sous test : sans ce mock, ConfigHistoryPanel affiche
    // aussi un role="alert" (« Impossible de charger l'historique »),
    // rendant le premier findByRole("alert") vrai pour la mauvaise raison
    // (piège de méthode signalé par la falsification F-shell-pages-05).
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Accès refusé");
  expect(screen.queryByText("reader.collection")).not.toBeInTheDocument();
  expect(savePipelineConfig).not.toHaveBeenCalled();
});

test("unsaved mode: pressing / focuses the palette search field", async () => {
  const user = userEvent.setup();
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await user.keyboard("/");
  expect(screen.getByRole("searchbox", { name: "Rechercher une opération" })).toHaveFocus();
});

test("unsaved mode: pressing / while typing in a text field does not steal focus", async () => {
  const user = userEvent.setup();
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await user.click(screen.getByRole("searchbox", { name: "Rechercher une opération" }));
  await user.type(screen.getByRole("searchbox", { name: "Rechercher une opération" }), "a/b");
  expect(screen.getByRole("searchbox", { name: "Rechercher une opération" })).toHaveValue("a/b");
});

test("unsaved mode: Ajouter une zone adds an editable note to the canvas", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));
  expect(screen.getByLabelText("Étiquette de la zone")).toHaveValue("Nouvelle zone");
});

test("persisted mode: saving includes notes added on the canvas", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(savePipelineConfig).toHaveBeenCalledWith(
      "p-1",
      expect.objectContaining({
        notes: [expect.objectContaining({ label: "Nouvelle zone" })],
      }),
    ),
  );
});

// Revue finale, follow-up (f8169238) : `totalNodes={draft.nodes.length}` était
// passé sans condition à PipelineRunPanel, y compris quand `draft` a divergé
// de la config sauvegardée (isDraftStale, déjà calculé pour
// PipelinePreviewPanel ci-dessus mais jamais réutilisé ici). `runPipeline`
// exécute toujours la DERNIÈRE config sauvegardée, jamais le brouillon — donc
// un brouillon avec des nœuds ajoutés/supprimés sans sauvegarde affichait une
// progression N/M fausse par rapport au run réellement en cours.
test("persisted mode: masque la progression N/M nœuds quand le brouillon a des nœuds non sauvegardés", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-1",
        status: "running",
        startedAt: "2026-08-06T10:00:00Z",
        finishedAt: null,
        error: null,
        nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 10 } },
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  // Ajoute un nœud au brouillon sans sauvegarder : draft.nodes.length (3)
  // diverge maintenant de configQuery.data.nodes.length (2), isDraftStale
  // devient vrai.
  await userEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  await waitFor(() => expect(screen.getAllByText("reader.collection").length).toBeGreaterThan(1));
  await waitFor(() => expect(screen.getByText("En cours")).toBeInTheDocument());
  expect(screen.queryByText(/\/ \d+ nœuds/)).not.toBeInTheDocument();
});

test("persisted mode: affiche la progression N/M nœuds quand le brouillon n'a pas divergé de la config sauvegardée", async () => {
  const payload: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", {
    getPipelineConfig: () => Promise.resolve(payload),
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-1",
        status: "running",
        startedAt: "2026-08-06T10:00:00Z",
        finishedAt: null,
        error: null,
        nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 10 } },
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("En cours")).toBeInTheDocument());
  expect(screen.getByText("1 / 2 nœuds")).toBeInTheDocument();
});

// Revue finale Vague B, I4 : la condition de masquage reposait sur
// `isDraftStale` (comparaison de RÉFÉRENCE avec configQuery.data), qui ne
// redevient jamais fausse après une sauvegarde — le refetch qui suit
// renvoie un nouvel objet. La progression N/M disparaissait donc pour le
// reste de la session dans le parcours normal éditer → enregistrer → lancer.
test("persisted mode: réaffiche la progression N/M nœuds après une sauvegarde", async () => {
  const saved: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
        title: "Villes",
      },
      {
        id: "f1",
        kind: "transform",
        op: "transform.filter",
        x: 150,
        y: 0,
        params: { expr: "pop > 0" },
        title: "Filtre",
      },
      {
        id: "w1",
        kind: "writer",
        op: "writer.collection",
        x: 300,
        y: 0,
        params: { collectionId: "villes_propres" },
        title: "Écriture",
      },
    ],
    edges: [
      { id: "e1", from: "r1", to: "f1" },
      { id: "e2", from: "f1", to: "w1" },
    ],
  };
  let current = saved;
  // Chaque lecture renvoie un NOUVEL objet (comme un vrai refetch réseau).
  const getPipelineConfig = vi.fn(() => Promise.resolve(structuredClone(current)));
  const savePipelineConfig = vi.fn((_pk: string, payload: PipelinePayload) => {
    current = payload;
    return Promise.resolve(undefined);
  });
  renderPage(
    "p-1",
    {
      getPipelineConfig,
      savePipelineConfig,
      getPipelineRuns: vi.fn().mockResolvedValue([
        {
          id: "run-1",
          status: "running",
          startedAt: "2026-08-06T10:00:00Z",
          finishedAt: null,
          error: null,
          nodeStats: { r1: { nodeId: "r1", op: "reader.collection", rowCount: 10 } },
        },
      ]),
    },
    "/?node=f1",
  );
  await waitFor(() => expect(screen.getByText("1 / 3 nœuds")).toBeInTheDocument());
  // Édition réelle (le brouillon devient « non sauvegardé ») : progression masquée.
  await userEvent.type(await screen.findByLabelText("expr"), "0");
  await waitFor(() => expect(screen.queryByText(/\/ \d+ nœuds/)).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalled());
  // Le refetch post-sauvegarde a bien eu lieu (nouvelle référence d'objet).
  await waitFor(() => expect(getPipelineConfig.mock.calls.length).toBeGreaterThan(1));
  expect(await screen.findByText("1 / 3 nœuds")).toBeInTheDocument();
});

// SP-B9c : `selectedNodeId` passe de useState à useUrlSyncedState (Tâche 16),
// même patron que la Tâche 17 sur AppBuilderPage (`?selected=`). La classe
// "ring-2 ring-accent" posée par PipelineCanvas.tsx (PipelineNodeBox, prop
// `selected`) sur le conteneur direct du titre du nœud est la seule preuve
// DOM que CE nœud précis est le nœud sélectionné (pas seulement "un nœud
// est sélectionné quelque part") — nécessaire ici parce que "Nœud
// sélectionné" seul n'identifie pas lequel des deux nœuds du payload est
// visé.
const TWO_NODE_PAYLOAD: PipelinePayload = {
  nodes: [
    {
      id: "r1",
      kind: "reader",
      op: "reader.collection",
      x: 0,
      y: 0,
      params: { collectionId: "villes" },
      title: "Villes",
    },
    {
      id: "w1",
      kind: "writer",
      op: "writer.collection",
      x: 300,
      y: 0,
      params: { collectionId: "villes_propres" },
      title: "Écriture",
    },
  ],
  edges: [{ id: "e1", from: "r1", to: "w1" }],
};

function isHighlighted(label: string): boolean {
  const box = screen.getByText(label).closest("div.relative");
  return (box?.className ?? "").includes("ring-2");
}

test("restaure le nœud sélectionné depuis l'URL après un remount (simule un rechargement)", async () => {
  const { unmount } = renderPage(
    "p-1",
    { getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD) },
    "/pipelines/p-1/edit?node=r1",
  );
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument();
  expect(isHighlighted("Villes")).toBe(true);
  expect(isHighlighted("Écriture")).toBe(false);
  unmount();

  // Remonte depuis zéro (nouveau QueryClient, nouveau MemoryRouter) avec la
  // même URL : si la sélection ne survivait que dans un useState local, ce
  // second rendu partirait de `null`. Prouve qu'elle est bien portée par
  // l'URL, pas par un état React qui aurait par coïncidence survécu.
  renderPage(
    "p-1",
    { getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD) },
    "/pipelines/p-1/edit?node=r1",
  );
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument();
  expect(isHighlighted("Villes")).toBe(true);
  expect(isHighlighted("Écriture")).toBe(false);
});

// Gap signalé par le relecteur de la Tâche 16 (cast non vérifié de la
// valeur brute de l'URL) : PipelineBuilderPage.tsx a déjà un garde-fou
// équivalent à celui trouvé sur AppBuilderPage (Tâche 17, findings
// C2/M2) — `const selectedNode = draft.nodes.find((n) => n.id ===
// selectedNodeId) ?? null;` (ligne ~184) ne retient `selectedNode` que
// s'il désigne un nœud qui existe réellement dans `draft.nodes` ; tout le
// reste du composant (inspecteur, panneau d'aperçu) est gardé derrière
// `selectedNode && …`, et PipelineCanvas ne met en évidence que les nœuds
// dont l'id réel correspond — un id inconnu ne correspond simplement à
// aucun nœud rendu. Ce test vérifie que ce garde-fou tient quand la valeur
// suspecte vient de l'URL (id de nœud qui n'a jamais existé), sans qu'il
// ait fallu ajouter de nouvelle logique de repli.
test("un id de nœud inconnu dans l'URL n'affiche aucune sélection et ne casse rien (garde-fou pré-existant)", async () => {
  renderPage(
    "p-1",
    { getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD) },
    "/pipelines/p-1/edit?node=nœud-fantôme-jamais-vu",
  );
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.queryByText("Nœud sélectionné")).not.toBeInTheDocument();
  expect(isHighlighted("Villes")).toBe(false);
  expect(isHighlighted("Écriture")).toBe(false);

  // Reste utilisable ensuite : une sélection réelle par clic fonctionne
  // normalement, l'id fantôme de l'URL n'a rien verrouillé.
  fireEvent.click(screen.getByText("Villes"));
  await waitFor(() => expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument());
  expect(isHighlighted("Villes")).toBe(true);
});

test("bloque la navigation après une modification non enregistrée du pipeline (SP-B6d)", async () => {
  renderPageWithNavigation("p-1", { getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD) });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));

  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    t("navigation.unsavedChangesMessage"),
  );
});

test("ne bloque pas la navigation juste après une sauvegarde réussie (SP-B6d)", async () => {
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPageWithNavigation("p-1", {
    getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD),
    savePipelineConfig,
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalled());

  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));
  expect(await screen.findByText("Autre page ouverte")).toBeInTheDocument();
});

// SP-B6d, risque signalé au brief : sélectionner un nœud (selectedNodeId,
// SP-B9c) navigue via useUrlSyncedState -> setSearchParams, même pathname —
// ne doit jamais déclencher la garde, même brouillon non enregistré.
test("sélectionner un nœud (URL interne, même pathname) ne déclenche pas la garde même brouillon non enregistré", async () => {
  renderPageWithNavigation("p-1", { getPipelineConfig: () => Promise.resolve(TWO_NODE_PAYLOAD) });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));

  fireEvent.click(screen.getByText("Villes"));

  await waitFor(() => expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument());
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

// SP-B6d, risque explicitement signalé au brief : le round-trip réel de
// création (/pipelines/new -> Enregistrer -> redirection interne vers
// /pipelines/{pk}/edit, un changement de pathname RÉEL) exécute
// `setHasUnsavedChanges(false)` puis `navigate(...)` de façon synchrone dans
// le même callback — vérifié empiriquement plutôt que supposé sûr, car nul
// autre éditeur de ce lot n'a ce patron (redirection interne juste après un
// succès de sauvegarde).
// Catalogue minimal (aucun champ requis) : un unique clic sur chaque bouton
// suffit à obtenir un graphe valide (≥1 source + ≥1 écriture, aucune arête
// requise hors acceptsSecondaryInput) — ce test porte sur la garde de
// navigation, pas sur la mécanique de validation de graphe.
const MINIMAL_CATALOG: PipelineOpsCatalog = {
  "reader.x": { kind: "reader", paramsSchema: { properties: {} } },
  "writer.x": { kind: "writer", paramsSchema: { properties: {} } },
};

test("le round-trip de création (pk=null -> Enregistrer -> redirection) n'affiche pas la boîte de confirmation (SP-B6d)", async () => {
  const createPipelineItem = vi.fn().mockResolvedValue({
    pk: "new-1",
    resourceType: "pipeline",
    title: "Nettoyer villes",
    abstract: "",
    owner: "alice",
    thumbnailUrl: null,
    date: "2026-01-01",
    configId: "cfg-new-1",
    isPublished: false,
    keywords: [],
    permissions: OWNER_PERMISSIONS,
    license: "",
    language: "fr",
  } satisfies Item);
  // React Flow ne rend les nœuds qu'une fois mesurés : stubs locaux (cf.
  // PipelineCanvas.test.tsx), retirés en fin de test.
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 160 });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 48 });
  class SizedResizeObserver {
    constructor(private readonly callback: ResizeObserverCallback) {}
    observe(target: Element) {
      const size = [{ inlineSize: 160, blockSize: 48 }];
      this.callback(
        [
          {
            target,
            contentRect: { width: 160, height: 48 },
            borderBoxSize: size,
            contentBoxSize: size,
            devicePixelContentBoxSize: size,
          } as unknown as ResizeObserverEntry,
        ],
        this as unknown as ResizeObserver,
      );
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", SizedResizeObserver);
  vi.stubGlobal(
    "DOMMatrixReadOnly",
    class {
      m22 = 1;
    },
  );
  renderNewPipelineRoutes({
    createPipelineItem,
    getPipelineOps: () => Promise.resolve(MINIMAL_CATALOG),
  });

  await waitFor(() => expect(screen.getByText("reader.x")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "reader.x" }));
  await userEvent.click(screen.getByRole("button", { name: "writer.x" }));
  // j06-002 : un writer sans entrée n'est plus enregistrable — on relie les deux
  // nœuds via l'affordance de connexion au clic.
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis reader.x" }));
  fireEvent.click(screen.getAllByText("writer.x").at(-1)!);
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(createPipelineItem).toHaveBeenCalled());
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  // Démonte avant de retirer les stubs : React Flow mesure encore ses nœuds sinon.
  cleanup();
  Reflect.deleteProperty(HTMLElement.prototype, "offsetWidth");
  Reflect.deleteProperty(HTMLElement.prototype, "offsetHeight");
});

// D55 : le canevas de pipeline n'appliquait pas réellement la lecture seule —
// connecter/supprimer des nœuds restait possible (corrigé dans
// PipelineCanvas.tsx, cf. son propre fichier de test), et Undo/Redo/Ctrl+Z
// restaient actifs ici. `readOnly` est dérivé de `permissions.write` (ligne
// ~82).
//
// Revue finale Vague C (point 2) : ce test affirmait auparavant que l'ajout
// de nœud via la palette n'était PAS gardé par `readOnly` ("hors périmètre
// de cette tâche") et s'en servait pour amener `canUndo` à vrai, afin de
// prouver que Annuler/Rétablir/Ctrl+Z restent désactivés/inertes MÊME
// quand `canUndo` l'est. Ce trou est désormais fermé (onDropOnCanvas garde
// `readOnly` — cf. PipelineBuilderPage.tsx), donc `canUndo` ne peut plus
// jamais devenir vrai en lecture seule : la prémisse du test a changé, il a
// été réécrit en conséquence. `recordUse(op)` (PipelinePalette.tsx) reste
// hors de ce garde par construction (c'est un historique de clics purement
// local, jamais persisté dans le brouillon) — la palette affiche donc bien
// une deuxième occurrence du texte de l'op ("Récemment utilisés"), mais
// jamais les deux occurrences supplémentaires qu'un nœud réellement ajouté
// produirait (titre + libellé d'op sur le canevas, cf. le test "unsaved
// mode: clicking a palette entry adds a node to the canvas" plus haut, qui
// prouve que 4 occurrences == nœud ajouté).
test("persisted mode: lecture seule empêche l'ajout de nœud via la palette et garde Annuler/Rétablir désactivés (D55)", async () => {
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getPipelineConfig: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
  });
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getAllByText("reader.collection")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  // recordUse() seul fait passer le compte à 2 (palette + "Récemment
  // utilisés") — jamais à 4, qui prouverait qu'un nœud a été ajouté au
  // canevas malgré la lecture seule.
  await waitFor(() => expect(screen.getAllByText("reader.collection")).toHaveLength(2));
  // Dépasse la fenêtre de coalescing de 400ms (useUndoableDraft) : même
  // après ce délai, canUndo reste faux puisqu'aucune mutation du brouillon
  // n'a eu lieu.
  await new Promise((resolve) => setTimeout(resolve, 450));
  expect(screen.getAllByText("reader.collection")).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getAllByText("reader.collection")).toHaveLength(2);
});

// Revue finale Vague C (point 7, D55) : le test bout-en-bout ci-dessus ne
// peut plus amener `canUndo` à vrai en lecture seule (tous les points de
// mutation du brouillon sont désormais gardés) — il resterait vert que la
// garde `readOnly` de `decideUndoRedoShortcut` soit présente ou non
// (vérifié par falsification en revue finale : 4/4 tests D55 passent avec
// ou sans elle). Ce test-ci isole la fonction de décision et prouve
// directement qu'elle refuse Ctrl+Z en lecture seule, indépendamment de
// tout état `canUndo` — falsifié : retirer `if (readOnly) return null;`
// dans `decideUndoRedoShortcut` fait échouer ce test (`"undo"` au lieu de
// `null`), confirmé puis la garde restaurée.
test("decideUndoRedoShortcut : Ctrl+Z ne déclenche rien en lecture seule (D55)", () => {
  const ctrlZ = { key: "z", ctrlKey: true, metaKey: false, shiftKey: false };
  expect(decideUndoRedoShortcut(ctrlZ, false, true)).toBeNull();
  // Même événement, hors lecture seule : l'action est bien décidée (la
  // garde readOnly est le seul point qui distingue les deux cas).
  expect(decideUndoRedoShortcut(ctrlZ, false, false)).toBe("undo");
  // Ctrl+Shift+Z : redo, toujours refusé en lecture seule.
  const ctrlShiftZ = { key: "z", ctrlKey: true, metaKey: false, shiftKey: true };
  expect(decideUndoRedoShortcut(ctrlShiftZ, false, true)).toBeNull();
  expect(decideUndoRedoShortcut(ctrlShiftZ, false, false)).toBe("redo");
  // Un champ texte reste prioritaire sur toute décision, lecture seule ou non.
  expect(decideUndoRedoShortcut(ctrlZ, true, false)).toBeNull();
});

// Revue finale Vague C (point 2, D55) : nouveaux points de mutation fermés
// dans ce lot — root onDrop/onDropOnCanvas (ci-dessus, via la palette),
// onInsertOnEdge, le bouton "Ajouter une zone", PipelineNodeInspector.onChange
// et PipelineScheduleEditor sont désormais tous gardés par `readOnly`.
test("persisted mode: lecture seule désactive le bouton Ajouter une zone (D55)", async () => {
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getPipelineConfig: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
  });
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  const addNoteButton = screen.getByRole("button", { name: "Ajouter une zone" });
  expect(addNoteButton).toBeDisabled();
  await userEvent.click(addNoteButton);
  expect(screen.queryByLabelText("Étiquette de la zone")).not.toBeInTheDocument();
});

// Revue finale Vague C (point 2, D55) : PipelineNodeInspector reçoit
// désormais `readOnly` — ses contrôles doivent être désactivés, pas
// seulement leur `onChange` neutralisé côté PipelineBuilderPage
// (updateSelectedNodeParams), sans quoi un champ resterait visuellement
// modifiable pour un utilisateur en lecture seule (illusion silencieuse).
test("persisted mode: lecture seule désactive les paramètres du nœud sélectionné (D55)", async () => {
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getPipelineConfig: vi.fn().mockResolvedValue(TWO_NODE_PAYLOAD),
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  fireEvent.click(screen.getByText("Villes"));
  await waitFor(() => expect(screen.getByText("Nœud sélectionné")).toBeInTheDocument());
  expect(screen.getByLabelText("collectionId")).toBeDisabled();
});

// Revue finale Vague C (point 2, D55) : PipelineScheduleEditor reçoit
// désormais `readOnly` — la case "Planification automatique" doit rester
// désactivée pour un utilisateur en lecture seule.
test("persisted mode: lecture seule désactive la case de planification automatique (D55)", async () => {
  renderPage("p-1", {
    getItem: vi
      .fn()
      .mockResolvedValue({ ...OWNED_PIPELINE_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getPipelineConfig: vi.fn().mockResolvedValue(TWO_NODE_PAYLOAD),
  });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.getByLabelText("Planification automatique")).toBeDisabled();
});
