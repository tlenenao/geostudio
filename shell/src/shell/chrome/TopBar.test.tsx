// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { AuthState } from "../../auth/useAuth";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../NewItemButton", () => ({ NewItemButton: () => <button>Nouveau</button> }));
vi.mock("../ImportFileButton", () => ({
  ImportFileButton: () => <button>Importer un fichier</button>,
}));
vi.mock("../Tileset3DUploadButton", () => ({
  Tileset3DUploadButton: () => <button>Téléverser un tileset</button>,
}));
vi.mock("./NotificationBell", () => ({
  NotificationBell: () => <button>Notifications</button>,
}));

const { TopBar } = await import("./TopBar");

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <TopBar tileset3dEnabled={false} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche la marque, Nouveau, Importer, et le compte", () => {
  renderBar();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Importer un fichier" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compte" })).toBeInTheDocument();
});

test("masque le bouton tileset 3D quand la capacité est coupée", () => {
  renderBar();
  expect(screen.queryByRole("button", { name: "Téléverser un tileset" })).not.toBeInTheDocument();
});
