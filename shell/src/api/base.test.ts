// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createBase, requestBlob } from "./base";
import { CoreUnreachableError } from "./CoreUnreachableError";
import { ApiError } from "./ApiError";
import { createAppsMethods } from "./domains/apps";

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

describe("requestBlob — export asynchrone 202 (REV-283e)", () => {
  // Chunk lazy préchargé : l'import dynamique ne doit pas courir sous fake timers.
  beforeAll(() => import("./exportJob"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

  it("sonde le statut puis télécharge resultUrl", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
      .mockResolvedValueOnce(json({ status: "running" }))
      .mockResolvedValueOnce(
        json({ status: "done", resultUrl: "https://s3.test/f", filename: "v.geojson" }),
      )
      .mockResolvedValueOnce(new Response("DATA"));
    vi.stubGlobal("fetch", fetchMock);
    const p = requestBlob(
      "http://core.test/v1",
      () => "tok",
      "GET",
      "/collections/c1/export/items?format=geojson",
    );
    await vi.advanceTimersByTimeAsync(5000);
    const out = await p;
    expect(out.filename).toBe("v.geojson");
    expect(out.blob.size).toBe(4);
    expect(fetchMock.mock.calls[1][0]).toBe("http://core.test/v1/collections/c1/export/jobs/j1");
    expect(fetchMock.mock.calls[3][0]).toBe("https://s3.test/f");
    expect(fetchMock.mock.calls[3][1].headers).toBeUndefined();
  });

  it("rejette avec le message d'un job failed", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
        .mockResolvedValueOnce(json({ status: "failed", error: "too many" })),
    );
    await expect(
      requestBlob("http://core.test", () => "t", "GET", "/collections/c1/export/items"),
    ).rejects.toThrow("Échec de l'export de données (statut : Échoué)");
  });

  it("relit le jeton à chaque tour de sondage", async () => {
    vi.useFakeTimers();
    let tok = "t1";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
      .mockResolvedValueOnce(json({ status: "running" }))
      .mockResolvedValueOnce(json({ status: "done", resultUrl: "https://s3.test/f" }))
      .mockResolvedValueOnce(new Response("D"));
    vi.stubGlobal("fetch", fetchMock);
    const p = requestBlob("http://core.test", () => tok, "GET", "/collections/c1/export/items");
    await vi.advanceTimersByTimeAsync(0);
    tok = "t2";
    await vi.advanceTimersByTimeAsync(5000);
    await p;
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer t1");
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer t2");
  });

  it("renouvelle le jeton sur un 401 pendant le sondage", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(json({ status: "done", resultUrl: "https://s3.test/f" }))
      .mockResolvedValueOnce(new Response("D"));
    vi.stubGlobal("fetch", fetchMock);
    const renew = vi.fn().mockResolvedValue("fresh");
    await requestBlob(
      "http://core.test",
      () => "old",
      "GET",
      "/collections/c1/export/items",
      undefined,
      undefined,
      renew,
    );
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
  });

  it("s'arrête quand le signal est abandonné (sleep interrompu)", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
      .mockImplementation(async () => json({ status: "running" }));
    vi.stubGlobal("fetch", fetchMock);
    const ac = new AbortController();
    const p = requestBlob(
      "http://core.test",
      () => "t",
      "GET",
      "/collections/c1/export/items",
      undefined,
      undefined,
      undefined,
      ac.signal,
    );
    const assertion = expect(p).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(100);
    const calls = fetchMock.mock.calls.length;
    ac.abort();
    await assertion;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("abandonne après 15 min", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({ jobId: "j1" }, 202))
        .mockImplementation(async () => json({ status: "running" })),
    );
    const p = requestBlob("http://core.test", () => "t", "GET", "/collections/c1/export/items");
    const assertion = expect(p).rejects.toThrow("export timed out");
    await vi.advanceTimersByTimeAsync(16 * 60_000);
    await assertion;
  });
});

