// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item, ItemClient } from "../api/types";
import { READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { PublicCatalogPage } from "./PublicCatalogPage";

vi.mock("../config", () => ({ loadRuntimeConfig: () => ({ coreUrl: "https://core.test" }) }));

function item(pk: string, resourceType: Item["resourceType"], extra: Partial<Item> = {}): Item {
  return {
    pk,
    resourceType,
    title: `Titre ${pk}`,
    abstract: "",
    owner: "alice",
    thumbnailUrl: null,
    date: "",
    configId: null,
    isPublished: true,
    permissions: READ_ONLY_PERMISSIONS,
    license: "",
    language: "fr",
    ...extra,
  };
}

function Loc() {
  return <div data-testid="loc">{useLocation().pathname}</div>;
}

function renderCatalog(listPublicItems: ItemClient["listPublicItems"], url = "/public") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{ listPublicItems } as unknown as ItemClient}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/public" element={<PublicCatalogPage />} />
            <Route path="*" element={<Loc />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("liste les items publics sans connexion, avec <h1>, filtre type et ouverture (P35.01)", async () => {
  const list = vi.fn().mockResolvedValue({
    items: [
      item("1", "site", { slug: "portail", thumbnailUrl: "/public/items/1/thumbnail" }),
      item("2", "map"),
    ],
    total: 2,
    page: 1,
    pageSize: 12,
  });
  renderCatalog(list);
  expect(await screen.findByRole("heading", { level: 1, name: "Catalogue public" })).toBeVisible();
  expect(screen.getByRole("main")).toBeInTheDocument();
  expect(list).toHaveBeenCalledWith({ type: undefined, tag: undefined, page: 1, pageSize: 12 });
  // vignette rendue absolue vers le cœur (route publique)
  expect((await screen.findByRole("img", { name: "Titre 1" })).getAttribute("src")).toBe(
    "https://core.test/v1/public/items/1/thumbnail",
  );

  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  expect(list).toHaveBeenLastCalledWith({ type: "map", tag: undefined, page: 1, pageSize: 12 });

  await userEvent.click(screen.getAllByRole("button", { name: /ouvrir/i })[0]);
  expect(screen.getByTestId("loc")).toHaveTextContent("/sites/portail");
});

test("état vide et pagination", async () => {
  const list = vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 });
  renderCatalog(list, "/public?tag=zzz");
  expect(await screen.findByText("Aucun contenu public pour le moment.")).toBeVisible();
  expect(list).toHaveBeenCalledWith(expect.objectContaining({ tag: "zzz" }));
});
