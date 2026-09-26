// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import { createBase } from "./base";
import { CoreUnreachableError } from "./CoreUnreachableError";

describe("createBase — connectivité (SP-B7)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("transforme un fetch qui rejette (réseau coupé) en CoreUnreachableError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await expect(base.request("GET", "/items")).rejects.toThrow(CoreUnreachableError);
  });

  it("applique un timeout sur toute requête", async () => {
    const fetchSpy = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      expect(init.signal).toBeInstanceOf(AbortSignal);
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchSpy);
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await base.request("GET", "/items");
    expect(fetchSpy).toHaveBeenCalled();
  });
});
