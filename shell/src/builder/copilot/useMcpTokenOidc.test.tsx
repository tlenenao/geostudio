// SPDX-License-Identifier: Apache-2.0
// Mode OIDC réel : le jeton d'audience MCP est demandé par un POST direct
// au endpoint de token (grant_type=refresh_token), pas par signinSilent()
// — cf. l'en-tête de useMcpToken.ts pour le pourquoi (le scope y était
// silencieusement perdu, et le User stocké de la session écrasé).
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const oidc = {
  user: { refresh_token: "the-refresh-token" } as { refresh_token?: string } | null,
  settings: { authority: "https://kc.example/realms/geostudio", client_id: "geostudio-shell" },
};
vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }));

function tokenResponse(body: Record<string, unknown>, ok = true) {
  return { ok, json: async () => body } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  oidc.user = { refresh_token: "the-refresh-token" };
  fetchMock = vi.fn().mockResolvedValue(tokenResponse({ access_token: "real-mcp-token", expires_in: 3600 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useMcpToken (real OIDC mode)", () => {
  it("POSTs a refresh_token grant carrying the geostudio-mcp-audience scope", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const token = await result.current();

    expect(token).toBe("real-mcp-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://kc.example/realms/geostudio/protocol/openid-connect/token");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    const body = new URLSearchParams(init.body as URLSearchParams);
    expect(body.get("grant_type")).toBe("refresh_token");
    expect(body.get("refresh_token")).toBe("the-refresh-token");
    expect(body.get("client_id")).toBe("geostudio-shell");
    expect(body.get("scope")).toContain("geostudio-mcp-audience");
  });

  it("serves a still-valid token from memory instead of re-fetching", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    expect(await result.current()).toBe("real-mcp-token");
    expect(await result.current()).toBe("real-mcp-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("re-fetches once the cached token approaches its expiry", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(tokenResponse({ access_token: "first-token", expires_in: 60 }))
      .mockResolvedValueOnce(tokenResponse({ access_token: "second-token", expires_in: 60 }));
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());

    expect(await result.current()).toBe("first-token");
    // 60s de durée de vie moins le buffer de 30s : encore valide à 20s…
    vi.advanceTimersByTime(20_000);
    expect(await result.current()).toBe("first-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // …périmé à 40s.
    vi.advanceTimersByTime(20_000);
    expect(await result.current()).toBe("second-token");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("throws a readable error when the session has no refresh token", async () => {
    oidc.user = null;
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("throws a readable error when the authorization server refuses the grant", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse({ error: "invalid_scope" }, false));
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });

  it("throws a readable error when the response carries no access_token", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse({ expires_in: 60 }));
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });
});
