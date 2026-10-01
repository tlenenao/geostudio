// SPDX-License-Identifier: Apache-2.0
// P07.06 : sur 401, renouvellement silencieux puis rejeu unique ; à défaut, l'erreur remonte.
import { afterEach, expect, it, vi } from "vitest";
import { createBase } from "./base";

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
