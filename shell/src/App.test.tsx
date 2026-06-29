import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
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
const { AppLayout } = await import("./shell/AppLayout");

test("shell layout shows the GeoStudio brand", () => {
  render(
    <MemoryRouter>
      <AppLayout>
        <div>x</div>
      </AppLayout>
    </MemoryRouter>,
  );
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
});
