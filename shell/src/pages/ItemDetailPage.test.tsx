// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ItemDetailPage } from "./ItemDetailPage";

vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));

// jsdom n'implémente pas window.matchMedia (cf. AppLayout.test.tsx, piège
// n°10) ; TriptychLayout l'appelle via useNarrowViewport. Stub local au
// fichier, jamais dans shell/src/test/setup.ts. matches: false => le layout
// "large" (3 volets simultanés), pas les onglets.
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
});

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function wrapperWithInitialSearch(initialPath: string, children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("shows the item detail", async () => {
  render(<ItemDetailPage pk="7" />, { wrapper });
  expect(await screen.findByRole("heading", { name: "Item 7" })).toBeInTheDocument();
  // item 7 has resourceType "app" (default mock) — editor button is now enabled for app/dashboard/map
  expect(screen.getByRole("button", { name: /éditeur/i })).not.toBeDisabled();
  expect(screen.getByText("actions")).toBeInTheDocument();
});

test("shows an error for a missing item", async () => {
  render(<ItemDetailPage pk="404" />, { wrapper });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

test("shows 'Ouvrir dans l'éditeur' for a pipeline item and calls onOpenEditor('pipeline')", async () => {
  server.use(
    http.get("https://core.test/items/7", () =>
      HttpResponse.json({
        pk: "7",
        resourceType: "pipeline",
        title: "Item 7",
        abstract: "Abstract 7",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01T00:00:00Z",
        configId: null,
        isPublished: false,
      }),
    ),
  );
  const onOpenEditor = vi.fn();
  render(<ItemDetailPage pk="7" onOpenEditor={onOpenEditor} />, { wrapper });
  const button = await screen.findByRole("button", { name: /éditeur/i });
  expect(button).not.toBeDisabled();
  await userEvent.click(button);
  expect(onOpenEditor).toHaveBeenCalledWith("pipeline");
});

test("affiche le formulaire d'édition quand l'URL porte ?panel=edit", async () => {
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=edit", children),
  });
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
});

test("affiche l'envoi de miniature quand l'URL porte ?panel=thumbnail", async () => {
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=thumbnail", children),
  });
  expect(await screen.findByLabelText("Miniature")).toBeInTheDocument();
});

test("affiche le formulaire de partage quand l'URL porte ?panel=share", async () => {
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=share", children),
  });
  expect(await screen.findByText("Partager l'élément")).toBeInTheDocument();
});

test("aucun panneau affiché sans ?panel=", async () => {
  render(<ItemDetailPage pk="1" />, { wrapper });
  await screen.findByRole("heading", { name: "Item 1" });
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Miniature")).not.toBeInTheDocument();
  expect(screen.queryByText("Partager l'élément")).not.toBeInTheDocument();
});

test("un ?panel= inconnu n'affiche aucun panneau", async () => {
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=bogus", children),
  });
  await screen.findByRole("heading", { name: "Item 1" });
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();
});
