// @vitest-environment node
// SPDX-License-Identifier: Apache-2.0
// Le service worker est évalué tel qu'émis (modèle + injection), avec un faux `self`/`caches`.
import { readFileSync } from "node:fs";
import { expect, test, vi } from "vitest";
import { buildServiceWorker } from "../../vite.serviceWorker";

const ORIGIN = "https://app.test";
const CRITICAL = ["/index.html", "/assets/entry-abc.js"];
const OPTIONAL = ["/env-config.js"];
const template = readFileSync(new URL("../../sw/sw.template.js", import.meta.url), "utf-8");

const key = (k: string | Request) => {
  const u = new URL(typeof k === "string" ? k : k.url, ORIGIN);
  return u.pathname + u.search;
};

function setup(opts: { network?: (req: Request) => Promise<Response> } = {}) {
  const stores = new Map<string, Map<string, Response>>();
  const open = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const s = stores.get(name)!;
    return Promise.resolve({
      put: async (k: string | Request, r: Response) => void s.set(key(k), r),
      match: async (k: string | Request) => s.get(key(k))?.clone(),
      add: async (k: string) => {
        const r = await network(new Request(new URL(k, ORIGIN)));
        if (!r.ok) throw new Error("bad status");
        s.set(key(k), r);
      },
      addAll: async (ks: string[]) => {
        for (const k of ks) {
          const r = await network(new Request(new URL(k, ORIGIN)));
          if (!r.ok) throw new Error("bad status");
          s.set(key(k), r);
        }
      },
    });
  };
  const network = vi.fn(opts.network ?? (async () => new Response("net", { status: 200 })));
  const handlers: Record<string, (e: never) => void> = {};
  const self = {
    location: { origin: ORIGIN },
    caches: {
      open,
      keys: async () => [...stores.keys()],
      delete: async (n: string) => stores.delete(n),
      match: async (k: string | Request) => {
        for (const s of stores.values()) {
          const hit = s.get(key(k));
          if (hit) return hit.clone();
        }
        return undefined;
      },
    },
    clients: { claim: vi.fn(async () => undefined) },
    skipWaiting: vi.fn(),
    addEventListener: (n: string, h: (e: never) => void) => void (handlers[n] = h),
  };
  const code = buildServiceWorker(template, CRITICAL, OPTIONAL, "seed");
  new Function("self", "fetch", "Response", "AbortSignal", code)(
    self,
    network,
    Response,
    AbortSignal,
  );
  const wait = async (name: string, event: Record<string, unknown> = {}) => {
    let p: Promise<unknown> = Promise.resolve();
    handlers[name]({ ...event, waitUntil: (x: Promise<unknown>) => (p = x) } as never);
    await p;
  };
  /** Rejoue un `fetch` : `undefined` = laissé au réseau (aucun respondWith). */
  const doFetch = async (
    url: string,
    init: RequestInit & { navigate?: boolean } = {},
  ): Promise<Response | undefined> => {
    const base = new Request(new URL(url, ORIGIN), init);
    const request = init.navigate ? { ...Object.assign({}, base), mode: "navigate" } : base;
    const fake = init.navigate
      ? ({
          method: base.method,
          url: base.url,
          mode: "navigate",
          headers: base.headers,
        } as unknown as Request)
      : request;
    let responded: Promise<Response> | undefined;
    handlers.fetch({
      request: fake,
      respondWith: (p: Promise<Response>) => (responded = p),
    } as never);
    return responded;
  };
  return { stores, self, network, wait, doFetch, handlers };
}

test("installation : précache les fichiers critiques ; un facultatif absent ne la bloque pas", async () => {
  const s = setup({
    network: async (r) =>
      new Response("x", { status: new URL(r.url).pathname === "/env-config.js" ? 404 : 200 }),
  });
  await s.wait("install");
  const [cache] = [...s.stores.entries()].filter(([n]) => n.startsWith("gs-shell-"));
  expect([...cache[1].keys()].sort()).toEqual([...CRITICAL].sort());
  expect(s.self.skipWaiting).not.toHaveBeenCalled(); // jamais d'activation automatique
});

