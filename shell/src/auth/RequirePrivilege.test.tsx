// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RequirePrivilege } from "./RequirePrivilege";

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges,
      }),
    ),
  );
}

function renderGate(privilege: string, deniedMessage: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RequirePrivilege privilege={privilege} deniedMessage={deniedMessage}>
          <p>Contenu protégé</p>
        </RequirePrivilege>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche le contenu quand le privilège requis est présent", async () => {
  mockMe(["analytics.sql_lab.access"]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche le message de refus quand le privilège requis est absent", async () => {
  mockMe([]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
  expect(screen.queryByText("Contenu protégé")).not.toBeInTheDocument();
});

test("un privilège se vérifie indépendamment des autres privilèges détenus", async () => {
  mockMe(["admin.roles.manage"]);
  renderGate("admin.roles.manage", "Accès réservé à la gestion des rôles.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche un statut de chargement avant la résolution de /me", () => {
  mockMe(["analytics.sql_lab.access"]);
  renderGate("analytics.sql_lab.access", "Accès réservé aux analystes.");
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");
});
