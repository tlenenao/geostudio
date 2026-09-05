// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, vi } from "vitest";
import { MemoryRouter, Link } from "react-router-dom";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CatalogPage } from "./CatalogPage";

vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));

import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";

// jsdom n'implémente pas window.matchMedia (cf. ItemDetailPage.test.tsx,
// piège n°10) ; TriptychLayout l'appelle via useNarrowViewport. Stub local
// au fichier, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets.
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

function mockCatalogItems() {
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      const url = new URL(request.url);
      const q = url.searchParams.get("q");
      const all = [
        {
          pk: "1",
          resourceType: "app",
          title: "Alpha",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: null,
          isPublished: false,
        },
        {
          pk: "2",
          resourceType: "dashboard",
          title: "Beta",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: null,
          isPublished: false,
        },
      ];
      const items = q ? all.filter((i) => i.title.toLowerCase().includes(q.toLowerCase())) : all;
      return HttpResponse.json({ items, total: items.length, page: 1, pageSize: 12 });
    }),
  );
}

test("lists items from the catalog", async () => {
  mockCatalogItems();
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeInTheDocument();
  expect(screen.getAllByText("actions").length).toBeGreaterThan(0);
});

test("filters by search term", async () => {
  mockCatalogItems();
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  await userEvent.type(screen.getByLabelText("Rechercher"), "beta");
  await waitFor(() => expect(screen.queryByText("Alpha")).not.toBeInTheDocument());
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("filters the catalog by scope", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await userEvent.selectOptions(screen.getByLabelText("Portée"), "mine");
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("scope")).toBe("mine"));
});

test("le filtre Type propose les douze types plus « Tous »", () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });

  const select = screen.getByLabelText("Type");
  expect(select.querySelectorAll("option")).toHaveLength(13);
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toContain("dataset");
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toContain("tileset3d");
});

test("fixedType locks the type filter and hides the selector", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} fixedType="bookmark" />, { wrapper });
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark"));
  expect(screen.queryByLabelText("Type")).not.toBeInTheDocument();
});

test("propose un lien vers /reports quand le type de la barre de domaines est pipeline (atterrissage Automatisation)", async () => {
  function wrapperWithPipelineType({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const client = createItemClient({
      coreUrl: "https://core.test",
      getToken: () => "test-token",
    });
    return (
      <MemoryRouter initialEntries={["/?type=pipeline"]}>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>{children}</ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }

  render(<CatalogPage onOpenItem={() => {}} />, { wrapper: wrapperWithPipelineType });
  expect(await screen.findByRole("link", { name: "Rapports planifiés →" })).toHaveAttribute(
    "href",
    "/reports",
  );
});

test("masque le lien vers /reports hors de l'atterrissage Automatisation (catalogue général)", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  // Attendre un rendu stable (le sélecteur Type, toujours présent hors
  // fixedType) avant l'assertion négative, plutôt qu'un sleep arbitraire.
  await screen.findByRole("combobox", { name: "Type" });
  expect(screen.queryByRole("link", { name: "Rapports planifiés →" })).not.toBeInTheDocument();
});

test("masque le lien vers /reports sur une vue à fixedType fixé (ex. /reports lui-même)", async () => {
  render(<CatalogPage onOpenItem={() => {}} fixedType="report" />, { wrapper });
  expect(screen.queryByRole("link", { name: "Rapports planifiés →" })).not.toBeInTheDocument();
});

test("prend le type initial depuis le paramètre d'URL ?type=", async () => {
  function wrapperWithInitialType({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const client = createItemClient({
      coreUrl: "https://core.test",
      getToken: () => "test-token",
    });
    return (
      <MemoryRouter initialEntries={["/?type=map"]}>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>{children}</ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }

  render(<CatalogPage onOpenItem={() => {}} />, { wrapper: wrapperWithInitialType });
  await screen.findByText("GeoStudio").catch(() => {});
  expect(screen.getByLabelText("Type")).toHaveValue("map");
});

test("setType met à jour la query au changement de filtre (history réelle testée en E2E, Task 6)", async () => {
  // La propriété "une seule entrée d'historique par changement de filtre"
  // (correctif SP-30a : `{ replace: true }` sur setSearchParams) n'a pas de
  // prise fiable au niveau unitaire — MemoryRouter n'expose pas sa pile
  // d'historique. Ce test couvre le comportement observable (le select
  // suit chaque changement) ; la propriété de non-empilement est vérifiée
  // en E2E via `page.goBack()` (Task 6).
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByLabelText("Type");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("dataset"));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("map"));
});

test("réinitialise la page à 1 quand le type change (navigation DomainBar)", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      // total > pageSize pour que le bouton "Suivant" ne soit pas désactivé
      // (avec total: 0, totalPages vaut 1 et page 1 >= totalPages).
      return HttpResponse.json({ items: [], total: 20, page: 1, pageSize: 12 });
    }),
  );
  function Harness() {
    return (
      <>
        <Link to="/?type=dataset">Données</Link>
        <CatalogPage onOpenItem={() => {}} />
      </>
    );
  }
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ItemClientProvider
          client={createItemClient({ coreUrl: "https://core.test", getToken: () => "t" })}
        >
          <Harness />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("map"));
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("page")).toBe("2"));
  await userEvent.click(screen.getByText("Données"));
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("page")).toBe("1"));
});

test("le volet Résumé affiche le compte total et les filtres actifs", async () => {
  mockCatalogItems();
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  expect(await screen.findByText("2 éléments")).toBeInTheDocument();
});

test("openError affiche le message d'échec d'ouverture dans le volet Catalogue", () => {
  render(<CatalogPage onOpenItem={() => {}} openError="Échec de l'ouverture de l'élément." />, {
    wrapper,
  });
  expect(screen.getByRole("alert")).toHaveTextContent("Échec de l'ouverture de l'élément.");
});

test("suit ?type= quand il change après une navigation (DomainBar) sans remonter la page", async () => {
  // Régression : CatalogPage lisait ?type= dans un useState initializer, donc
  // une navigation vers la même page montée (Cartes -> Données via DomainBar)
  // ne mettait pas à jour le select/la grille. L'URL doit être la seule
  // source de vérité.
  function Harness() {
    return (
      <>
        <Link to="/?type=dataset">Données</Link>
        <CatalogPage onOpenItem={() => {}} />
      </>
    );
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <Harness />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );

  expect(screen.getByLabelText("Type")).toHaveValue("map");

  await userEvent.click(screen.getByText("Données"));

  await waitFor(() => expect(screen.getByLabelText("Type")).toHaveValue("dataset"));
});
