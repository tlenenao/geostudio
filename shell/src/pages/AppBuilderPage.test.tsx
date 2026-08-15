// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppBuilderPage } from "./AppBuilderPage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

vi.mock("html-to-image", () => ({
  toBlob: vi.fn().mockResolvedValue(new Blob(["x"], { type: "image/png" })),
}));

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
};

function renderPage(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
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
  await userEvent.selectOptions(emitterSelect, within(emitterSelect).getByRole("option", { name: "Filtre" }));
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(targetSelect, within(targetSelect).getByRole("option", { name: "Liste" }));
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
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
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
  await userEvent.selectOptions(emitterSelect, within(emitterSelect).getByRole("option", { name: "Filtre" }));
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(targetSelect, within(targetSelect).getByRole("option", { name: "Variable : Variable 1" }));
  await userEvent.selectOptions(screen.getByLabelText("Action"), "set");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.variables).toHaveLength(1);
  expect(saved.messages).toHaveLength(1);
  expect(saved.messages[0]).toMatchObject({ event: "changed", action: "set", to: `var:${saved.variables[0].id}` });
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
    kind: "app", theme: {}, messages: [],
    dataSources: [
      { id: "s1", type: "features", service: "core", layer: "parcs", query: {} },
      { id: "s2", type: "features", service: "core", layer: "routes", query: {} },
    ],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  const createDatasetItem = vi.fn().mockResolvedValue({
    pk: "ds-1", resourceType: "dataset", title: "parcs", abstract: "",
    owner: "tanguy", thumbnailUrl: null, date: "", configId: "1", isPublished: false,
  });
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(withSources),
    saveAppConfig,
    createDatasetItem,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });

  const promoteButton = await screen.findByRole("button", { name: "Promouvoir en dataset partagé s1" });
  await userEvent.click(promoteButton);

  await waitFor(() => expect(createDatasetItem).toHaveBeenCalledWith({
    title: "parcs", owner: "tanguy", source: "collection", collectionId: "parcs",
  }));
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
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
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
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
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
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
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
