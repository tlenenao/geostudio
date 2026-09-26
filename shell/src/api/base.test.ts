// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import { createBase, requestBlob } from "./base";
import { CoreUnreachableError } from "./CoreUnreachableError";
import { ApiError } from "./ApiError";

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

describe("createBase — ApiError RFC 7807 (SP-B5)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("jette une ApiError portant title+detail RFC 7807 sur une réponse d'erreur", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ title: "Conflict", detail: "quota d'items du tenant dépassé : 1/1" }),
            { status: 409, headers: { "content-type": "application/problem+json" } },
          ),
        ),
    );
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await expect(base.request("POST", "/items")).rejects.toMatchObject({
      status: 409,
      title: "Conflict",
      detail: "quota d'items du tenant dépassé : 1/1",
    });
  });

  it("jette une ApiError sans title/detail si le corps n'est pas parsable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    let caught: unknown;
    try {
      await base.request("GET", "/items");
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({ status: 500, title: undefined, detail: undefined });
  });

  it("porte retryAfter (secondes) depuis l'en-tête Retry-After sur un 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ title: "Too Many Requests", detail: "rate limit exceeded for items" }),
          {
            status: 429,
            headers: { "content-type": "application/problem+json", "Retry-After": "60" },
          },
        ),
      ),
    );
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await expect(base.request("GET", "/items")).rejects.toMatchObject({
      status: 429,
      retryAfter: 60,
    });
  });

  it("ignore un en-tête Retry-After absent ou non numérique, même sur un 429", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 429 })));
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await expect(base.request("GET", "/items")).rejects.toMatchObject({
      status: 429,
      retryAfter: undefined,
    });
  });
});

describe("requestBlob — ApiError RFC 7807 (SP-B5)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("jette une ApiError portant title+detail sur un export refusé", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ title: "Payload Too Large", detail: "too many entities" }), {
          status: 413,
          headers: { "content-type": "application/problem+json" },
        }),
      ),
    );
    await expect(
      requestBlob("http://core.test", () => undefined, "GET", "/export/items"),
    ).rejects.toMatchObject({
      status: 413,
      title: "Payload Too Large",
      detail: "too many entities",
    });
  });
});
