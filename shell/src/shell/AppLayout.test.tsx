// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AuthState } from "../auth/useAuth";

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
});

test("shows the read-only demo banner when the instance is in read-only mode", async () => {
  server.use(http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })));
  renderLayout();
  expect(
    await screen.findByText(
      "Mode démo — lecture seule, les modifications ne sont pas enregistrées.",
    ),
  ).toBeInTheDocument();
});

test("hides the read-only demo banner by default", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByText(/Mode démo/)).not.toBeInTheDocument();
});
