// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../api/types";
import { DatasetDownloadButtons } from "./DatasetDownloadButtons";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: null,
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
  const view = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DatasetDownloadButtons collectionId="parcs" featureCount={featureCount} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client, ...view };
}

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", {
    value: vi.fn(() => "blob:mock"),
    writable: true,
    configurable: true,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    value: vi.fn(),
    writable: true,
    configurable: true,
  });
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
  expect(
    screen.getByText(
      /trop volumineux pour l'export CSV navigateur — export serveur à venir \(SP-15\)/,
    ),
  ).toBeInTheDocument();
});

test("disables the CSV button for an unknown feature count without showing the too-large message", async () => {
  renderButtons(null);
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  expect(button).toBeDisabled();
  expect(screen.queryByText(/trop volumineux/)).not.toBeInTheDocument();
});

test("clicking the CSV button fetches records via the client and triggers a download", async () => {
  const { client } = renderButtons(1, {
    queryDataSource: vi
      .fn()
      .mockResolvedValue([{ id: 1, properties: { nom: "X" }, geometry: null }]),
  });
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  await userEvent.click(button);
  await vi.waitFor(() => expect(client.queryDataSource).toHaveBeenCalled());
});

// SP-B12b: pas de couleur Tailwind de palette codée en dur. `container`
// (pas un des deux éléments cliquables directement) : `Element.innerHTML`
// ne reflète que le balisage des ENFANTS d'un élément, jamais ses propres
// attributs — vérifié par falsification (cf. rapport de tâche) que checker
// un des deux éléments directement passait vacuously même sans correctif.
// Un seul rendu couvre les 6 occurrences liées au lien + bouton
// (border-slate-300/text-slate-700/hover:bg-slate-100 ×2) ; la 7e
// (text-slate-500, message "trop volumineux") a son propre test ci-dessous
// car elle n'apparaît que dans l'état au-dessus du plafond.
test("link and CSV button use semantic tokens, not literal Tailwind colors (SP-B12b)", async () => {
  const { container } = renderButtons(2);
  await screen.findByRole("link", { name: "Télécharger GeoJSON" });
  await screen.findByRole("button", { name: "Télécharger CSV" });
  expectTokenizedClasses(container);
});

test("too-large message uses semantic tokens, not literal Tailwind colors (SP-B12b)", async () => {
  const { container } = renderButtons(10001);
  await screen.findByText(
    /trop volumineux pour l'export CSV navigateur — export serveur à venir \(SP-15\)/,
  );
  expectTokenizedClasses(container);
});

test("annonce que le GeoJSON est borné aux 1000 premières entités (P29.03)", async () => {
  renderButtons(500000);
  expect(
    screen.getByText("Le GeoJSON ne contient que les 1000 premières entités sur 500000."),
  ).toBeInTheDocument();
});

test("aucune annonce de troncature sous 1000 entités", async () => {
  renderButtons(900);
  expect(screen.queryByText(/premières entités/)).not.toBeInTheDocument();
});
