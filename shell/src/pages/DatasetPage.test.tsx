// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DatasetPage } from "./DatasetPage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: false, username: null,
  error: null, getAccessToken: () => undefined, signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

const collection: CollectionAdmin = {
  id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
  isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
  canWrite: false, featureCount: 2, owner: null,
};

function renderPage(client: Partial<ItemClient>, collectionId = "parcs") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/public/datasets/${collectionId}`]}>
          <DatasetPage collectionId={collectionId} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("200: renders the collection's chrome, download buttons, and the AppRenderer preview", async () => {
  renderPage({
    getCollection: vi.fn().mockResolvedValue(collection),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByRole("heading", { name: "Parcs" })).toBeInTheDocument();
  expect(screen.getByText("Parcs publics")).toBeInTheDocument();
  expect(screen.getByText(/2 entités/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Télécharger GeoJSON" })).toBeInTheDocument();
});

test("404: shows a not-found message without leaking whether the collection exists", async () => {
  renderPage({ getCollection: vi.fn().mockRejectedValue(new Error("404")) }, "private-x");
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/private-x/i);
});
