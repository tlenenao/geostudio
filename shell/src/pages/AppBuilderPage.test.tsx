// SPDX-License-Identifier: Apache-2.0
import { ApiError } from "../api/ApiError";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { useState } from "react";
import { createMemoryRouter, Link, RouterProvider, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS, READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { ToastProvider } from "../ui/kit/ToastProvider";
import { getWidget, registerWidget } from "../builder/registry";
import { AppBuilderPage } from "./AppBuilderPage";
import type { AuthState } from "../auth/useAuth";
import { t } from "../i18n";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "tanguy",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

vi.mock("html-to-image", () => ({
  toBlob: vi.fn().mockResolvedValue(new Blob(["x"], { type: "image/png" })),
}));

const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
};

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. AppBuilderPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests existants de ce fichier, qui n'affirment pas
// sur la largeur.
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

afterEach(() => {
  vi.unstubAllGlobals();
});

// Item par défaut de l'app "5" (seul pk utilisé par ce fichier) :
// permissions.write=true, comme avant l'introduction du garde
// SP-42/F-shell-pages-04 (aucun test existant n'affirme sur des permissions
// restreintes — celui qui le fait le surcharge explicitement).
const OWNED_APP_ITEM: Item = {
  pk: "5",
  resourceType: "app",
  title: "App",
  abstract: "",
  owner: "tanguy",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-5",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

// Sonde discrète de l'état réel de l'URL (via le même useSearchParams que
// useUrlSyncedState) : sert à vérifier que la réconciliation d'un
// `selectedId`/`activePageId` périmé (SP-19 findings C2/M2) se répercute
// vraiment sur l'URL elle-même, pas seulement sur l'affichage — un test qui
// ne regarderait que le DOM ne distinguerait pas "corrigé" de "jamais lu".
function SearchParamsProbe() {
  const [params] = useSearchParams();
  return <span data-testid="url-search">{params.toString()}</span>;
}

// `route` : chemin (avec éventuelle chaîne de requête) que voit
// useUrlSyncedState via useSearchParams. Par défaut "/", sans paramètre —
// tous les tests existants (écrits avant SP-B9b) ne portent aucune
// affirmation sur l'URL et restent inchangés.
//
// SP-B6d : `useDirtyGuard` (Tâche 26) s'appuie sur `useBlocker`, qui exige un
// data router (`createMemoryRouter`/`RouterProvider`) — un `<MemoryRouter>`
// déclaratif fait lever `useBlocker` à l'exécution (cf. Tâche 27). Seule la
// query string varie entre les appels existants (jamais le pathname) : une
// unique route "/" suffit à tous les couvrir.
function renderPage(client: Partial<ItemClient>, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    getItem: vi.fn().mockResolvedValue(OWNED_APP_ITEM),
    ...client,
  };
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <ToastPrimitive.Provider>
            <QueryClientProvider client={qc}>
              <ItemClientProvider client={merged as ItemClient}>
                <ToastProvider>
                  <AppBuilderPage pk="5" />
                </ToastProvider>
              </ItemClientProvider>
            </QueryClientProvider>
            <ToastPrimitive.Viewport />
            <SearchParamsProbe />
          </ToastPrimitive.Provider>
        ),
      },
    ],
    { initialEntries: [route] },
  );
  return render(<RouterProvider router={router} />);
}

// Harnais dédié aux tests de garde de navigation (SP-B6d, même patron que
// Task 27/MapEditorPage) : un lien factice vers une autre page suffit, le
// chrome réel (AppLayout/TopBar) est hors périmètre de ce fichier.
function renderPageWithNavigation(client: Partial<ItemClient>, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    getItem: vi.fn().mockResolvedValue(OWNED_APP_ITEM),
    ...client,
  };
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <ToastPrimitive.Provider>
            <QueryClientProvider client={qc}>
              <ItemClientProvider client={merged as ItemClient}>
                <ToastProvider>
                  <Link to="/autre">Autre page</Link>
                  <AppBuilderPage pk="5" />
                </ToastProvider>
              </ItemClientProvider>
            </QueryClientProvider>
            <ToastPrimitive.Viewport />
            <SearchParamsProbe />
          </ToastPrimitive.Provider>
        ),
      },
      { path: "/autre", element: <p>Autre page ouverte</p> },
    ],
    { initialEntries: [route] },
  );
  return render(<RouterProvider router={router} />);
}

