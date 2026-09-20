// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ConfigProvider } from "../ConfigContext";
import type { AppConfig } from "../config";
import { SettingsPage } from "./SettingsPage";

// Stub for window.matchMedia (jsdom doesn't implement it)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  }),
});

const OIDC_CONFIG: AppConfig = {
  coreUrl: "https://core.test",
  oidcAuthority: "https://kc.test/realms/geostudio",
  oidcClientId: "shell",
  oidcRedirectUri: "https://app.test/callback",
  authMode: "oidc",
};
const MOCK_CONFIG: AppConfig = { ...OIDC_CONFIG, authMode: "mock" };

function mockMe() {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        tenantId: "t1",
        tenantSlug: "acme",
        username: "alice",
        email: "alice@example.com",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges: [],
      }),
    ),
  );
}

function mockPreference(value = "all") {
  server.use(
    http.get("https://core.test/v1/notifications/preference", () => HttpResponse.json({ value })),
  );
}

function renderPage(config: AppConfig = OIDC_CONFIG) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <ConfigProvider config={config}>
            <SettingsPage />
          </ConfigProvider>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

test("affiche le profil et la préférence de notifications courante", async () => {
  mockMe();
  mockPreference("all");
  renderPage();
  expect(await screen.findByText("alice")).toBeInTheDocument();
  expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  expect(screen.getByText("Alice Martin")).toBeInTheDocument();
  expect(screen.getByText("Créateur")).toBeInTheDocument();
  expect(screen.getByText("acme")).toBeInTheDocument();
  expect(await screen.findByRole("radio", { name: "Toutes" })).toBeChecked();
});

test("change la préférence de notifications appelle PATCH avec la nouvelle valeur", async () => {
  mockMe();
  mockPreference("all");
  let patchedBody: unknown = null;
  server.use(
    http.patch("https://core.test/v1/notifications/preference", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ value: "failures_only" });
    }),
  );
  renderPage();
  const failuresRadio = await screen.findByRole("radio", { name: "Échecs seulement" });
  await userEvent.click(failuresRadio);
  await waitFor(() => expect(patchedBody).toEqual({ value: "failures_only" }));
});

test("affiche une erreur si la sauvegarde de la préférence échoue", async () => {
  mockMe();
  mockPreference("all");
  server.use(
    http.patch(
      "https://core.test/v1/notifications/preference",
      () => new HttpResponse(null, { status: 500 }),
    ),
  );
  renderPage();
  const noneRadio = await screen.findByRole("radio", { name: "Aucune" });
  await userEvent.click(noneRadio);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Échec de l'enregistrement de la préférence.",
  );
});

test("masque la section Compte en mode mock", async () => {
  mockMe();
  mockPreference("all");
  renderPage(MOCK_CONFIG);
  await screen.findByText("alice");
  expect(screen.queryByRole("link", { name: /Gérer mon compte/ })).not.toBeInTheDocument();
});

test("affiche le lien vers la console de compte Keycloak en mode oidc", async () => {
  mockMe();
  mockPreference("all");
  renderPage(OIDC_CONFIG);
  const link = await screen.findByRole("link", { name: /Gérer mon compte/ });
  expect(link).toHaveAttribute("href", "https://kc.test/realms/geostudio/account");
  expect(link).toHaveAttribute("target", "_blank");
});
