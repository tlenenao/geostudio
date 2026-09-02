// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AuthState } from "../../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

const { AccountMenu } = await import("./AccountMenu");

function renderMenu() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <AccountMenu />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

function meResponse(overrides: Partial<Record<string, unknown>> = {}) {
  return HttpResponse.json({
    id: "u1",
    username: "alice",
    firstName: "Alice",
    lastName: "Martin",
    role: { id: "role-reader", name: "Lecteur", slug: "reader" },
    privileges: [],
    version: "0.1.0",
    tenantSlug: "demo",
    ...overrides,
  });
}

// Même constat que src/ui/kit/Popover.test.tsx (AccountMenu ouvre ce même
// Popover) : le repositionnement Popper sous jsdom dépasse par intermittence
// le testTimeout par défaut (5000ms) quand la suite complète tourne sous
// charge CPU, jamais en lançant ce fichier seul. Même valeur (45000)
// reprise ici plutôt que redécouverte.
const OPEN_TIMEOUT = 45000;

test(
  "ouvre le menu et affiche le nom, le badge Lecteur, puis se déconnecte",
  async () => {
    server.use(http.get("https://core.test/me", () => meResponse()));
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.getByText("Lecteur")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Déconnexion" }));
    expect(authState.signOut).toHaveBeenCalled();
  },
  OPEN_TIMEOUT,
);

test(
  "affiche Créateur pour un compte avec le rôle créateur",
  async () => {
    server.use(
      http.get("https://core.test/me", () =>
        meResponse({ role: { id: "role-creator", name: "Créateur", slug: "creator" } }),
      ),
    );
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("Créateur")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "affiche Administrateur pour un compte avec le rôle admin",
  async () => {
    server.use(
      http.get("https://core.test/me", () =>
        meResponse({ role: { id: "role-admin", name: "Administrateur", slug: "admin" } }),
      ),
    );
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("Administrateur")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "affiche Analyste pour un compte avec le rôle analyste",
  async () => {
    server.use(
      http.get("https://core.test/me", () =>
        meResponse({ role: { id: "role-analyst", name: "Analyste", slug: "analyst" } }),
      ),
    );
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("Analyste")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "affiche le nom du rôle brut pour un rôle personnalisé sans clé i18n dédiée",
  async () => {
    server.use(
      http.get("https://core.test/me", () =>
        meResponse({ role: { id: "role-custom", name: "Cartographe", slug: "cartographe" } }),
      ),
    );
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("Cartographe")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);
