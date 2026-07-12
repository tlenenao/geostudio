import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
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

test("shows brand, username and sign-out", async () => {
  render(
    <MemoryRouter>
      <AppLayout><div>content</div></AppLayout>
    </MemoryRouter>,
  );
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByText("alice")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /déconnexion/i }));
  expect(authState.signOut).toHaveBeenCalled();
});
