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
