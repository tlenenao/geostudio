import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
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

function renderLayout() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <AppLayout><div>content</div></AppLayout>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("shows brand, username and sign-out", async () => {
  renderLayout();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByText("alice")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /déconnexion/i }));
  expect(authState.signOut).toHaveBeenCalled();
});

test("shows the admin link only when the current user is admin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "Administration" })).toBeInTheDocument();
});

test("hides the admin link for a non-admin user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
});
