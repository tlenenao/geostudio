// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { UsagePage } from "./UsagePage";

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
          <UsagePage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
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
        role: { id: "role-x", name: "X", slug: "creator" },
        privileges,
        version: "0.1.0",
        tenantSlug: "default",
      }),
    ),
  );
}

test("un profil tasks.view (sans tasks.view_all) voit sa liste mais pas la section usage", async () => {
  mockMe(["tasks.view"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "p1",
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Mes tâches récentes");
  // pas juste masquée par CSS : absente du DOM
  expect(screen.queryByText("Usage de la plateforme")).not.toBeInTheDocument();
});

test("un profil tasks.view_all voit les deux sections", async () => {
  mockMe(["tasks.view", "tasks.view_all"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({ tasks: [], total: 0, page: 1, pageSize: 50 }),
    ),
    http.get("https://core.test/v1/usage/summary", () =>
      HttpResponse.json({
        byActor: [{ actorId: "u1", actorUsername: "alice", count: 3 }],
        byResource: [{ objectType: "collection", objectId: "c1", count: 2 }],
        totalActions: 3,
        windowStart: "2026-08-01T00:00:00Z",
        windowEnd: "2026-09-01T00:00:00Z",
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Tâches du tenant");
  await screen.findByText("Usage de la plateforme");
  expect(await screen.findByText(/alice/)).toBeInTheDocument();
});

test("état vide : aucune tâche récente affiche un message, pas une table vide", async () => {
  mockMe(["tasks.view"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({ tasks: [], total: 0, page: 1, pageSize: 50 }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Aucune tâche récente.");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("cliquer l'en-tête Action trie les tâches par libellé (DataTable, Tâche 22)", async () => {
  mockMe(["tasks.view"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "report.run",
            objectType: "report",
            objectId: "r1",
            createdAt: "2026-09-01T00:00:00Z",
          },
          {
            id: 2,
            actorId: "u1",
            action: "alert.evaluate",
            objectType: "alert",
            objectId: "al1",
            createdAt: "2026-09-02T00:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Génération de rapport");
  const rowsBefore = screen.getAllByRole("row").slice(1);
  expect(within(rowsBefore[0]).getByText("Génération de rapport")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("columnheader", { name: "Action" }));

  const rowsAfter = screen.getAllByRole("row").slice(1);
  expect(within(rowsAfter[0]).getByText("Évaluation d'alerte")).toBeInTheDocument();
  expect(within(rowsAfter[1]).getByText("Génération de rapport")).toBeInTheDocument();
});

test("le libellé français de l'action est affiché, pas la clé technique brute", async () => {
  mockMe(["tasks.view"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "p1",
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Exécution de pipeline");
  expect(screen.queryByText("pipeline.run")).not.toBeInTheDocument();
});

test("tasks.view_all : titre « Tâches du tenant » et colonne Utilisateur (j08-012)", async () => {
  mockMe(["tasks.view", "tasks.view_all"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u2",
            actorUsername: "bob",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "p1",
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        pageSize: 50,
      }),
    ),
    http.get("https://core.test/v1/usage/summary", () =>
      HttpResponse.json({
        byActor: [],
        byResource: [],
        totalActions: 0,
        windowStart: "2026-08-01T00:00:00Z",
        windowEnd: "2026-09-01T00:00:00Z",
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByRole("columnheader", { name: "Utilisateur" })).toBeInTheDocument();
  expect(await screen.findByText("bob")).toBeInTheDocument();
  expect(screen.queryByText("Mes tâches récentes")).not.toBeInTheDocument();
});

test("tasks.view seul : pas de colonne Utilisateur, titre « Mes tâches récentes »", async () => {
  mockMe(["tasks.view"]);
  server.use(
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "p1",
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Mes tâches récentes");
  expect(screen.queryByRole("columnheader", { name: "Utilisateur" })).not.toBeInTheDocument();
});

test("REV-285(f) : titre fourni par l'API d'usage, aucun GET /items par ligne", async () => {
  mockMe(["tasks.view"]);
  let itemFetches = 0;
  server.use(
    http.get("https://core.test/v1/items/:pk", () => {
      itemFetches += 1;
      return HttpResponse.json({}, { status: 404 });
    }),
    http.get("https://core.test/v1/usage/tasks", () =>
      HttpResponse.json({
        tasks: [
          {
            id: 1,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "abcdef1234",
            objectTitle: "Nettoyage des adresses",
            createdAt: "2026-09-01T00:00:00Z",
          },
          {
            id: 2,
            actorId: "u1",
            action: "pipeline.run",
            objectType: "pipeline",
            objectId: "0123456789",
            objectTitle: null,
            createdAt: "2026-09-01T00:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        pageSize: 50,
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("Nettoyage des adresses (Pipeline)")).toBeInTheDocument();
  expect(screen.getByText("Pipeline 01234567…")).toBeInTheDocument();
  expect(itemFetches).toBe(0);
});
