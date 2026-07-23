// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { HarvestSourcesAdminPage } from "./HarvestSourcesAdminPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <HarvestSourcesAdminPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockAdmin() {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
  );
}

test("shows an access-denied message and never calls /harvest/sources when not admin", async () => {
  let called = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/harvest/sources", () => {
      called = true;
      return HttpResponse.json({ sources: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(called).toBe(false);
});

test("admin creates a STAC source and triggers a manual run", async () => {
  mockAdmin();
  let created: Record<string, unknown> | null = null;
  let ran = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: created ? [{
          id: "src-1", type: "stac", url: "https://stac.example.com/collections",
          mode: "reference", enabled: true, intervalMinutes: null,
          lastRunAt: null, lastStatus: ran ? "ok" : null, lastError: null,
        }] : [],
      }),
    ),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      created = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: "src-1", ...created, lastRunAt: null, lastStatus: null, lastError: null,
      }, { status: 201 });
    }),
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      ran = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  const dialog = screen.getByRole("dialog", { name: "Ajouter une source" });
  await userEvent.type(dialog.querySelector("input[aria-label='URL']")!, "https://stac.example.com/collections");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(created).not.toBeNull());
  expect(await screen.findByText("https://stac.example.com/collections")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Moissonner maintenant" }));
  await waitFor(() => expect(ran).toBe(true));
});

test("delete removes the source from the list", async () => {
  mockAdmin();
  let deleted = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: deleted ? [] : [{
          id: "src-1", type: "stac", url: "https://a", mode: "reference",
          enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        }],
      }),
    ),
    http.delete("https://core.test/harvest/sources/src-1", () => {
      deleted = true;
      return HttpResponse.text("", { status: 204 });
    }),
  );
  render(<Harness />);
  await screen.findByText("https://a");
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  // Le bouton de la ligne et celui du ConfirmDialog partagent le même nom
  // accessible une fois le dialogue ouvert — on scope au dialogue (même
  // patron que CollectionsAdminPage.test.tsx : within(dialog).getByRole).
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleted).toBe(true));
  await waitFor(() => expect(screen.queryByText("https://a")).not.toBeInTheDocument());
});

test("masque les boutons d'écriture en mode démo (read-only)", async () => {
  mockAdmin();
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [{
          id: "s1", type: "stac", url: "https://stac/x", mode: "reference",
          enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: "ok", lastError: null,
        }],
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("https://stac/x");
  expect(screen.queryByRole("button", { name: "Ajouter une source" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Moissonner maintenant" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Éditer" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Supprimer" })).toBeNull();
});