test("adds a widget from the palette and saves the config", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items).toHaveLength(1);
  expect(saved.layout.items[0].widget).toBe("text");
});

test("sends the loaded version on save and keeps the one returned (P09.05)", async () => {
  const saveAppConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue({ ...config, baseVersion: 3 }),
    saveAppConfig,
  });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalledTimes(1));
  expect((saveAppConfig.mock.calls[0][1] as AppConfig).baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalledTimes(2));
  expect((saveAppConfig.mock.calls[1][1] as AppConfig).baseVersion).toBe(4);
});

test("shows a conflict message and reloads the latest version on a 412 (P09.05)", async () => {
  const saveAppConfig = vi.fn().mockRejectedValue(new ApiError(412, { detail: "stale" }));
  const getAppConfig = vi
    .fn()
    .mockResolvedValueOnce({ ...config, baseVersion: 1 })
    .mockResolvedValue({ ...config, baseVersion: 7 });
  renderPage({ getAppConfig, saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await screen.findByText(t("appBuilder.conflict"));
  await userEvent.click(screen.getByRole("button", { name: t("appBuilder.conflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("appBuilder.conflict"))).toBeNull());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalledTimes(2));
  expect((saveAppConfig.mock.calls[1][1] as AppConfig).baseVersion).toBe(7);
});

test("toggles interactions on and saves it with the app config", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByLabelText("Interactions automatiques (cross-filter)");
  expect(screen.getByLabelText("Interactions automatiques (cross-filter)")).not.toBeChecked();
  await userEvent.click(screen.getByLabelText("Interactions automatiques (cross-filter)"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.interactions).toBe("auto");
});

test("shows an error when loading fails", async () => {
  renderPage({ getAppConfig: vi.fn().mockRejectedValue(new Error("x")) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/erreur de chargement/i);
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
});

test("P22.09 : un 404 est « introuvable » (sans Réessayer), un 403 « accès refusé »", async () => {
  const { unmount } = renderPage({
    getAppConfig: vi.fn().mockRejectedValue(new ApiError(404)),
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
  unmount();
  renderPage({ getAppConfig: vi.fn().mockRejectedValue(new ApiError(403)) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/accès refusé/i);
});

test("adds a data source and persists it", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByRole("button", { name: "Ajouter une source" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.dataSources).toHaveLength(1);
});

test("composes an action between two widgets and persists it", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByRole("button", { name: "Filtre" });
  await userEvent.click(screen.getByRole("button", { name: "Filtre" }));
  await userEvent.click(screen.getByRole("button", { name: "Liste" }));

  const emitterSelect = screen.getByLabelText("Widget émetteur");
  const targetSelect = screen.getByLabelText("Widget cible");
  await userEvent.selectOptions(
    emitterSelect,
    within(emitterSelect).getByRole("option", { name: "Filtre" }),
  );
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(
    targetSelect,
    within(targetSelect).getByRole("option", { name: "Liste" }),
  );
  await userEvent.selectOptions(screen.getByLabelText("Action"), "setFilter");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.messages).toHaveLength(1);
  expect(saved.messages[0]).toMatchObject({ event: "changed", action: "setFilter" });
});

test("edits a position at the sm breakpoint and persists layouts.sm", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(
    await screen.findByRole("button", { name: "Éditer la disposition Mobile" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer Texte à droite" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0); // base untouched
  expect(saved.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
});

// REV-054 : PropsPanel n'avait pas de key par widget sélectionné, donc les
// états locaux transitoires d'un PropsPanel de widget (busy/erreur/mode
// avancé — MapSymbologyEditor/PopupEditor en particulier) fuyaient d'un
// widget à l'autre au changement de sélection dans le builder d'App
// lui-même, pas seulement dans LayoutEditor (widgets conteneurs) — même
// bug, deux sites à corriger, testés séparément.
function registerProbeWidgetOnce() {
  if (getWidget("probe")) return;
  registerWidget({
    type: "probe",
    label: "Sonde",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: () => {
      const [advanced, setAdvanced] = useState(false);
      return (
        <label>
          Mode avancé
          <input
            type="checkbox"
            checked={advanced}
            onChange={(e) => setAdvanced(e.target.checked)}
          />
        </label>
      );
    },
    Component: () => <div />,
  });
}

test("REV-054 : changer de widget sélectionné remonte PropsPanel (pas de fuite d'état local transitoire)", async () => {
  registerProbeWidgetOnce();
  const withTwoProbes: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "probe", x: 0, y: 0, w: 1, h: 1, props: {} },
        { id: "w2", widget: "probe", x: 1, y: 0, w: 1, h: 1, props: {} },
      ],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withTwoProbes) });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Sonde 1" }));
  await userEvent.click(screen.getByLabelText("Mode avancé"));
  expect(screen.getByLabelText("Mode avancé")).toBeChecked();

  await userEvent.click(screen.getByRole("button", { name: "Sélectionner Sonde 2" }));
  expect(screen.getByLabelText("Mode avancé")).not.toBeChecked();
});

test("edits the theme's primary color and persists it", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByLabelText("Couleur primaire");
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(screen.getByLabelText("Couleur primaire"), { target: { value: "#ff0000" } });
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.theme.colors.primary).toBe("#ff0000");
});

test("adds a variable and wires a Filtre action to it, then persists both", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByRole("button", { name: "Ajouter une variable" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  await userEvent.click(screen.getByRole("button", { name: "Filtre" }));

  const emitterSelect = screen.getByLabelText("Widget émetteur");
  const targetSelect = screen.getByLabelText("Widget cible");
  await userEvent.selectOptions(
    emitterSelect,
    within(emitterSelect).getByRole("option", { name: "Filtre" }),
  );
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(
    targetSelect,
    within(targetSelect).getByRole("option", { name: "Variable : variable_1" }),
  );
  await userEvent.selectOptions(screen.getByLabelText("Action"), "set");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.variables).toHaveLength(1);
  expect(saved.messages).toHaveLength(1);
  expect(saved.messages[0]).toMatchObject({
    event: "changed",
    action: "set",
    to: `var:${saved.variables[0].id}`,
  });
});

test("adds a second page and can switch back to editing the first", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Ajouter une page" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une page" }));
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir la page page-1" }));
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.pages).toHaveLength(2);
  expect(saved.pages![0].id).toBe("page-1");
  expect(saved.pages![0].layout.items).toHaveLength(1); // Texte landed on page 1
  expect(saved.pages![1].layout.items).toHaveLength(0); // page 2 untouched
});

