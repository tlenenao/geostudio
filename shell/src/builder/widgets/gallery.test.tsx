// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { Item, ItemClient } from "../../api/types";
import { OWNER_PERMISSIONS } from "../../auth/permissions";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

function renderGallery(props: Record<string, unknown>, clientOverrides: Partial<ItemClient> = {}) {
  const client = {
    listPublicItems: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 }),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Gallery = getWidget("gallery")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Gallery props={props} ctx={{ mode: "runtime" } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

const publishedItem: Item = {
  pk: "8",
  resourceType: "app",
  title: "Carte des risques",
  abstract: "Resume",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: null,
  isPublished: true,
  keywords: ["risques"],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

test("gallery calls listPublicItems with the author's fixed filter props", () => {
  const client = renderGallery({ type: "app", tag: "risques", limit: 6, columns: 2 });
  expect(client.listPublicItems).toHaveBeenCalledWith({
    type: "app",
    tag: "risques",
    page: 1,
    pageSize: 6,
  });
});

test("gallery renders a grid of published items, each linking to its public page", async () => {
  renderGallery(
    {},
    {
      listPublicItems: vi
        .fn()
        .mockResolvedValue({ items: [publishedItem], total: 1, page: 1, pageSize: 12 }),
    },
  );
  expect(await screen.findByText("Carte des risques")).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /Carte des risques/ });
  expect(link).toHaveAttribute("href", "/public/items/8");
});

test("gallery shows an empty state when there are no published items", async () => {
  renderGallery({});
  expect(await screen.findByText("Aucun élément publié")).toBeInTheDocument();
});

test("gallery shows an error state when the fetch fails", async () => {
  renderGallery({}, { listPublicItems: vi.fn().mockRejectedValue(new Error("fail")) });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
