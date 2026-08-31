// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RequireRole } from "./RequireRole";

function mockMe(overrides: { isAdmin?: boolean; isAnalyst?: boolean }) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        isAdmin: overrides.isAdmin ?? false,
        isAnalyst: overrides.isAnalyst ?? false,
      }),
    ),
  );
}

function renderGate(role: "admin" | "analyst", deniedMessage: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RequireRole role={role} deniedMessage={deniedMessage}>
          <p>Contenu protégé</p>
        </RequireRole>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche le contenu quand le rôle requis est présent", async () => {
  mockMe({ isAnalyst: true });
  renderGate("analyst", "Accès réservé aux analystes.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche le message de refus quand le rôle requis est absent", async () => {
  mockMe({ isAnalyst: false });
  renderGate("analyst", "Accès réservé aux analystes.");
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
  expect(screen.queryByText("Contenu protégé")).not.toBeInTheDocument();
});

test("le rôle admin se vérifie indépendamment du rôle analyste", async () => {
  mockMe({ isAdmin: true, isAnalyst: false });
  renderGate("admin", "Accès réservé aux administrateurs.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche un statut de chargement avant la résolution de /me", () => {
  mockMe({ isAnalyst: true });
  renderGate("analyst", "Accès réservé aux analystes.");
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");
});