// Revue finale Vague B, I2 : fetch simulé qui honore réellement le signal
// d'abandon (comme un vrai fetch) et ne répond qu'après `delayMs`.
function slowFetch(delayMs: number, body: unknown) {
  return vi.fn().mockImplementation(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        const timer = setTimeout(
          () => resolve(new Response(JSON.stringify(body), { status: 200 })),
          delayMs,
        );
        init.signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          reject(new DOMException("aborted", "AbortError"));
        });
      }),
  );
}

describe("timeouts longs et abandon pendant la lecture du corps (revue finale Vague B, I2)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("copilotTurn ne coupe pas un tour de 20s (le cœur accorde 30s)", async () => {
    vi.useFakeTimers();
    // AbortSignal.timeout() n'est pas piloté par les faux timers de vitest :
    // on le remplace par un setTimeout (lui, simulé) qui abandonne après `ms`.
    vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
      const ctrl = new AbortController();
      setTimeout(() => ctrl.abort(new DOMException("timeout", "TimeoutError")), ms);
      return ctrl.signal;
    });
    vi.stubGlobal("fetch", slowFetch(20_000, { reply: "ok" }));
    const apps = createAppsMethods(
      createBase({ coreUrl: "http://core.test", getToken: () => undefined }),
    );
    const turn = apps.copilotTurn(undefined, {
      message: "bonjour",
      history: [],
      currentConfig: {},
    } as unknown as Parameters<typeof apps.copilotTurn>[1]);
    const settled = turn.then(
      (v) => ({ ok: true as const, v }),
      (e: unknown) => ({ ok: false as const, e }),
    );
    await vi.advanceTimersByTimeAsync(20_000);
    const result = await settled;
    expect(result).toEqual({ ok: true, v: { reply: "ok" } });
  });

  it("request() convertit un AbortError levé par res.json() en CoreUnreachableError", async () => {
    const res = new Response("{}", { status: 200 });
    vi.spyOn(res, "json").mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    await expect(base.request("GET", "/items")).rejects.toBeInstanceOf(CoreUnreachableError);
  });

  it("request() relance telle quelle une erreur de JSON invalide", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("pas du json", { status: 200 })));
    const base = createBase({ coreUrl: "http://core.test", getToken: () => undefined });
    const err = await base.request("GET", "/items").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(SyntaxError);
  });

  it("requestBlob() convertit un AbortError levé par res.blob() en CoreUnreachableError", async () => {
    const res = new Response("x", { status: 200 });
    vi.spyOn(res, "blob").mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));
    await expect(
      requestBlob("http://core.test", () => undefined, "GET", "/export/items"),
    ).rejects.toBeInstanceOf(CoreUnreachableError);
  });
});

describe("createBase — fetchGeoJsonPage ne fuit pas le jeton (P30 revue)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const geojson = () => new Response(JSON.stringify({ features: [] }), { status: 200 });

  it("n'envoie aucun jeton à une URL hors du cœur", async () => {
    const fetchSpy = vi.fn().mockImplementation(() => Promise.resolve(geojson()));
    vi.stubGlobal("fetch", fetchSpy);
    const base = createBase({ coreUrl: "http://core.test", getToken: () => "secret-tok" });
    await base.fetchGeoJsonPage("https://attacker.example/data.geojson");
    const headers = new Headers((fetchSpy.mock.calls[0][1] as RequestInit).headers);
    expect(headers.get("authorization")).toBeNull();
  });

  it("envoie le jeton à une URL servie par le cœur", async () => {
    const fetchSpy = vi.fn().mockImplementation(() => Promise.resolve(geojson()));
    vi.stubGlobal("fetch", fetchSpy);
    const base = createBase({ coreUrl: "http://core.test", getToken: () => "secret-tok" });
    await base.fetchGeoJsonPage("http://core.test/v1/collections/c1/items");
    const headers = new Headers((fetchSpy.mock.calls[0][1] as RequestInit).headers);
    expect(headers.get("authorization")).toBe("Bearer secret-tok");
  });
});