// SP-19 final-branch-review fix pass, finding C2: `activePageId` is a plain
// useState, not part of the undo stack. Undoing "Ajouter une page" reverts
// the config (page removed) but left activePageId pointing at the
// now-nonexistent page — every subsequent edit (e.g. adding a widget)
// silently no-op'd because setPageLayout() returns the config unchanged for
// an unknown pageId. Mirrors the saveAppConfig assertion pattern of the
// Task 3 GridCanvas undo tests above.
test("undoing 'Ajouter une page' then adding a widget lands on a real page, not a stale one", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Ajouter une page" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une page" }));

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  // The widget must show up on the canvas actually being edited, not be
  // silently dropped.
  expect(screen.getAllByRole("button", { name: /^Sélectionner / })).toHaveLength(1);

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  const items = saved.pages ? saved.pages[0].layout.items : saved.layout.items;
  expect(items).toHaveLength(1);
  expect(items[0].widget).toBe("text");
});

test("captures a thumbnail and uploads it", async () => {
  const uploadThumbnail = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig: vi.fn().mockResolvedValue(undefined),
    uploadThumbnail,
  });
  await screen.findByRole("button", { name: "Capturer une miniature" });
  await userEvent.click(screen.getByRole("button", { name: "Capturer une miniature" }));
  await waitFor(() => expect(uploadThumbnail).toHaveBeenCalledWith("5", expect.any(File)));
});

