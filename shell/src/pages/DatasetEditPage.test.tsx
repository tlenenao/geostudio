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

  await screen.findByLabelText("Libellé de nom");
  await userEvent.type(screen.getByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.columns.nom.label).toBe("Nom du parc");
});

test("edits the time field and reacts-to-extent flag, and saves them with the columns", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.selectOptions(screen.getByLabelText("Colonne temporelle"), "nom");
  await userEvent.click(screen.getByLabelText("Réagir au déplacement de la carte"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.timeField).toBe("nom");
  expect(savedConfig.reactsToExtent).toBe(true);
});

test("time field defaults to the empty option (no temporal context)", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn(),
  });
  await screen.findByLabelText("Libellé de nom");
  expect(screen.getByLabelText("Colonne temporelle")).toHaveValue("");
  expect(screen.getByLabelText("Réagir au déplacement de la carte")).not.toBeChecked();
});

test("adding a cross-filter link and saving includes it in the saved payload", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [{ pk: "ds-2", resourceType: "dataset", title: "Incidents", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false }],
      total: 1, page: 1, pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un lien" }));
  await userEvent.selectOptions(screen.getByLabelText("Dataset cible"), "ds-2");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "", targetField: "" },
  ]);
});

test("removing a cross-filter link drops it from the draft before saving", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue({
      ...datasetConfig,
      crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "attribute" as const, sourceField: "nom", targetField: "nom" }],
    }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
    updateItem: vi.fn().mockResolvedValue(item),
    listItems: vi.fn().mockResolvedValue({
      items: [{ pk: "ds-2", resourceType: "dataset", title: "Incidents", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false }],
      total: 1, page: 1, pageSize: 100,
    }),
  });

  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer le lien" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));

  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalled());
  const [, savedConfig] = saveDatasetConfig.mock.calls[0];
  expect(savedConfig.crossFilterLinks).toEqual([]);
});

test("offers CSV/XLSX/GeoJSON/GPKG export when the collection has geometry, and downloads on click", async () => {
  const blob = new Blob(["a,b\n1,2\n"], { type: "text/csv" });
  const exportDataSource = vi.fn().mockResolvedValue({ blob, filename: "villes.csv" });
  const createObjectURL = vi.fn().mockReturnValue("blob:fake");
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });

  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue({ ...schema, geometry: { column: "geometry", type: "Point", srid: 4326 } }),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
    exportDataSource,
  });

  await screen.findByText(/Dataset partagé/);
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(
    expect.objectContaining({ type: "features", datasetId: "ds-1", query: {} }), "csv",
  );
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("a failed export surfaces an inline error message instead of failing silently", async () => {
  const exportDataSource = vi.fn().mockRejectedValue(new Error("Request failed: 413 GET /collections/parcs/export/items"));

  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue({ ...schema, geometry: { column: "geometry", type: "Point", srid: 4326 } }),
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
    exportDataSource,
  });

  await screen.findByText(/Dataset partagé/);
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));

  expect(await screen.findByRole("alert")).toHaveTextContent("413");
});

test("only offers CSV/XLSX when the collection has no geometry", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema), // schema.geometry is already null
    saveDatasetConfig: vi.fn(),
    updateItem: vi.fn().mockResolvedValue(item),
  });
  await screen.findByText(/Dataset partagé/);
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});
