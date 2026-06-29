import { render, screen } from "@testing-library/react";
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

afterEach(() => {
  authState.isLoading = false;
  authState.isAuthenticated = false;
  authState.error = null;
  (authState.signIn as ReturnType<typeof vi.fn>).mockClear();
});

test("shows loading while auth resolves", () => {
  authState.isLoading = true;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("triggers signIn and hides children when unauthenticated", () => {
  authState.isAuthenticated = false;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(authState.signIn).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("renders children when authenticated", () => {
  authState.isAuthenticated = true;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(screen.getByText("secret")).toBeInTheDocument();
});

test("renders an error and does not signIn when auth errored", () => {
  authState.isAuthenticated = false;
  authState.error = "boom";
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(authState.signIn).not.toHaveBeenCalled();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});
