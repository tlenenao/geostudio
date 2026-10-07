/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { expect, test } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, token } from "../j03/api";
import { psql } from "../j02/helpers";
import { bug, docker } from "./helpers";

const APP_CFG = {
  version: 1,
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
};

async function raw(
  method: string,
  path: string,
  init: { auth?: string; body?: string; headers?: Record<string, string> } = {},
): Promise<{ status: number; ct: string; retryAfter: string | null; body: any }> {
  const r = await fetch(`${CORE_URL}${path}`, {
    method,
    headers: {
      ...(init.auth ? { authorization: init.auth } : {}),
      ...(init.body !== undefined ? { "content-type": "application/json" } : {}),
      ...init.headers,
    },
    body: init.body,
  });
  const text = await r.text();
  let body: any = text;
  try {
    body = JSON.parse(text);
  } catch {
    /* corps non JSON */
  }
  return {
    status: r.status,
    ct: r.headers.get("content-type") ?? "",
    retryAfter: r.headers.get("retry-after"),
    body,
  };
}

const FAMILIES = [
  "/v1/items",
  "/v1/collections/candidates",
  "/v1/secrets",
  "/v1/users",
  "/v1/notifications",
  "/v1/groups",
  "/v1/roles",
];

test.describe("t02 API : 401 / 403 / 404 sur chaque famille", () => {
  test("401 : absence de jeton, jeton corrompu et schéma non Bearer répondent en problem+json", async () => {
    for (const path of FAMILIES) {
      for (const auth of [undefined, "Bearer junk", "Basic dXNlcjpwYXNz", "Bearer "]) {
        const r = await raw("GET", path, { auth });
        expect(r.status, `${path} ${auth}`).toBe(401);
        expect(r.ct, `${path} ${auth}`).toContain("application/problem+json");
        expect(r.body.status).toBe(401);
      }
    }
  });

  test("401 : un jeton signé mais tronqué ou altéré est refusé sans 500", async () => {
    const tok = await token("creator");
    const [h, p, s] = tok.split(".");
    for (const bad of [
      `${h}.${p}.`,
      `${h}.${p}.${s.slice(0, -4)}AAAA`,
      `${h}.${p.slice(0, -3)}xyz.${s}`,
    ]) {
      const r = await raw("GET", "/v1/items", { auth: `Bearer ${bad}` });
      expect(r.status).toBe(401);
    }
  });

  test("404 : identifiants inconnus répondent en problem+json sur les familles à identifiant", async () => {
    const creator = await apiFor("creator");
    for (const path of [
      "/v1/items/nope",
      "/v1/configs/by-item/nope",
      "/v1/configs/nope",
      "/v1/configs/nope/revisions",
      "/v1/collections/nope",
      "/v1/uploads/nope",
    ]) {
      const tok = await token("creator");
      const r = await raw("GET", path, { auth: `Bearer ${tok}` });
      expect([404, 403], path).toContain(r.status);
      expect(r.ct, path).toContain("application/problem+json");
    }
    expect((await creator.get("/v1/items/nope")).status).toBe(404);
  });

  test("403 : le Lecteur reçoit un problem+json sur les écritures de chaque famille", async () => {
    const tok = await token("reader");
    const auth = `Bearer ${tok}`;
    const cases: [string, string, unknown][] = [
      ["POST", "/v1/secrets", { name: "x", value: "y" }],
      ["POST", "/v1/roles", { name: "x", privileges: [] }],
      ["POST", "/v1/harvest/sources", {}],
      ["GET", "/v1/users", undefined],
      ["GET", "/v1/collections/candidates", undefined],
    ];
    for (const [m, p, b] of cases) {
      const r = await raw(m, p, { auth, body: b === undefined ? undefined : JSON.stringify(b) });
      expect([401, 403, 404, 422], `${m} ${p}`).toContain(r.status);
      if (r.status === 403) expect(r.ct, `${m} ${p}`).toContain("application/problem+json");
      expect(r.status, `${m} ${p}`).not.toBeGreaterThanOrEqual(500);
    }
  });

  test("aucune route GET ne répond 5xx sur des identifiants inexistants (balayage OpenAPI)", async () => {
    const spec = (await (await fetch(`${CORE_URL}/openapi.json`)).json()) as any;
    const tok = await token("admin");
    const bad: string[] = [];
    let n = 0;
    for (const [path, ops] of Object.entries<any>(spec.paths)) {
      if (!ops.get || /compliance|logout|\/mcp/.test(path)) continue;
      for (const val of ["nope", "0".repeat(32)]) {
        const url = path.replace(/\{[^}]+\}/g, val);
        const r = await raw("GET", url, { auth: `Bearer ${tok}` });
        n++;
        if (r.status >= 500) bad.push(`${url} -> ${r.status}`);
      }
    }
    expect(n).toBeGreaterThan(100);
    expect(bad).toEqual([]);
  });

  test("le corps 422 d'une validation contient la localisation du champ fautif", async () => {
    const tok = await token("creator");
    const r = await raw("POST", "/v1/configs", {
      auth: `Bearer ${tok}`,
      body: JSON.stringify({ title: "x", config: { kind: "zzz" } }),
    });
    expect(r.status).toBe(422);
    expect(JSON.stringify(r.body.detail)).toContain("kind");
  });
});