test("seul le shell est intercepté : API, MCP, embed, admin, Authorization, autres origines, non-GET passent au réseau", async () => {
  const s = setup();
  await s.wait("install");
  const passthrough = [
    ["/api/v1/items"],
    ["/v1/collections/c/items"],
    ["/mcp"],
    ["/embed/tok", { navigate: true }],
    ["/admin/grafana", { navigate: true }],
    ["/sitemap.xml", { navigate: true }],
    ["https://cdn.example/assets/x.js"],
    ["/assets/x.js", { headers: { Authorization: "Bearer t" } }],
    ["/assets/x.js", { method: "POST" }],
    ["/api/assets/x.js"],
  ] as const;
  for (const [url, init] of passthrough)
    expect(await s.doFetch(url, init as RequestInit), url).toBeUndefined();
});

test("navigation /collect/… et /apps/… : réseau d'abord, repli sur le shell en cache hors-ligne ou sur 502-504", async () => {
  let mode: "up" | "down" | "bad" = "up";
  const s = setup({
    network: async (r) => {
      if (new URL(r.url).pathname !== "/index.html" && mode === "down")
        throw new TypeError("offline");
      if (new URL(r.url).pathname !== "/index.html" && mode === "bad")
        return new Response("", { status: 503 });
      return new Response(`page:${new URL(r.url).pathname}`, { status: 200 });
    },
  });
  await s.wait("install");
  expect(await (await s.doFetch("/collect/tok", { navigate: true }))!.text()).toBe(
    "page:/collect/tok",
  );
  mode = "down";
  expect(await (await s.doFetch("/collect/tok", { navigate: true }))!.text()).toBe(
    "page:/index.html",
  );
  expect(await (await s.doFetch("/apps/12", { navigate: true }))!.text()).toBe("page:/index.html");
  mode = "bad";
  expect(await (await s.doFetch("/", { navigate: true }))!.text()).toBe("page:/index.html");
});

test("/assets/ : cache d'abord (un chunk déjà vu ne repart pas au réseau)", async () => {
  const s = setup();
  await s.wait("install");
  await (await s.doFetch("/assets/lazy-1.js"))!.text();
  const calls = s.network.mock.calls.length;
  await (await s.doFetch("/assets/lazy-1.js"))!.text();
  expect(s.network.mock.calls.length).toBe(calls);
});

test("activation : purge les caches d'anciens builds, garde les siens, prend le contrôle", async () => {
  const s = setup();
  s.stores.set("gs-shell-old", new Map());
  s.stores.set("gs-assets-old", new Map());
  s.stores.set("autre-appli", new Map());
  await s.wait("install");
  await s.wait("activate");
  const names = [...s.stores.keys()];
  expect(names).not.toContain("gs-shell-old");
  expect(names).not.toContain("gs-assets-old");
  expect(names).toContain("autre-appli");
  expect(s.self.clients.claim).toHaveBeenCalled();
});

test("SKIP_WAITING demandé par la page : seul message qui active la nouvelle version", async () => {
  const s = setup();
  s.handlers.message({ data: { type: "autre" } } as never);
  expect(s.self.skipWaiting).not.toHaveBeenCalled();
  s.handlers.message({ data: { type: "SKIP_WAITING" } } as never);
  expect(s.self.skipWaiting).toHaveBeenCalledTimes(1);
});

test("l'identifiant de build suit le contenu : deux listes différentes, deux caches", () => {
  const a = buildServiceWorker(template, ["/index.html", "/assets/a.js"], OPTIONAL, "s");
  const b = buildServiceWorker(template, ["/index.html", "/assets/b.js"], OPTIONAL, "s");
  const id = (c: string) => /gs-shell-|BUILD_ID = "([0-9a-f]{12})"/.exec(c)?.[1];
  expect(id(a)).toMatch(/^[0-9a-f]{12}$/);
  expect(id(a)).not.toBe(id(b));
  expect(a).not.toContain("__");
});
