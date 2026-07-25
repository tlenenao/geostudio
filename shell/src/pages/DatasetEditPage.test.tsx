// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionSchema, DatasetConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DatasetEditPage } from "./DatasetEditPage";

const item: Item = {
  pk: "ds-1",
  resourceType: "dataset",
  title: "Parcs",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-ds1",
  isPublished: false,
  keywords: [],
};

const datasetConfig: DatasetConfig = {
  source: "collection",
  collectionId: "parcs",
  columns: {},
};

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

function renderPage(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <DatasetEditPage pk="ds-1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("loads the dataset, shows merged columns, and saves an edited label", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
  });

  await screen.findByText("nom");
  await userEvent.type(screen.getByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.columns.nom.label).toBe("Nom du parc");
});