test.describe("t02 API : 409, 429 et charges limites", () => {
  test("409 : un slug de site déjà utilisé est refusé en problem+json", async () => {
    const creator = await apiFor("creator");
    const slug = stamp("t02");
    const cfg = { ...APP_CFG, kind: "site" };
    const first = await creator.send("POST", "/v1/configs", { title: slug, slug, config: cfg });
    expect(first.status).toBe(201);
    const tok = await token("creator");
    const dup = await raw("POST", "/v1/configs", {
      auth: `Bearer ${tok}`,
      body: JSON.stringify({ title: slug, slug, config: cfg }),
    });
    expect(dup.status).toBe(409);
    expect(dup.ct).toContain("application/problem+json");
    expect(dup.body.detail).toContain(slug);
  });

  test("429 : au-delà du budget @audit-flaky, la réponse porte Retry-After et un problem+json", async () => {
    // Budget « collections_empty » = 5 / 60 s par jeton ; le limiteur passe AVANT l'authentification.
    const tok = await token("reader");
    const seen: number[] = [];
    let last: Awaited<ReturnType<typeof raw>> | undefined;
    for (let i = 0; i < 7; i++) {
      last = await raw("POST", "/v1/collections/empty", {
        auth: `Bearer ${tok}`,
        body: "{}",
      });
      seen.push(last.status);
    }
    expect(seen.slice(0, 5).every((s) => s !== 429)).toBe(true);
    expect(seen.slice(5)).toEqual([429, 429]);
    expect(last!.retryAfter).toBe("60");
    expect(last!.ct).toContain("application/problem+json");
  });

  test("le budget d'un jeton n'est pas consommé par un autre appelant", async () => {
    const tok = await token("analyst");
    const r = await raw("POST", "/v1/collections/empty", { auth: `Bearer ${tok}`, body: "{}" });
    expect(r.status).not.toBe(429);
  });

  // Finding t02-001 : aucune borne de taille de corps côté cœur (40 Mo de JSON acceptés et stockés).
  test("t02-001 : un corps de 40 Mo sur POST /configs est refusé (413/422)", async () => {
    const creator = await apiFor("creator");
    const cfg = { ...APP_CFG, theme: { k: "x".repeat(40 * 1024 * 1024) } };
    const r = await creator.send("POST", "/v1/configs", {
      title: `${stamp("t02")}-big`,
      config: cfg,
    });
    if (r.status === 201) await creator.send("DELETE", `/v1/items/${r.body.itemId}`);
    expect([413, 422]).toContain(r.status);
  });
});

