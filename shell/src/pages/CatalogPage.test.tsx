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
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("lists items from the catalog", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeInTheDocument();
  expect(screen.getAllByText("actions").length).toBeGreaterThan(0);
});

test("filters by search term", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  await userEvent.type(screen.getByLabelText("Rechercher"), "beta");
  await waitFor(() => expect(screen.queryByText("Alpha")).not.toBeInTheDocument());
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("filters the catalog by scope", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await userEvent.selectOptions(screen.getByLabelText("Portée"), "mine");
  await waitFor(() =>
    expect(new URL(lastUrl).searchParams.get("filter{owner.username.in}")).toBe("alice"),
  );
});
