// SPDX-License-Identifier: Apache-2.0
// Mode OIDC réel : le jeton d'audience MCP est demandé par un second
// signinSilent({scope, forceIframeAuth: true}) — cf. l'en-tête de
// useMcpToken.ts pour le pourquoi (le drapeau forceIframeAuth force la
// branche iframe d'oidc-client-ts, seule à transmettre `scope` au
// fournisseur ; la branche refresh-token, elle, le perd silencieusement,
// et un grant refresh_token ne réapplique de toute façon jamais le mapper
// d'audience côté Keycloak).
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const oidc = { signinSilent: vi.fn() };
vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }));

const MCP_SCOPE = "openid profile email geostudio-mcp-audience";

beforeEach(() => {
  oidc.signinSilent.mockReset();
  oidc.signinSilent.mockResolvedValue({ access_token: "real-mcp-token", expires_in: 3600 });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useMcpToken (real OIDC mode)", () => {
  it("requests a silent sign-in carrying the MCP scope and forceIframeAuth", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const token = await result.current();

    expect(token).toBe("real-mcp-token");
    expect(oidc.signinSilent).toHaveBeenCalledTimes(1);
    expect(oidc.signinSilent).toHaveBeenCalledWith({ scope: MCP_SCOPE, forceIframeAuth: true });
  });

  it("serves a still-valid token from memory instead of re-requesting one", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    expect(await result.current()).toBe("real-mcp-token");
    expect(await result.current()).toBe("real-mcp-token");
    expect(oidc.signinSilent).toHaveBeenCalledTimes(1);
  });

  it("re-requests a token once the cached one approaches its expiry", async () => {
    vi.useFakeTimers();
    oidc.signinSilent
      .mockResolvedValueOnce({ access_token: "first-token", expires_in: 60 })
      .mockResolvedValueOnce({ access_token: "second-token", expires_in: 60 });
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());

    expect(await result.current()).toBe("first-token");
    // 60s de durée de vie moins le buffer de 30s : encore valide à 20s…
    vi.advanceTimersByTime(20_000);
    expect(await result.current()).toBe("first-token");
    expect(oidc.signinSilent).toHaveBeenCalledTimes(1);
    // …périmé à 40s.
    vi.advanceTimersByTime(20_000);
    expect(await result.current()).toBe("second-token");
    expect(oidc.signinSilent).toHaveBeenCalledTimes(2);
  });

  it("throws a readable error when the silent sign-in yields no access token", async () => {
    oidc.signinSilent.mockResolvedValue(null);
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });
});