test("disables Enregistrer and shows the error when a widget's visibleWhen is invalid", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.type(screen.getByLabelText("Condition d'affichage (visibleWhen)"), "vars.x ==");
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  expect(screen.getByRole("alert", { name: /condition d'affichage/i })).toBeInTheDocument();
  expect(saveAppConfig).not.toHaveBeenCalled();
});

test("promotes one data source to a shared dataset without touching its siblings", async () => {
  const withSources: AppConfig = {
    kind: "app",
    theme: {},
    messages: [],
    dataSources: [
      { id: "s1", type: "features", service: "core", layer: "parcs", query: {} },
      { id: "s2", type: "features", service: "core", layer: "routes", query: {} },
    ],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  const createDatasetItem = vi.fn().mockResolvedValue({
    pk: "ds-1",
    resourceType: "dataset",
    title: "parcs",
    abstract: "",
    owner: "tanguy",
    thumbnailUrl: null,
    date: "",
    configId: "1",
    isPublished: false,
  });
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(withSources),
    saveAppConfig,
    createDatasetItem,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });

  const promoteButton = await screen.findByRole("button", {
    name: "Promouvoir en jeu de données partagé s1",
  });
  await userEvent.click(promoteButton);

  await waitFor(() =>
    expect(createDatasetItem).toHaveBeenCalledWith({
      title: "parcs",
      owner: "tanguy",
      source: "collection",
      collectionId: "parcs",
    }),
  );
  await screen.findByText("Jeu de données partagé actif");

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;

  const s1 = saved.dataSources.find((s) => s.id === "s1");
  const s2 = saved.dataSources.find((s) => s.id === "s2");
  expect(s1).toMatchObject({ id: "s1", layer: "parcs", query: {}, datasetId: "ds-1" });
  expect(s2).toEqual({ id: "s2", type: "features", service: "core", layer: "routes", query: {} });
});

test("re-enables Enregistrer once the invalid visibleWhen is corrected", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x ==");
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  await userEvent.type(area, " 'a'");
  expect(screen.getByRole("button", { name: "Enregistrer" })).not.toBeDisabled();
});

test("a GridCanvas move can be undone with Ctrl+Z", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer Texte à droite" }));

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0);
});

test("Ctrl+Shift+Z redoes an undone GridCanvas move", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer Texte à droite" }));
  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeEnabled();

  await userEvent.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(1);
});

test("the remove button on GridCanvas removes the selected widget", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Supprimer Texte" }));
  expect(screen.queryByRole("button", { name: "Sélectionner Texte" })).not.toBeInTheDocument();
});

test("Backspace with a widget selected removes it, ignored while typing", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
  await userEvent.keyboard("{Backspace}");
  expect(screen.queryByRole("button", { name: "Sélectionner Texte" })).not.toBeInTheDocument();
});

describe("raccourcis de suppression (P10.03/05)", () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };

  test("Retour arrière dans un select du panneau ne supprime pas le widget", async () => {
    renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) });
    await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
    screen.getByLabelText("Widget émetteur").focus();
    await userEvent.keyboard("{Backspace}");
    expect(screen.getByRole("button", { name: "Sélectionner Texte" })).toBeInTheDocument();
  });

  test("Suppr en mode Aperçu ne supprime pas le widget resté sélectionné", async () => {
    renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) });
    await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
    await userEvent.click(screen.getByRole("button", { name: "Aperçu" }));
    document.body.focus();
    await userEvent.keyboard("{Delete}");
    await userEvent.click(screen.getByRole("button", { name: "Édition" }));
    expect(screen.getByRole("button", { name: "Sélectionner Texte" })).toBeInTheDocument();
  });
});

