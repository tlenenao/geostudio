// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CatalogPage } from "./CatalogPage";

vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));

import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function mockCatalogItems() {
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      const url = new URL(request.url);
      const q = url.searchParams.get("q");
      const all = [
        { pk: "1", resourceType: "app", title: "Alpha", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
        { pk: "2", resourceType: "dashboard", title: "Beta", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
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
  await waitFor(() =>
    expect(new URL(lastUrl).searchParams.get("scope")).toBe("mine"),
  );
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
