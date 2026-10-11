// SPDX-License-Identifier: Apache-2.0
// OidcAuthProvider (REV-267, chargé à la demande) : passerelle react-oidc-context -> useAuth().
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../config";

const oidc: {
  isLoading: boolean;
  isAuthenticated: boolean;
  user:
    { profile: { preferred_username?: string; sub?: string }; access_token: string } | undefined;
  error: Error | undefined;
  signinRedirect: ReturnType<typeof vi.fn>;
  signoutRedirect: ReturnType<typeof vi.fn>;
  signinSilent: ReturnType<typeof vi.fn>;
} = {
  isLoading: false,
  isAuthenticated: false,
  user: undefined,
  error: undefined,
  signinRedirect: vi.fn(),
  signoutRedirect: vi.fn(),
  signinSilent: vi.fn(),
};
vi.mock("react-oidc-context", () => ({
  useAuth: () => oidc,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const { default: OidcAuthProvider } = await import("./OidcAuthProvider");
const { useAuth: useAuthHook } = await import("./useAuth");

const config = {
  authMode: "oidc",
  oidcAuthority: "http://kc",
  oidcClientId: "c",
  oidcRedirectUri: "http://localhost/",
} as unknown as AppConfig;

function renderAuth(signInOnMount = false) {
  return renderHook(() => useAuthHook(), {
    wrapper: ({ children }) => (
      <OidcAuthProvider config={config} signInOnMount={signInOnMount}>
        {children}
      </OidcAuthProvider>
    ),
  });
}

beforeEach(() => {
  oidc.isLoading = false;
  oidc.isAuthenticated = false;
  oidc.user = undefined;
  oidc.error = undefined;
  oidc.signinRedirect.mockReset();
  oidc.signoutRedirect.mockReset();
  oidc.signinSilent.mockReset();
});

describe("OidcAuthProvider -> useAuth", () => {
  it("reflects the oidc-client loading/authenticated/username/error state", () => {
    oidc.isLoading = true;
    oidc.isAuthenticated = true;
    oidc.user = { profile: { preferred_username: "alice" }, access_token: "tok-1" };
    oidc.error = new Error("boom");
    const { result } = renderAuth();
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe("alice");
    expect(result.current.error).toBe("boom");
    expect(result.current.getAccessToken()).toBe("tok-1");
  });

  it("reports no username, no error and no access token when signed out", () => {
    const { result } = renderAuth();
    expect(result.current.username).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.getAccessToken()).toBeUndefined();
  });

  it("signIn triggers oidc signinRedirect", () => {
    const { result } = renderAuth();
    result.current.signIn();
    expect(oidc.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it("signOut triggers oidc signoutRedirect", () => {
    const { result } = renderAuth();
    result.current.signOut();
    expect(oidc.signoutRedirect).toHaveBeenCalledTimes(1);
  });

  it("renewToken renvoie le jeton du signinSilent, ou undefined s'il échoue", async () => {
    const { result } = renderAuth();
    oidc.signinSilent.mockResolvedValueOnce({ access_token: "tok-2" });
    expect(await result.current.renewToken?.()).toBe("tok-2");
    oidc.signinSilent.mockResolvedValueOnce(null);
    expect(await result.current.renewToken?.()).toBeUndefined();
    oidc.signinSilent.mockRejectedValueOnce(new Error("iframe timeout"));
    expect(await result.current.renewToken?.()).toBeUndefined();
  });

  it("signInOnMount enchaîne sur la redirection une seule fois (connexion demandée depuis /public)", () => {
    const { rerender } = renderAuth(true);
    expect(oidc.signinRedirect).toHaveBeenCalledTimes(1);
    rerender();
    expect(oidc.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it("sans signInOnMount, aucune redirection automatique", () => {
    renderAuth(false);
    expect(oidc.signinRedirect).not.toHaveBeenCalled();
  });
});