test("removing a widget prunes any ActionsPanel message wired to it", async () => {
  // La disparition visuelle de la ligne dans ActionsPanel ne prouve rien à
  // elle seule : `resolvesOnThisPage` (ActionsPanel.tsx) masque déjà tout
  // message dont from/to ne résout plus dans `items`, que `config.messages`
  // ait été purgé ou non (vérifié par falsification : la ligne disparaît de
  // l'affichage même quand la purge est désactivée). L'assertion qui compte
  // est sur l'objet réellement sauvegardé.
  const withMessage: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [{ id: "m1", from: "w1", event: "changed", to: "w2", action: "setFilter" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "filter", x: 0, y: 0, w: 4, h: 2, props: {} },
        { id: "w2", widget: "list", x: 4, y: 0, w: 4, h: 2, props: {} },
      ],
    },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withMessage), saveAppConfig });

  await screen.findByRole("button", { name: "Sélectionner Filtre" });
  expect(screen.getByText("Filtre.changed → Liste.setFilter")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Sélectionner Filtre" }));
  await userEvent.click(screen.getByRole("button", { name: "Supprimer Filtre" }));

  expect(screen.queryByText("Filtre.changed → Liste.setFilter")).not.toBeInTheDocument();
  expect(screen.getByText("Aucune action.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.messages).toEqual([]);
});

test.each([
  [new ApiError(400, { detail: "configuration invalide : widget w1" }), "configuration invalide"],
  [new ApiError(429, { detail: "Trop de requêtes.", retryAfter: 12 }), "Réessayez dans 12 s."],
  [new Error("boom"), "Échec de l'enregistrement."],
])("un échec d'enregistrement affiche le message du cœur (P10.14)", async (error, expected) => {
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(cfg),
    saveAppConfig: vi.fn().mockRejectedValue(error),
  });
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText(new RegExp(expected))).toBeInTheDocument();
});

test("removing a page prunes messages wired to its widgets after confirmation (P10.07)", async () => {
  const gridOf = (items: AppConfig["layout"]["items"]) => ({
    type: "grid" as const,
    breakpoints: {},
    items,
  });
  const page2Items = [
    { id: "f2", widget: "filter", x: 0, y: 0, w: 4, h: 2, props: {} },
    { id: "t2", widget: "text", x: 4, y: 0, w: 4, h: 2, props: { text: "T" } },
  ];
  const withPages: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    variables: [{ id: "v1", name: "v", type: "string", initialValue: "" }],
    messages: [{ id: "m1", from: "f2", event: "changed", to: "var:v1", action: "set" }],
    pages: [
      { id: "p1", name: "P1", layout: gridOf([]), onEnter: [] },
      { id: "p2", name: "P2", layout: gridOf(page2Items), onEnter: [] },
    ],
    layout: gridOf([]),
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withPages), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Retirer la page p2" }));
  // Rien n'est retiré avant la confirmation.
  expect(
    screen.getByRole("button", { name: "Ouvrir la page p2", hidden: true }),
  ).toBeInTheDocument();
  await userEvent.click(
    within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Supprimer" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.messages).toEqual([]);
  expect(saved.pages).toHaveLength(1);
});

test("removing a variable prunes any ActionsPanel message wired to it", async () => {
  // Même limite que le test jumeau de suppression de widget : la disparition
  // visuelle dans ActionsPanel ne prouve pas la purge de `config.messages`
  // (resolvesOnThisPage masque déjà tout message dont la variable référencée
  // n'existe plus). L'assertion qui compte porte sur l'objet sauvegardé.
  const withWiredVariable: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    variables: [{ id: "v1", name: "seuil", type: "number", initialValue: 0 }],
    messages: [{ id: "m1", from: "w1", event: "changed", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "filter", x: 0, y: 0, w: 4, h: 2, props: {} }],
    },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withWiredVariable), saveAppConfig });

  await screen.findByText("Filtre.changed → Variable : seuil.set");

  await userEvent.click(screen.getByRole("button", { name: "Retirer la variable v1" }));

  expect(screen.queryByText("Filtre.changed → Variable : seuil.set")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.messages).toEqual([]);
  expect(saved.variables).toEqual([]);
});

