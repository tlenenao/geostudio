// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { PublicItemPage } from "./PublicItemPage";
import type { AuthState } from "../auth/useAuth";
import { READ_ONLY_PERMISSIONS } from "../auth/permissions";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

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

function renderPage(client: Partial<ItemClient>, pk = "8") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/public/items/${pk}`]}>
          <PublicItemPage pk={pk} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const item: Item = {
  pk: "8",
  resourceType: "dataset",
  title: "Mon jeu de données",
  abstract: "Une description",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: "cfg-1",
  isPublished: true,
  permissions: READ_ONLY_PERMISSIONS,
  license: "",
  language: "fr",
};

const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 1, props: { text: "Detail de l'article" } },
    ],
  },
};

test("200: renders the published item's runtime layout via AppRenderer", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(await screen.findByText("Detail de l'article")).toBeInTheDocument();
  expect(screen.queryByText(/introuvable/i)).not.toBeInTheDocument();
});

test("REV-284(b) : un <h1> (sr-only) porte le titre de l'item", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(
    await screen.findByRole("heading", { level: 1, name: "Mon jeu de données" }),
  ).toBeInTheDocument();
});

test("D50 : pose document.title/meta description une fois l'item chargé", async () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  await screen.findByText("Detail de l'article");

  expect(document.title).toBe("Mon jeu de données");
  expect(document.querySelector('meta[name="description"]')?.getAttribute("content")).toBe(
    "Une description",
  );
});

test("shows the shared LoadingState (role=status, spinner) while the config is in flight", () => {
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getPublicAppConfig: vi.fn(() => new Promise<AppConfig>(() => {})),
  });
  const status = screen.getByRole("status");
  expect(status).toHaveTextContent("Chargement…");
  expect(status.querySelector('[aria-hidden="true"]')).not.toBeNull();
});

test("fenêtre de titre obsolète : ne déclenche getPublicAppConfig qu'après le succès de getItem, même si getItem résout après getPublicAppConfig aurait pu répondre", async () => {
  let resolveItem!: (value: Item) => void;
  const itemPromise = new Promise<Item>((resolve) => {
    resolveItem = resolve;
  });
  const getPublicAppConfig = vi.fn().mockResolvedValue(config);
  renderPage({
    getItem: vi.fn(() => itemPromise),
    getPublicAppConfig,
  });

  // itemQuery est encore en vol : le repli doit rester affiché, et
  // configQuery — dont dépend le contenu visible — ne doit pas être
  // déclenchée tant que itemQuery n'a pas réussi. `findByRole` (au lieu
  // d'une assertion synchrone juste après `render`) laisse les effets
  // React Query se propager, sinon l'assertion passerait vacuously même
  // sans le correctif (queryFn appelée dans un effet, pas pendant le rendu).
  await screen.findByRole("status");
  expect(getPublicAppConfig).not.toHaveBeenCalled();
  expect(document.title).toBe("GeoStudio");
  expect(screen.queryByText("Detail de l'article")).not.toBeInTheDocument();

  // getItem résout maintenant — plus tard que getPublicAppConfig n'aurait
  // pu le faire si les deux requêtes avaient couru en parallèle (bug
  // trouvé en revue finale de Task 28 : configQuery non gardée par
  // itemQuery.isSuccess).
  resolveItem(item);
  await screen.findByText("Detail de l'article");

  expect(getPublicAppConfig).toHaveBeenCalledTimes(1);
  expect(document.title).toBe("Mon jeu de données");
  expect(document.querySelector('meta[name="description"]')?.getAttribute("content")).toBe(
    "Une description",
  );
});

test("404: shows a not-found message without leaking whether the item exists", async () => {
  const { container } = renderPage(
    {
      getItem: vi.fn().mockRejectedValue(new Error("404")),
      getPublicAppConfig: vi.fn().mockRejectedValue(new Error("404")),
    },
    "does-not-exist",
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/does-not-exist/i);
  // SP-B12b: pas de couleur Tailwind de palette codée en dur. `container`
  // (pas l'élément role="alert" lui-même) : `Element.innerHTML` ne reflète
  // que le balisage des ENFANTS d'un élément, jamais ses propres attributs
  // — vérifié par falsification (cf. rapport de tâche) que checker le <p>
  // directement passait vacuously même sans correctif.
  expectTokenizedClasses(container);
});
