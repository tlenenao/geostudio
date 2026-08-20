// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ItemDetailPage } from "./ItemDetailPage";

vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));

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