test("a burst of keystrokes in visibleWhen collapses into one undo step once blurred", async () => {
  // Seeds an already-existing widget (mirrors the GridCanvas tests above)
  // rather than adding one via the palette click just before typing: adding
  // a widget is itself a setDraft call, and with real timers there's no
  // guaranteed >400ms gap between that click and the first keystroke below,
  // so it would risk coalescing into the *same* undo step as the typed
  // text — one Ctrl+Z would then remove the widget outright instead of
  // just clearing visibleWhen, which is not what this test means to check.
  // Seeding seeds the widget outside the undo stack entirely (seedDraft
  // never creates a step), isolating the burst under test to exactly the
  // keystrokes typed below.
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) });
  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x == 'a'");
  // Move focus to a non-text element — tabbing would only land in the "text"
  // widget's own textarea just below visibleWhen in the same panel, still a
  // text field, so it wouldn't actually exercise the "focus left every text
  // field" path the keyboard shortcut check depends on.
  await userEvent.click(screen.getByRole("button", { name: "Édition" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(area).toHaveValue("");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
});

test("Ctrl+Z while focus is in a text field does not trigger the builder's undo", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x");
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.type(area, "{Control>}z{/Control}"); // focus stays in `area`
  expect(area).toHaveValue("vars.x");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled();
});

test("Annuler and Rétablir start disabled and stay disabled with no edits", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
});

test("affiche le panneau d'historique", async () => {
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});

// SP-23 Task 17: rollbackConfig résout, puis getAppConfig est rechargé avec
// une config différente. resetDraft (pas setDraft) doit vider toute la pile
// undo — la pile ne peut pas défaire une écriture serveur (Task 15,
// useUndoableDraft.resetDraft).
test("restaurer une version recharge le brouillon et vide l'undo", async () => {
  const restoredConfig: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  const getAppConfig = vi.fn().mockResolvedValueOnce(config).mockResolvedValue(restoredConfig);
  renderPage({
    getAppConfig,
    listConfigRevisions: vi.fn().mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]),
    rollbackConfig: vi.fn().mockResolvedValue(undefined),
  });

  // On fait un edit avant : canUndo doit être vrai avant la restauration.
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));
  const dialog = screen.getByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /restaurer/i }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled());
});

test("sous viewport étroit, affiche trois onglets Structure/Canevas/Propriétés avec Canevas actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Structure", "Canevas", "Propriétés"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Canevas");
});

test("SP-42/F-shell-pages-04 : verrouille Enregistrer quand permissions.write est false", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue({ ...OWNED_APP_ITEM, permissions: READ_ONLY_PERMISSIONS }),
    getAppConfig: vi.fn().mockResolvedValue(config),
  });
  const saveButton = await screen.findByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeDisabled();
  expect(
    screen.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeInTheDocument();
});

