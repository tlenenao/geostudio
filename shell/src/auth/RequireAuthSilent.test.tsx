// SPDX-License-Identifier: Apache-2.0
// P07.01 : un renouvellement silencieux (isLoading repasse à true, voire
// `error`) ne doit jamais démonter les enfants d'une session déjà établie.
import { render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { AuthState } from "./useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "u",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("./useAuth", () => ({ useAuth: () => authState }));
const { RequireAuth } = await import("./RequireAuth");

function Draft() {
  const [v] = useState(() => Math.random());
  return <div data-testid="draft">{v}</div>;
}

test("les enfants gardent leur état pendant un signinSilent (isLoading, puis error)", () => {
  const ui = () => (
    <MemoryRouter>
      <RequireAuth>
        <Draft />
      </RequireAuth>
    </MemoryRouter>
  );
  const { rerender } = render(ui());
  const before = screen.getByTestId("draft").textContent;

  authState.isLoading = true;
  rerender(ui());
  expect(screen.getByTestId("draft").textContent).toBe(before);

  authState.isLoading = false;
  authState.error = "silent failed";
  rerender(ui());
  expect(screen.getByTestId("draft").textContent).toBe(before);
  expect(authState.signIn).not.toHaveBeenCalled();
});