test.describe("t02 API : écritures concurrentes", () => {
  async function newApp(creator: Awaited<ReturnType<typeof apiFor>>, tag: string) {
    const r = await creator.send("POST", "/v1/configs", {
      title: `${stamp("t02")}-${tag}`,
      config: APP_CFG,
    });
    expect(r.status).toBe(201);
    return { itemId: r.body.itemId as string, configId: r.body.id as string };
  }

  // Finding t02-002 : dix PUT simultanés produisent dix révisions portant le même numéro de version.
  test("t02-002 : des PUT concurrents ne créent jamais deux révisions de même version", async () => {
    const creator = await apiFor("creator");
    const { itemId, configId } = await newApp(creator, "conc");
    const rs = await Promise.all(
      Array.from({ length: 10 }, (_, i) =>
        creator.send("PUT", `/v1/configs/by-item/${itemId}`, {
          ...APP_CFG,
          theme: { primary: `#00000${i}` },
        }),
      ),
    );
    const okCount = rs.filter((r) => r.status === 200).length;
    const revs = await creator.get(`/v1/configs/${configId}/revisions`);
    const versions: number[] = revs.body.map((r: any) => r.version);
    const dupes = versions.length - new Set(versions).size;
    // Soit le cœur sérialise (pas de doublon), soit il refuse les perdants (409) : jamais de doublon silencieux.
    expect(dupes, `versions: ${versions.join(",")} (200: ${okCount})`).toBe(0);
  });

  // Finding t02-003 : PUT ne porte aucune version de base ; la dernière écriture écrase silencieusement.
  bug("t02-003 : une écriture fondée sur une version périmée est refusée (409/412)", async () => {
    const creator = await apiFor("creator");
    const { itemId } = await newApp(creator, "lost");
    const base = await creator.get(`/v1/configs/by-item/${itemId}`);
    const baseVersion = base.body.version;
    const a = await creator.send("PUT", `/v1/configs/by-item/${itemId}`, {
      ...APP_CFG,
      theme: { primary: "#aaaaaa" },
    });
    expect(a.status).toBe(200);
    // Le second client a chargé la version `baseVersion` : son écriture est périmée.
    const b = await creator.send("PUT", `/v1/configs/by-item/${itemId}`, {
      ...APP_CFG,
      theme: { primary: "#bbbbbb" },
    });
    expect(baseVersion).toBeLessThan(a.body.version);
    expect([409, 412, 428]).toContain(b.status);
  });

  // Finding t02-004 : l'écriture d'un item/collection défère un calcul d'embedding dont l'échec est avalé.
  test("t02-004 : la création d'un item met réellement en file le calcul d'embedding", async () => {
    const before = Number(
      psql(
        "SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE '%embed_item_task'",
      ).trim(),
    );
    const creator = await apiFor("creator");
    const { itemId } = await newApp(creator, "embed");
    await new Promise((r) => setTimeout(r, 1500));
    const after = Number(
      psql(
        "SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE '%embed_item_task'",
      ).trim(),
    );
    const logs = docker("logs", "--since", "20s", "geostudio-core-1");
    expect(logs).not.toContain(`échec de l'enqueue du job d'embedding pour l'item ${itemId}`);
    expect(after).toBeGreaterThan(before);
  });
});

test.describe("t02 API : surface d'enregistrement de collections", () => {
  // Finding t02-005 : les tables Keycloak et procrastinate du même schéma sont proposées à l'enregistrement.
  test("t02-005 : GET /collections/candidates n'expose aucune table étrangère au produit", async () => {
    const admin = await apiFor("admin");
    const r = await admin.get("/v1/collections/candidates");
    expect(r.status).toBe(200);
    const foreign = (r.body.candidates as any[])
      .filter((c) => c.registrable)
      .map((c) => c.tableName as string)
      .filter((n) => /^(user_entity|credential|realm|client|procrastinate_)/.test(n));
    expect(foreign).toEqual([]);
  });
});
