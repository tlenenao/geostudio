// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS, READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { AppBuilderPage } from "./AppBuilderPage";
import type { AuthState } from "../auth/useAuth";

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

function renderPage(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged: Partial<ItemClient> = {
    getItem: vi.fn().mockResolvedValue(OWNED_APP_ITEM),
    ...client,
  };
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={merged as ItemClient}>
        <AppBuilderPage pk="5" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
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
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
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

  await userEvent.click(await screen.findByRole("button", { name: "Éditer en sm" }));
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0); // base untouched
  expect(saved.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
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
    within(targetSelect).getByRole("option", { name: "Variable : Variable 1" }),
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
  expect(screen.getAllByRole("button", { name: /^Sélectionner widget-/ })).toHaveLength(1);

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
    name: "Promouvoir en dataset partagé s1",
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
  await screen.findByText("Dataset partagé actif");

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

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));

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

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
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

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Supprimer widget-w1" }));
  expect(screen.queryByRole("button", { name: "Sélectionner widget-w1" })).not.toBeInTheDocument();
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

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.keyboard("{Backspace}");
  expect(screen.queryByRole("button", { name: "Sélectionner widget-w1" })).not.toBeInTheDocument();
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

  await screen.findByRole("button", { name: "Sélectionner widget-w1" });
  expect(screen.getByText("Filtre.changed → Liste.setFilter")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Supprimer widget-w1" }));

  expect(screen.queryByText("Filtre.changed → Liste.setFilter")).not.toBeInTheDocument();
  expect(screen.getByText("Aucune action.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.messages).toEqual([]);
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
  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
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
  vi.spyOn(window, "confirm").mockReturnValue(true);
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
