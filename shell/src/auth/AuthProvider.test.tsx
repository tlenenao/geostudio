// SPDX-License-Identifier: Apache-2.0
// REV-267 : un visiteur anonyme de /public ne charge jamais oidc-client-ts.
import { act, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../config";

let oidcLoaded = 0;
vi.mock("./OidcAuthProvider", async () => {
  oidcLoaded += 1;
  const { AuthContext } = await import("./useAuth");
  return {
    default: ({
      signInOnMount,
      children,
    }: {
      signInOnMount?: boolean;
      children: React.ReactNode;
    }) => (
      <AuthContext.Provider
        value={{
          isLoading: false,
          isAuthenticated: false,
          username: "from-oidc",
          error: null,
          getAccessToken: () => undefined,
          signIn: () => {},
          signOut: () => {},
        }}
      >
        <span data-testid="sign-on-mount">{String(!!signInOnMount)}</span>
        {children}
      </AuthContext.Provider>
    ),
  };
});

const { AuthProvider, isAnonymousLanding } = await import("./AuthProvider");
const { useAuth } = await import("./useAuth");

const config = { authMode: "oidc" } as unknown as AppConfig;

function Probe() {
  const a = useAuth();
  return (
    <button onClick={a.signIn}>
      {a.isAuthenticated ? "auth" : "anon"}:{a.username ?? "-"}
    </button>
  );
}

afterEach(() => window.history.replaceState({}, "", "/"));

describe("isAnonymousLanding", () => {
  it.each([
    ["/public", "", true],
    ["/public/items/3", "", true],
    ["/public", "?code=a&state=b", false],
    ["/publicity", "", false],
    ["/", "", false],
    ["/maps", "", false],
  ])("%s%s -> %s", (pathname, search, expected) => {
    expect(isAnonymousLanding({ pathname, search })).toBe(expected);
  });
});

describe("AuthProvider charge oidc à la demande", () => {
  it("/public anonyme : rend sans charger le module oidc", () => {
    window.history.replaceState({}, "", "/public");
    render(
      <AuthProvider config={config}>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByRole("button").textContent).toBe("anon:-");
    expect(oidcLoaded).toBe(0);
  });

  it("signIn depuis /public charge oidc puis demande la connexion", async () => {
    window.history.replaceState({}, "", "/public");
    render(
      <AuthProvider config={config}>
        <Probe />
      </AuthProvider>,
    );
    act(() => screen.getByRole("button").click());
    await waitFor(() => expect(screen.getByTestId("sign-on-mount").textContent).toBe("true"));
    expect(oidcLoaded).toBe(1);
  });

  it("route authentifiée : oidc chargé d'emblée", async () => {
    window.history.replaceState({}, "", "/maps");
    render(
      <AuthProvider config={config}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button").textContent).toBe("anon:from-oidc"));
  });
});

describe("graphe de modules", () => {
  it("useAuth.ts et AuthProvider.tsx n'importent pas oidc statiquement", () => {
    for (const f of ["./useAuth.ts", "./AuthProvider.tsx"]) {
      const src = readFileSync(new URL(f, import.meta.url), "utf8");
      expect(src).not.toMatch(/from "(react-oidc-context|oidc-client-ts)"/);
      expect(src).not.toMatch(/from "\.\/OidcAuthProvider"/);
    }
  });
});
