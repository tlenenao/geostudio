// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { AuthState } from "./useAuth";
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
  const { container } = renderAt("/", <div>secret</div>);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(authState.signIn).not.toHaveBeenCalled();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
});

describe("export worker", () => {
  // readExportToken lit window.location (AppShell est au-dessus du routeur).
  afterEach(() => {
    window.sessionStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("renders children without triggering signIn when the worker injected its token, even though not authenticated", () => {
    authState.isAuthenticated = false;
    window.sessionStorage.setItem("gs_export_token", "t");
    window.history.pushState({}, "", "/maps/1?exportRender=1");
    renderAt("/maps/1?exportRender=1", <div>contenu protégé</div>);
    expect(screen.getByText("contenu protégé")).toBeInTheDocument();
    expect(authState.signIn).not.toHaveBeenCalled();
  });

  it("an ?exportToken= link alone does not bypass sign-in (AUD-024)", () => {
    authState.isAuthenticated = false;
    window.history.pushState({}, "", "/maps/1?exportToken=x&exportRender=1");
    renderAt("/maps/1?exportToken=x&exportRender=1", <div>contenu protégé</div>);
    expect(authState.signIn).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("contenu protégé")).not.toBeInTheDocument();
  });
});
