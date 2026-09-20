// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AdminNav } from "./AdminNav";

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Administrateur", slug: "admin" },
        privileges,
      }),
    ),
  );
}

function renderNav(initialPath = "/admin/extensions") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminNav />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const ALL_PRIVILEGES = [
  "admin.extensions.manage",
  "settings.instance.manage",
  "admin.roles.manage",
  "admin.users.manage",
  "admin.collections.manage",
  "admin.harvest.manage",
  "compliance.manage",
];

test("toujours un lien retour au catalogue, même sans aucun privilège", async () => {
  mockMe([]);
  renderNav();
  expect(await screen.findByRole("link", { name: "← Retour au catalogue" })).toHaveAttribute(
    "href",
    "/",
  );
  for (const name of [
    "Extensions →",
    "Outils d'infrastructure →",
    "Rôles et privilèges →",
    "Utilisateurs →",
    "Collections →",
    "Moissonnage →",
    "Conformité (RGPD) →",
  ]) {
    expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
  }
});

test("affiche les sept liens admin quand tous les privilèges sont détenus", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav();
  expect(await screen.findByRole("link", { name: "Extensions →" })).toHaveAttribute(
    "href",
    "/admin/extensions",
  );
  expect(screen.getByRole("link", { name: "Outils d'infrastructure →" })).toHaveAttribute(
    "href",
    "/admin/infrastructure",
  );
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toHaveAttribute(
    "href",
    "/admin/roles",
  );
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
  expect(screen.getByRole("link", { name: "Collections →" })).toHaveAttribute(
    "href",
    "/admin/collections",
  );
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toHaveAttribute(
    "href",
    "/admin/harvest",
  );
  expect(screen.getByRole("link", { name: "Conformité (RGPD) →" })).toHaveAttribute(
    "href",
    "/admin/compliance",
  );
});

test("ne montre que le lien Rôles quand seul admin.roles.manage est détenu", async () => {
  mockMe(["admin.roles.manage"]);
  renderNav();
  expect(await screen.findByRole("link", { name: "Rôles et privilèges →" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Utilisateurs →" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Extensions →" })).not.toBeInTheDocument();
});

test("marque la page courante comme active (aria-current) parmi les liens admin", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav("/admin/roles");
  const rolesLink = await screen.findByRole("link", { name: "Rôles et privilèges →" });
  expect(rolesLink).toHaveAttribute("aria-current", "page");
  const usersLink = screen.getByRole("link", { name: "Utilisateurs →" });
  expect(usersLink).not.toHaveAttribute("aria-current");
});

test("permet de naviguer d'une page admin à une autre sans repasser par /admin/extensions", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav("/admin/roles");
  expect(await screen.findByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});
