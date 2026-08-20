// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const signinSilent = vi.fn().mockResolvedValue({ access_token: "real-mcp-token" });
vi.mock("react-oidc-context", () => ({ useAuth: () => ({ signinSilent }) }));

describe("useMcpToken (real OIDC mode)", () => {
  it("calls signinSilent with the geostudio-mcp-audience scope and caches the result", async () => {
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const first = await result.current();
    expect(first).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledWith({ scope: "openid profile email geostudio-mcp-audience" });

    const second = await result.current();
    expect(second).toBe("real-mcp-token");
    expect(signinSilent).toHaveBeenCalledTimes(1); // cached, not called again
  });

  it("throws a readable error when signinSilent resolves without a token", async () => {
    signinSilent.mockResolvedValueOnce(null);
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    await expect(result.current()).rejects.toThrow(/Impossible d'obtenir un jeton MCP/);
  });
});
