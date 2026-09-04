// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, CollectionAdmin, ItemClient, WidgetItem } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DatasetPage } from "./DatasetPage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: false,
  username: null,
  error: null,
  getAccessToken: () => undefined,
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

// AppRenderer est lourd à monter réellement dans ce fichier (MapView réel
// nécessite maplibre-gl mocké, hors périmètre d'un test de page) — espionné
// à la place, pour vérifier ce que DatasetPage lui transmet (patron autorisé
// par le brief Task 15, SP-40). Les deux tests existants ci-dessous ne
// vérifient que le chrome de la page (titre, description, boutons), jamais
// le rendu interne d'AppRenderer : le mock ne change aucune de leurs
// assertions.
const { appRendererMock } = vi.hoisted(() => ({
  appRendererMock: vi.fn((_props: { config: unknown; mode: string }) => null),
}));
vi.mock("../builder/AppRenderer", () => ({ AppRenderer: appRendererMock }));

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
  attachmentFields: [],
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
    getCollectionSchema: vi
      .fn()
      .mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
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

test("dérive attachmentField du premier champ attachment déclaré sur la collection et le passe au widget carte (SP-40)", async () => {
  renderPage({
    getCollection: vi.fn().mockResolvedValue(collection),
    getCollectionSchema: vi.fn().mockResolvedValue({
      collection: "parcs",
      pk: "id",
      geometry: null,
      fields: [
        { name: "nom", type: "string", required: false },
        { name: "photos", type: "attachment", required: false, label: "Photos" },
      ],
    }),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByRole("heading", { name: "Parcs" })).toBeInTheDocument();

  // AppRenderer est mocké (cf. en-tête du fichier) : on inspecte directement
  // les props qu'il a reçues plutôt que le DOM produit par le widget carte.
  const lastCall = appRendererMock.mock.calls.at(-1)?.[0] as { config: AppConfig } | undefined;
  const mapItem = lastCall?.config.layout.items.find((item: WidgetItem) => item.widget === "map");
  expect(mapItem?.props).toMatchObject({ popup: { attachmentField: "photos" } });
});
