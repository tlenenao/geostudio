// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../api/types";
import { DatasetDownloadButtons } from "./DatasetDownloadButtons";

const schema: CollectionSchema = {
  collection: "parcs", pk: "id", geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

function renderButtons(featureCount: number | null, clientOverrides: Partial<ItemClient> = {}) {
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    queryDataSource: vi.fn().mockResolvedValue([]),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DatasetDownloadButtons collectionId="parcs" featureCount={featureCount} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:mock"), writable: true, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true, configurable: true });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

test("always renders a GeoJSON download link built from the client", () => {
  renderButtons(2);
  const link = screen.getByRole("link", { name: "Télécharger GeoJSON" });
  expect(link).toHaveAttribute("href", "https://core.test/collections/parcs/items?limit=1000");
  expect(link).toHaveAttribute("download", "parcs.geojson");
});

test("enables the CSV button once the schema loads, under the 10000-row cap", async () => {
  renderButtons(2);
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  await vi.waitFor(() => expect(button).toBeEnabled());
  expect(screen.queryByText(/trop volumineux/)).not.toBeInTheDocument();
});

test("disables the CSV button above the 10000-row cap and shows the explanatory message", async () => {
  renderButtons(10001);
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  expect(button).toBeDisabled();
  expect(screen.getByText(/trop volumineux pour l'export CSV navigateur — export serveur à venir \(SP-15\)/)).toBeInTheDocument();
});

test("clicking the CSV button fetches records via the client and triggers a download", async () => {
  const client = renderButtons(1, { queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "X" }, geometry: null }]) });
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  await userEvent.click(button);
  await vi.waitFor(() => expect(client.queryDataSource).toHaveBeenCalled());
});
