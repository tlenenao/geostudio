// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, vi } from "vitest";
import { Link, MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AuthState } from "../auth/useAuth";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));
vi.mock("./NewItemButton", () => ({
  NewItemButton: () => <button>Nouveau</button>,
}));
vi.mock("./ImportFileButton", () => ({
  ImportFileButton: () => <button>Importer un fichier</button>,
}));

const { AppLayout } = await import("./AppLayout");

// jsdom n'implémente pas window.matchMedia (piège documenté pour
// @floating-ui/react-dom ; ici c'est useNarrowViewport, Task 8, qui
// l'appelle en dehors de tout mock). Stub local au fichier, jamais dans
// shell/src/test/setup.ts (CLAUDE.md, piège n°10) : matches: false pour
// que AppLayout choisisse DomainBar (des <Link>) plutôt que BottomNav
// (des <button>), seule branche où `findByRole("link", { name: ... })`
// trouve quoi que ce soit.
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
});

function renderLayout() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <AppLayout>
            <div>content</div>
          </AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("assemble TopBar, DomainBar et StatusBar autour du contenu", async () => {
  renderLayout();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Catalogue" })).toBeInTheDocument();
  expect(screen.getByText("content")).toBeInTheDocument();
  // Régression (Finding 4) : le fixture partagé /me (test/msw/handlers.ts)
  // ne portait pas version/tenantSlug (ajoutés par Task 2), donc StatusBar
  // rendait silencieusement "vundefined · undefined". Cette assertion
  // transforme le fixture en contrat vérifié plutôt qu'en décor.
  expect(await screen.findByText("v0.1.0 · demo")).toBeInTheDocument();
});

test("shows the read-only demo banner when the instance is in read-only mode", async () => {
  // GAP-31 : AppLayout lit désormais Me.capabilities (GET /me) au lieu de
  // GET /instance — surcharger /me, pas /instance, pour piloter la
  // bannière (sinon ce test resterait vert par accident, sans plus jamais
  // exercer le vrai chemin de lecture).
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        email: "alice@example.com",
        tenantId: "t1",
        role: { id: "role-creator", name: "Créateur", slug: "creator" },
        privileges: ["catalog.manage", "maps.manage", "data.view", "data.manage"],
        version: "0.1.0",
        tenantSlug: "demo",
        capabilities: {
          readOnly: true,
          etlEnabled: false,
          exportEnabled: false,
          appExportEnabled: false,
          tileset3dEnabled: false,
          terrain3dEnabled: false,
          copilotEnabled: false,
          adminToolsEnabled: false,
          quotasEnabled: false,
        },
      }),
    ),
  );
  const { container } = renderLayout();
  expect(
    await screen.findByText(
      "Mode démo — lecture seule, les modifications ne sont pas enregistrées.",
    ),
  ).toBeInTheDocument();
  // SP-B12c : la bannière de mode démo n'a pas de couleur Tailwind codée en
  // dur.
  expectTokenizedClasses(container);
});

test("hides the read-only demo banner by default", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByText(/Mode démo/)).not.toBeInTheDocument();
});

// D07 (Task 21) : le montage paresseux de CommandPalette et l'écouteur
// clavier Ctrl/Cmd+K vivent dans AppLayout lui-même — non couverts par
// CommandPalette.test.tsx (qui rend le composant directement, `open` déjà
// vrai) ni par TopBar.test.tsx (qui mocke `onOpenPalette`). Sans ce test,
// la vraie intégration clavier n'était exercée par rien — trouvé en
// clôture de Vague C (Tâche 40) via le plancher de santé de fonctionnalité
// (`cartes-rendu-export-headless...` partage `AppLayout.tsx` comme seule
// preuve, sa couverture de lignes a baissé sous le plancher moyenne-priorité
// à cause des branches ⌘K jamais exercées).
test("Ctrl/Cmd+K ouvre la palette de commandes (montage paresseux)", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  await userEvent.keyboard("{Control>}k{/Control}");
  expect(await screen.findByRole("combobox")).toBeInTheDocument();
});

test("REV-286(f) : changer de route remet le défilement de <main> en haut", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/a"]}>
          <AppLayout>
            <Link to="/b">aller plus loin</Link>
          </AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const main = screen.getByRole("main");
  main.scrollTop = 500;
  expect(main.scrollTop).toBe(500);
  await userEvent.click(screen.getByRole("link", { name: "aller plus loin" }));
  expect(main.scrollTop).toBe(0);
});
