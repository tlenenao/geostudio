// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { UsersAdminPage } from "./UsersAdminPage";

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

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <UsersAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const ROLES = [
  { id: "role-admin", name: "Administrateur", slug: "admin", isBuiltIn: true, privileges: [] },
  { id: "role-reader", name: "Lecteur", slug: "reader", isBuiltIn: true, privileges: [] },
];
const USERS = [
  { id: "u1", username: "alice", roleSlug: "admin" },
  { id: "u2", username: "bob", roleSlug: "reader" },
];

test("affiche la liste des utilisateurs avec le rôle courant sélectionné", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByLabelText("Rôle de alice")).toHaveValue("role-admin");
  expect(screen.getByLabelText("Rôle de bob")).toHaveValue("role-reader");
});

test("changer le rôle d'un utilisateur appelle PATCH /users/{id} avec le roleId choisi", async () => {
  let patchedBody: unknown = null;
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
    http.patch("https://core.test/users/u2", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "u2", username: "bob", roleSlug: "admin" });
    }),
  );
  render(<Harness />);
  await screen.findByText("bob");
  await userEvent.selectOptions(screen.getByLabelText("Rôle de bob"), "role-admin");
  await waitFor(() => expect(patchedBody).toEqual({ roleId: "role-admin" }));
});

test("un changement de rôle refusé affiche une erreur sur la bonne ligne, sans affecter les autres", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
    http.patch("https://core.test/users/u1", () => new HttpResponse(null, { status: 409 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  await userEvent.selectOptions(screen.getByLabelText("Rôle de alice"), "role-reader");

  const aliceRow = screen.getByText("alice").closest("tr") as HTMLElement;
  await waitFor(() =>
    expect(within(aliceRow).getByText("Échec de la mise à jour du rôle.")).toBeInTheDocument(),
  );
  const bobRow = screen.getByText("bob").closest("tr") as HTMLElement;
  expect(within(bobRow).queryByText("Échec de la mise à jour du rôle.")).not.toBeInTheDocument();
  // Le select revient à la valeur d'avant la tentative (donnée serveur inchangée).
  expect(screen.getByLabelText("Rôle de alice")).toHaveValue("role-admin");
});

test("la recherche interroge /users avec q et remet la page à 1", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users: USERS, total: 2 });
    }),
  );
  render(<Harness />);
  await screen.findByText("alice");
  await userEvent.type(screen.getByLabelText("Rechercher"), "ali");
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("q")).toBe("ali"));
  expect(new URL(lastUrl).searchParams.get("page")).toBe("1");
});

test("pagination : Précédent désactivé en page 1, Suivant désactivé quand tout est chargé", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
});

test("pagination : un clic sur Suivant redemande la page 2", async () => {
  let lastPage = "";
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", ({ request }) => {
      lastPage = new URL(request.url).searchParams.get("page") ?? "";
      return HttpResponse.json({ users: USERS, total: 120 });
    }),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  await waitFor(() => expect(lastPage).toBe("2"));
});

test("un échec de /users affiche une alerte de chargement", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => new HttpResponse(null, { status: 500 })),
  );
  render(<Harness />);
  expect(await screen.findByText("Échec du chargement des utilisateurs.")).toBeInTheDocument();
});

test("un échec de /roles (403) affiche une alerte expliquant le privilège manquant, sans planter la table", async () => {
  server.use(
    http.get("https://core.test/roles", () => new HttpResponse(null, { status: 403 })),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  expect(
    await screen.findByText(/gestion des rôles.*requis en plus.*gestion des utilisateurs/i),
  ).toBeInTheDocument();
  // La table (qui dépend de rolesQuery.data) ne doit pas apparaître.
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("le volet Détail explique l'invariant anti-lockout", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(
    screen.getByText(/dernier titulaire de la gestion des rôles et des utilisateurs/i),
  ).toBeInTheDocument();
});
