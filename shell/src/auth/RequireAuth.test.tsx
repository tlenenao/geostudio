// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { AuthState } from "./useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: false,
  username: null,
  error: null,
  getAccessToken: () => undefined,
  signIn: vi.fn(),
  signOut: vi.fn(),
};

vi.mock("./useAuth", () => ({ useAuth: () => authState }));

// Import after the mock is registered.
const { RequireAuth } = await import("./RequireAuth");

function renderAt(path: string, children: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RequireAuth>{children}</RequireAuth>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authState.isLoading = false;
  authState.isAuthenticated = false;
  authState.error = null;
  (authState.signIn as ReturnType<typeof vi.fn>).mockClear();
});

test("shows loading while auth resolves", () => {
  authState.isLoading = true;
  renderAt("/", <div>secret</div>);
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("triggers signIn and hides children when unauthenticated", () => {
  authState.isAuthenticated = false;
  renderAt("/", <div>secret</div>);
  expect(authState.signIn).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("renders children when authenticated", () => {
  authState.isAuthenticated = true;
  renderAt("/", <div>secret</div>);
  expect(screen.getByText("secret")).toBeInTheDocument();
});

test("renders an error and does not signIn when auth errored", () => {
  authState.isAuthenticated = false;
  authState.error = "boom";
  renderAt("/", <div>secret</div>);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(authState.signIn).not.toHaveBeenCalled();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

it("renders children without triggering signIn when exportToken is present, even though not authenticated", () => {
  authState.isAuthenticated = false;
  renderAt("/maps/1?exportToken=abc123", <div>contenu protégé</div>);
  expect(screen.getByText("contenu protégé")).toBeInTheDocument();
  expect(authState.signIn).not.toHaveBeenCalled();
});