test("SP-42, revue finale (point 2, Critical) : reste en chargement tant que l'item n'est pas résolu, ne verrouille pas Enregistrer par erreur", async () => {
  let resolveItem!: (item: Item) => void;
  let resolveAppConfig!: (config: AppConfig) => void;
  renderPage({
    getItem: vi.fn(
      () =>
        new Promise<Item>((resolve) => {
          resolveItem = resolve;
        }),
    ),
    getAppConfig: vi.fn(
      () =>
        new Promise<AppConfig>((resolve) => {
          resolveAppConfig = resolve;
        }),
    ),
  });

  // Laisse le registre d'extensions (listActiveExtensions, absent ici =>
  // résolution vide par défaut, hooks.ts) se stabiliser en premier — sinon
  // `!extensionsRegistered` masquerait la fenêtre qu'on veut observer.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  // Résout le config d'app SEUL, jamais l'item : avant le correctif, la
  // page rendait déjà le builder complet avec Enregistrer verrouillé
  // (permissions.write lu sur `undefined` => false) au lieu de rester en
  // "Chargement…" comme son jumeau DatasetEditPage.tsx.
  await act(async () => {
    resolveAppConfig(config);
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");

  await act(async () => {
    resolveItem(OWNED_APP_ITEM);
  });
  const saveButton = await screen.findByRole("button", { name: "Enregistrer" });
  expect(saveButton).toBeEnabled();
});

// SP-B9b : activePageId/selectedId passent de useState à useUrlSyncedState
// (Tâche 16). Fixture à deux pages explicites, ids connus ("page-1"/
// "page-2") — les deux tests de ce lot en dépendent pour cibler une page
// précise depuis l'URL sans passer par "Ajouter une page" (qui génère un id
// via un vrai crypto.randomUUID(), non prévisible en test).
const twoPagesConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
  pages: [
    { id: "page-1", name: "Page 1", layout: { type: "grid", breakpoints: {}, items: [] } },
    { id: "page-2", name: "Page 2", layout: { type: "grid", breakpoints: {}, items: [] } },
  ],
};

test("conserve la page active dans l'URL après un remount (simule un rechargement)", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  const { unmount } = renderPage(
    { getAppConfig: vi.fn().mockResolvedValue(twoPagesConfig), saveAppConfig },
    "/?page=page-2",
  );
  await screen.findByRole("button", { name: "Texte" });
  unmount();

  renderPage(
    { getAppConfig: vi.fn().mockResolvedValue(twoPagesConfig), saveAppConfig },
    "/?page=page-2",
  );
  // Si la page active n'avait pas survécu au remount, ce clic ajouterait le
  // widget sur page-1 (page par défaut) au lieu de page-2.
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.pages![0].layout.items).toHaveLength(0); // page-1 non touchée
  expect(saved.pages![1].layout.items).toHaveLength(1); // atterrit sur page-2
});

// Gap signalé par le relecteur de la Tâche 16 : useUrlSyncedState fait un
// cast non vérifié de la chaîne brute de l'URL vers T, sans validation
// runtime. AppBuilderPage a déjà (SP-19, finding C2) un garde-fou qui ne
// fait jamais confiance à `activePageId` brut : `activePage` (la valeur
// réellement utilisée partout ailleurs dans le composant) ne le retient que
// s'il désigne une page qui existe dans le draft courant, sinon retombe sur
// la première page. Ce test vérifie que ce garde-fou tient quand la valeur
// suspecte vient de l'URL (un id de page qui n'a jamais existé), pas
// seulement d'une dérive de la pile undo — et surtout qu'aucune édition
// n'est perdue silencieusement (setPageLayout no-op sur un pageId inconnu,
// même finding C2).
test("un id de page inconnu dans l'URL retombe sur la première page sans perdre l'édition", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage(
    {
      getAppConfig: vi.fn().mockResolvedValue(twoPagesConfig),
      saveAppConfig,
      // listConfigRevisions non fourni ailleurs dans ce fichier lève un
      // alert() sans rapport (ConfigHistoryPanel) qui aurait fait échouer
      // une assertion générique "aucun alert" — mocké ici pour isoler le
      // seul comportement sous test (l'id de page fantôme de l'URL).
      listConfigRevisions: vi.fn().mockResolvedValue([]),
    },
    "/?page=page-fantome-jamais-vue",
  );
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.pages![0].layout.items).toHaveLength(1); // retombé sur page-1
  expect(saved.pages![1].layout.items).toHaveLength(0);
});

