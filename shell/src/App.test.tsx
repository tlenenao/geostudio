// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import type { AuthState } from "./auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("./auth/useAuth", () => ({ useAuth: () => authState }));
vi.mock("./shell/NewItemButton", () => ({
  NewItemButton: () => <button>Nouveau</button>,
}));
vi.mock("./shell/ImportFileButton", () => ({
  ImportFileButton: () => <button>Importer un fichier</button>,
}));
const { AppLayout } = await import("./shell/AppLayout");

// jsdom n'implémente pas window.matchMedia (cf. shell/src/shell/AppLayout.test.tsx) ;
// AppLayout appelle useNarrowViewport (Task 8) sans mock ici. Stub local au
// fichier (CLAUDE.md, piège n°10), jamais dans shell/src/test/setup.ts.
vi.stubGlobal(
  "matchMedia",
  vi.fn().mockReturnValue({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }),
);

test("shell layout shows the GeoStudio brand", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <AppLayout>
            <div>x</div>
          </AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
});
