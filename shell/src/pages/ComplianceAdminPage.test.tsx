// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ComplianceAdminPage } from "./ComplianceAdminPage";

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

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "me",
        firstName: "Moi",
        lastName: "Même",
        email: "me@example.com",
        tenantId: "t1",
        tenantSlug: "demo",
        role: { id: "role-x", name: "X", slug: "x" },
        privileges,
        version: "0.1.0",
      }),
    ),
  );
}

// Défaut : les deux privilèges — chaque section est ensuite testée seule.
beforeEach(() => {
  stubMatchMedia(false);
  mockMe(["admin.users.manage", "compliance.manage"]);
});
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <ComplianceAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("le bouton de purge reste désactivé tant que le slug tapé ne correspond pas", async () => {
  render(<Harness />);
  await screen.findByText("Purger toutes les données du tenant");
  const purgeButton = screen.getByRole("button", { name: "Purger définitivement ce tenant" });
  expect(purgeButton).toBeDisabled();

  await userEvent.type(screen.getByLabelText(/Retapez le slug du tenant/), "mauvais-slug");
  expect(purgeButton).toBeDisabled();
});

test("le bouton de purge s'active une fois le slug exact tapé, et déclenche POST /compliance/tenants/{id}/purge", async () => {
  let postedTenantId: string | null = null;
  let postedBody: unknown = null;
  server.use(
    http.post(
      "https://core.test/v1/compliance/tenants/:tenantId/purge",
      async ({ params, request }) => {
        postedTenantId = String(params.tenantId);
        postedBody = await request.json();
        return HttpResponse.json({ jobId: "purge-123" }, { status: 202 });
      },
    ),
    http.get("https://core.test/v1/compliance/purges/purge-123", () =>
      HttpResponse.json({ status: 202, detail: "in progress" }, { status: 202 }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Purger toutes les données du tenant");

  // "demo" = tenantSlug servi par le mock /me par défaut (src/test/msw/handlers.ts).
  await userEvent.type(screen.getByLabelText(/Retapez le slug du tenant/), "demo");
  const purgeButton = screen.getByRole("button", { name: "Purger définitivement ce tenant" });
  expect(purgeButton).toBeEnabled();
  await userEvent.click(purgeButton);

  await waitFor(() => expect(postedTenantId).toBe("t1"));
  expect(postedBody).toEqual({ confirmSlug: "demo" });
  expect(await screen.findByText("Purge en cours…")).toBeInTheDocument();
});

test("anonymiser un compte appelle POST /compliance/users/{id}/erase et affiche une confirmation", async () => {
  let erasedUserId: string | null = null;
  server.use(
    http.post("https://core.test/v1/compliance/users/:userId/erase", ({ params }) => {
      erasedUserId = String(params.userId);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await screen.findByText("Anonymiser un compte");

  await userEvent.type(screen.getByLabelText(/Identifiant de l'utilisateur/), "u42");
  await userEvent.click(screen.getByRole("button", { name: "Anonymiser ce compte" }));

  await waitFor(() => expect(erasedUserId).toBe("u42"));
  expect(await screen.findByText("Compte anonymisé.")).toBeInTheDocument();
});

test("les deux sections (anonymiser / purger) sont visuellement distinctes, jamais mélangées", async () => {
  render(<Harness />);
  await screen.findByText("Anonymiser un compte");
  const eraseHeading = screen.getByText("Anonymiser un compte");
  const purgeHeading = screen.getByText("Purger toutes les données du tenant");
  // Deux panneaux <section>/<div> DISTINCTS, jamais le même conteneur —
  // preuve minimale (piège spec §5) que les deux actions ne partagent pas
  // de conteneur visuel commun.
  expect(eraseHeading.closest("div")).not.toBe(purgeHeading.closest("div"));
});

test("un administrateur sans compliance.manage anonymise mais ne voit pas la purge (j08-002)", async () => {
  mockMe(["admin.users.manage"]);
  render(<Harness />);
  await screen.findByText("Anonymiser un compte");
  expect(screen.queryByText("Purger toutes les données du tenant")).not.toBeInTheDocument();
});

test("compliance.manage seul voit la purge mais pas l'anonymisation", async () => {
  mockMe(["compliance.manage"]);
  render(<Harness />);
  await screen.findByText("Purger toutes les données du tenant");
  expect(screen.queryByText("Anonymiser un compte")).not.toBeInTheDocument();
});

test("l'échec d'anonymisation distingue « introuvable » (j08-006)", async () => {
  server.use(
    http.post("https://core.test/v1/compliance/users/:userId/erase", () =>
      HttpResponse.json(
        { title: "Not Found", status: 404, detail: "user not found in this tenant" },
        { status: 404, headers: { "Content-Type": "application/problem+json" } },
      ),
    ),
  );
  render(<Harness />);
  await screen.findByText("Anonymiser un compte");
  await userEvent.type(screen.getByLabelText(/Identifiant de l'utilisateur/), "nope");
  await userEvent.click(screen.getByRole("button", { name: "Anonymiser ce compte" }));
  expect(await screen.findByText("Utilisateur introuvable dans ce tenant.")).toBeInTheDocument();
});
