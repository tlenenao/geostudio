// SPDX-License-Identifier: Apache-2.0
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

test("shows the Extensions and Collections admin links only when the current user is admin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "Extensions" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Collections" })).toBeInTheDocument();
});

test("hides the admin links for a non-admin user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "Extensions" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
});

test("shows the read-only demo banner when the instance is in read-only mode", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  renderLayout();
  expect(
    await screen.findByText("Mode démo — lecture seule, les modifications ne sont pas enregistrées."),
  ).toBeInTheDocument();
});

test("hides the read-only demo banner by default", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByText(/Mode démo/)).not.toBeInTheDocument();
});

test("shows the SQL Lab link only when the current user is an analyst", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false, isAnalyst: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "SQL Lab" })).toBeInTheDocument();
});

test("hides the SQL Lab link for a non-analyst user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "SQL Lab" })).not.toBeInTheDocument();
});
