// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionAdmin, ItemClient } from "../../api/types";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const collection: CollectionAdmin = {
  id: "parcs",
  title: "Parcs",
  description: "Parcs publics",
  tableName: "parcs",
  isPublic: true,
  editable: false,
  geometryType: null,
  srid: null,
  pkColumn: "id",
  permissions: { read: true, write: false, delete: false, share: false },
  featureCount: 2,
  owner: null,
};

function renderCard(
  props: Record<string, unknown>,
  clientOverrides: Partial<ItemClient> = {},
  hasSource = true,
) {
  const client = {
    getCollection: vi.fn().mockResolvedValue(collection),
    getCollectionSchema: vi
      .fn()
      .mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const DatasetCard = getWidget("datasetCard")!.Component;
  const ctx = {
    mode: "runtime",
    data: hasSource ? { loading: false, error: false, records: [], layer: "parcs" } : undefined,
  } as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DatasetCard props={props} ctx={ctx} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

test("shows a discreet message when no data source is bound", () => {
  renderCard({}, {}, false);
  expect(screen.getByText(/Aucune source de données/)).toBeInTheDocument();
});

test("renders title, description, feature count, and a link to the dataset page", async () => {
  renderCard({ dataSourceId: "ds1", showDownload: true });
  expect(await screen.findByText("Parcs")).toBeInTheDocument();
  expect(screen.getByText("Parcs publics")).toBeInTheDocument();
  expect(screen.getByText(/2 entités/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Voir le jeu de données" })).toHaveAttribute(
    "href",
    "/public/datasets/parcs",
  );
});

test("an author-set title overrides the collection's own title", async () => {
  renderCard({ dataSourceId: "ds1", title: "Nos parcs" });
  expect(await screen.findByText("Nos parcs")).toBeInTheDocument();
  expect(screen.queryByText("Parcs")).not.toBeInTheDocument();
});

test("hides the download buttons when showDownload is false", async () => {
  renderCard({ dataSourceId: "ds1", showDownload: false });
  await screen.findByText("Parcs");
  expect(screen.queryByRole("link", { name: "Télécharger GeoJSON" })).not.toBeInTheDocument();
});

test("shows the download buttons by default", async () => {
  renderCard({ dataSourceId: "ds1" });
  expect(await screen.findByRole("link", { name: "Télécharger GeoJSON" })).toBeInTheDocument();
});

test("shows a discreet not-found message for a non-public or unknown collection, without leaking detail", async () => {
  renderCard(
    { dataSourceId: "ds1" },
    { getCollection: vi.fn().mockRejectedValue(new Error("404")) },
  );
  expect(await screen.findByText(/introuvable/i)).toBeInTheDocument();
  expect(screen.queryByText(/parcs/i)).not.toBeInTheDocument();
});
