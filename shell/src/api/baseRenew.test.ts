// SPDX-License-Identifier: Apache-2.0
// P07.06 : sur 401, renouvellement silencieux puis rejeu unique ; à défaut, l'erreur remonte.
import { afterEach, expect, it, vi } from "vitest";
import { createBase, requestBlob } from "./base";

afterEach(() => vi.unstubAllGlobals());

const ok = () => new Response("{}", { status: 200 });
const unauthorized = () => new Response("", { status: 401 });

it("401 puis jeton renouvelé : la requête est rejouée avec le nouveau jeton", async () => {
  const fetchSpy = vi.fn().mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const onUnauthorized = vi.fn().mockResolvedValue("fresh");
  const base = createBase({ coreUrl: "http://c", getToken: () => "old", onUnauthorized });
  await base.request("GET", "/items");
  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(fetchSpy.mock.calls[1][1].headers.Authorization).toBe("Bearer fresh");
});

it("renouvellement impossible : l'ApiError 401 remonte, sans rejeu", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(unauthorized());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({
    coreUrl: "http://c",
    getToken: () => "old",
    onUnauthorized: async () => undefined,
  });
  await expect(base.request("GET", "/items")).rejects.toMatchObject({ status: 401 });
  expect(fetchSpy).toHaveBeenCalledTimes(1);
});

it("authFetch et requestBlob renouvellent aussi sur 401 (fetch hors request())", async () => {
  const fetchSpy = vi
    .fn()
    .mockResolvedValueOnce(unauthorized())
    .mockResolvedValueOnce(ok())
    .mockResolvedValueOnce(unauthorized())
    .mockResolvedValueOnce(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({
    coreUrl: "http://c",
    getToken: () => "old",
    onUnauthorized: async () => "fresh",
  });
  const res = await base.authFetch("http://c/v1/x", { method: "POST" });
  expect(res.ok).toBe(true);
  expect(fetchSpy.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer fresh");
  await requestBlob("http://c/v1", () => "old", "GET", "/y", undefined, undefined, base.renewToken);
  expect(fetchSpy).toHaveBeenCalledTimes(4);
  expect(fetchSpy.mock.calls[3][1].headers.Authorization).toBe("Bearer fresh");
});

it("pas de renouvellement sans jeton, et un seul pour des 401 parallèles", async () => {
  const onUnauthorized = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => unauthorized()),
  );
  const anon = createBase({ coreUrl: "http://c", getToken: () => undefined, onUnauthorized });
  await expect(anon.request("GET", "/a")).rejects.toMatchObject({ status: 401 });
  expect(onUnauthorized).not.toHaveBeenCalled();

  const authed = createBase({ coreUrl: "http://c", getToken: () => "t", onUnauthorized });
  await Promise.allSettled([authed.request("GET", "/a"), authed.request("GET", "/b")]);
  expect(onUnauthorized).toHaveBeenCalledTimes(1);
});

it("P30.03 fetchUrl : jeton et lien de partage seulement si authenticated", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({
    coreUrl: "http://c",
    getToken: () => "tok",
    getShareLinkToken: () => "share",
  });
  await base.fetchUrl("http://c/v1/collections/x/tiles/0/0/0.mvt", { authenticated: true });
  const h = fetchSpy.mock.calls[0][1].headers as Headers;
  expect(h.get("Authorization")).toBe("Bearer tok");
  expect(h.get("X-Share-Link-Token")).toBe("share");
  await base.fetchUrl("http://evil.example/x.geojson");
  expect(fetchSpy.mock.calls[1][1].headers).toBeUndefined();
});

it("REV-290 : authFetch lève hors du cœur, sans requête ni lecture du jeton", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const getToken = vi.fn().mockReturnValue("tok");
  const base = createBase({ coreUrl: "http://c", getToken });
  for (const url of [
    "https://evil.example/x",
    "http://c.evil.example/v1/x", // hôte voisin
    "http://c:81/v1/x", // autre port = autre origine
    "http://c/v1evil/x", // préfixe de chemin voisin
    "http://c/other", // même origine, hors /v1
    "http://c/v1/../admin", // traversée normalisée hors /v1
    "//evil.example/v1/x", // protocole-relatif
  ]) {
    await expect(base.authFetch(url), url).rejects.toThrow(/not served by the core/);
  }
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(getToken).not.toHaveBeenCalled();
});

it("REV-290 : authFetch accepte l'URL absolue du cœur et l'URL relative résolue contre lui", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({ coreUrl: "http://c", getToken: () => "tok" });
  await base.authFetch("http://c/v1/items?x=1");
  await base.authFetch("/v1/items");
  expect(fetchSpy.mock.calls[0][0]).toBe("http://c/v1/items?x=1");
  expect(fetchSpy.mock.calls[1][0]).toBe("http://c/v1/items");
  for (const call of fetchSpy.mock.calls) {
    expect((call[1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  }
});

it("REV-290 : fetchUrl authenticated vers un hôte tiers est refusé (jamais de jeton hors cœur)", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({ coreUrl: "http://c", getToken: () => "tok" });
  await expect(
    base.fetchUrl("http://evil.example/x.geojson", { authenticated: true }),
  ).rejects.toThrow(/not served by the core/);
  expect(fetchSpy).not.toHaveBeenCalled();
});