test("restaure le widget sélectionné depuis l'URL", async () => {
  const withTwoWidgets: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
        { id: "w2", widget: "text", x: 4, y: 0, w: 4, h: 2, props: { text: "Yo" } },
      ],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withTwoWidgets) }, "/?selected=w2");
  // "Supprimer widget-X" (GridCanvas) ne s'affiche que pour l'item sélectionné.
  expect(await screen.findByRole("button", { name: "Supprimer Texte 2" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Supprimer Texte 1" })).not.toBeInTheDocument();
});

// Contrepartie sélection du test de page fantôme ci-dessus : un id de
// sélection inconnu dans l'URL ne doit ni planter ni verrouiller le
// builder dans un état cassé — aucune sélection ne s'affiche, et l'app
// reste utilisable normalement ensuite (sélectionner un widget réel
// fonctionne comme si l'URL n'avait rien annoncé).
test("un id de sélection inconnu dans l'URL n'affiche aucune sélection et reste utilisable", async () => {
  const withItem: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem) }, "/?selected=widget-fantome");
  await screen.findByRole("button", { name: "Sélectionner Texte" });
  expect(screen.queryByRole("button", { name: /^Supprimer / })).not.toBeInTheDocument();
  // La réconciliation (SP-19, finding M2) ne se contente pas de masquer la
  // sélection périmée à l'écran : elle efface aussi le paramètre "selected"
  // de l'URL — sinon un permalink partagé continuerait de pointer vers un
  // widget fantôme indéfiniment.
  await waitFor(() => expect(screen.getByTestId("url-search").textContent).toBe(""));

  await userEvent.click(screen.getByRole("button", { name: "Sélectionner Texte" }));
  expect(screen.getByRole("button", { name: "Supprimer Texte" })).toBeInTheDocument();
});

test("bloque la navigation après une modification non enregistrée du builder (SP-B6d)", async () => {
  renderPageWithNavigation({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    t("navigation.unsavedChangesMessage"),
  );
});

test("ne bloque pas la navigation juste après une sauvegarde réussie (SP-B6d)", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPageWithNavigation({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());

  await userEvent.click(screen.getByRole("link", { name: "Autre page" }));
  expect(await screen.findByText("Autre page ouverte")).toBeInTheDocument();
});

// SP-B6d, risque signalé au brief : `useUrlSyncedState` (activePageId/
// selectedId, Tâche 16/17) navigue via `setSearchParams` — même pathname,
// query différente. Le prédicat de useDirtyGuard/useBlocker ne bloque que
// sur un pathname différent : changer d'onglet de page à l'intérieur du
// builder ne doit donc jamais déclencher la boîte de confirmation, même
// brouillon non enregistré.
test("changer d'onglet de page (URL interne, même pathname) ne déclenche pas la garde même brouillon non enregistré", async () => {
  renderPageWithNavigation({ getAppConfig: vi.fn().mockResolvedValue(twoPagesConfig) });
  await userEvent.click(await screen.findByRole("button", { name: "Texte" }));

  await userEvent.click(screen.getByRole("button", { name: "Ouvrir la page page-2" }));

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId("url-search").textContent).toContain("page-2"));
});

test("D47 : le toggle Édition/Aperçu et les boutons de largeur d'écran ne sont jamais bg-accent plein", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  const editButton = await screen.findByRole("button", { name: t("appBuilder.editMode") });
  const previewButton = screen.getByRole("button", { name: t("appBuilder.previewMode") });
  const lgButton = screen.getByRole("button", {
    name: t("appBuilder.editBreakpointAria", { bp: t("appBuilder.breakpointLg") }),
  });
  const saveButton = screen.getByRole("button", { name: t("appBuilder.save") });

  // État initial : mode "edit" et breakpoint "lg" actifs par défaut.
  expect(editButton.className).not.toMatch(/(^|\s)bg-accent(\s|$)/);
  expect(editButton.className).toMatch(/(^|\s)bg-sunken(\s|$)/);
  expect(previewButton.className).not.toMatch(/(^|\s)bg-accent(\s|$)/);
  expect(previewButton.className).not.toMatch(/(^|\s)bg-sunken(\s|$)/);
  expect(lgButton.className).not.toMatch(/(^|\s)bg-accent(\s|$)/);
  expect(lgButton.className).toMatch(/(^|\s)bg-sunken(\s|$)/);

  // Enregistrer reste le seul bg-accent plein légitime de cet écran.
  expect(saveButton.className).toMatch(/(^|\s)bg-accent(\s|$)/);

  await userEvent.click(previewButton);
  expect(previewButton.className).toMatch(/(^|\s)bg-sunken(\s|$)/);
  expect(editButton.className).not.toMatch(/(^|\s)bg-sunken(\s|$)/);
  expect(previewButton.className).not.toMatch(/(^|\s)bg-accent(\s|$)/);
});
