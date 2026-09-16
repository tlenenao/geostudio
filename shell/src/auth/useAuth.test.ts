// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const oidc: {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: { profile: { preferred_username?: string }; access_token: string } | undefined;
  error: Error | undefined;
  signinRedirect: ReturnType<typeof vi.fn>;
  signoutRedirect: ReturnType<typeof vi.fn>;
} = {
  isLoading: false,
  isAuthenticated: false,
  user: undefined,
  error: undefined,
  signinRedirect: vi.fn(),
  signoutRedirect: vi.fn(),
};
vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }));

beforeEach(() => {
  oidc.isLoading = false;
  oidc.isAuthenticated = false;
  oidc.user = undefined;
  oidc.error = undefined;
  oidc.signinRedirect.mockReset();
  oidc.signoutRedirect.mockReset();
});

describe("useAuth (real OIDC mode)", () => {
  it("reflects the oidc-client loading/authenticated/username/error state", async () => {
    oidc.isLoading = true;
    oidc.isAuthenticated = true;
    oidc.user = { profile: { preferred_username: "alice" }, access_token: "tok-1" };
    oidc.error = new Error("boom");
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe("alice");
    expect(result.current.error).toBe("boom");
    expect(result.current.getAccessToken()).toBe("tok-1");
  });

  it("reports no username, no error and no access token when signed out", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    expect(result.current.username).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.getAccessToken()).toBeUndefined();
  });

  it("signIn triggers oidc signinRedirect", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    result.current.signIn();
    expect(oidc.signinRedirect).toHaveBeenCalledTimes(1);
  });

  it("signOut triggers oidc signoutRedirect", async () => {
    const { useAuth } = await import("./useAuth");
    const { result } = renderHook(() => useAuth());
    result.current.signOut();
    expect(oidc.signoutRedirect).toHaveBeenCalledTimes(1);
  });
});

describe("useAuth (mock mode)", () => {
  it("enableMockAuth switches every consumer to the fixed mock state", async () => {
    const { useAuth, enableMockAuth, isMockMode } = await import("./useAuth");
    enableMockAuth();
    expect(isMockMode()).toBe(true);
    const { result } = renderHook(() => useAuth());
    expect(result.current).toMatchObject({
      isLoading: false,
      isAuthenticated: true,
      username: "mockuser",
      error: null,
    });
    expect(result.current.getAccessToken()).toBe("mock-token");
    // signIn/signOut are no-ops in mock mode — must not touch the real oidc client.
    result.current.signIn();
    result.current.signOut();
    expect(oidc.signinRedirect).not.toHaveBeenCalled();
    expect(oidc.signoutRedirect).not.toHaveBeenCalled();
  });
});
