// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

describe("useAuth (contexte)", () => {
  it("lit l'état fourni par AuthContext", async () => {
    const { useAuth, AuthContext } = await import("./useAuth");
    const state = {
      isLoading: false,
      isAuthenticated: true,
      username: "alice",
      error: null,
      getAccessToken: () => "tok",
      signIn: vi.fn(),
      signOut: vi.fn(),
    };
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => createElement(AuthContext.Provider, { value: state }, children),
    });
    expect(result.current).toBe(state);
  });

  it("lève sans <AuthProvider>", async () => {
    const { useAuth } = await import("./useAuth");
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
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
    // signIn/signOut are no-ops in mock mode.
    result.current.signIn();
    result.current.signOut();
  });
});
