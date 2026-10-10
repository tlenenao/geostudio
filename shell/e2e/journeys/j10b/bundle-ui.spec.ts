import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import type { Server } from "node:http";
import { join } from "node:path";
import { stamp } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import {
  apiFor,
  appConfig,
  createApp,
  makeCollection,
  runExport,
  serveDir,
  tableApp,
  type Api,
} from "./helpers";

test.setTimeout(240_000);
const tag = stamp("j10b");
let creator: Api;
let srv: Server | undefined;

test.beforeAll(async () => {
  creator = await apiFor("creator");
});
test.afterEach(() => {
  srv?.close();
  srv = undefined;
});

// Conteneur jetable de l'image autoportée ; code du mini-serveur courant monté
// sur l'image locale (périmée, cf. j10b-009) et runtime shell courant en /runtime.
async function withStandalone(
  dir: string,
  port: number,
  fn: (base: string) => Promise<void>,
): Promise<void> {
  const name = `j10b-standalone-${port}`;
  const rm = () => execFileSync("docker", ["rm", "-f", name], { stdio: "ignore" });
  try {
    rm();
    execFileSync("docker", [
      "run",
      "-d",
      "--rm",
      "--name",
      name,
      "-p",
      `127.0.0.1:${port}:8000`,
      "-v",
      `${dir}/data:/data:ro`,
      "-v",
      `${join(process.cwd(), "../core/app")}:/app/app:ro`,
      "-v",
      "geostudio_appexport-runtime:/runtime:ro",
      "geostudio-appexport-standalone:local",
    ]);
    const base = `http://127.0.0.1:${port}`;
    await expect
      .poll(
        () =>
          fetch(`${base}/geostudio-connection.json`)
            .then((r) => r.status)
            .catch(() => 0),
        { timeout: 30_000 },
      )
      .toBe(200);
    await fn(base);
  } finally {
    rm();
  }
}

const BUNDLE = "http://127.0.0.1:9312";

test.describe("j10b bundles exportés ouverts dans un navigateur", () => {
  test("static : le tableau se rend depuis la config gelée, sans aucun appel au cœur", async ({
    page,
  }) => {
    const col = await makeCollection(creator, `${tag}-ui1`, { pub: true, rows: 3 });
    const id = await createApp(creator, `${tag}-ui-st`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "static");
    srv = await serveDir(run.dir!, 9312);
    const coreCalls: string[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith("http://localhost:8200")) coreCalls.push(r.url());
    });
    await page.goto(BUNDLE);
    await expect(page.getByRole("cell", { name: "pub-1" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "pub-3" })).toBeVisible();
    expect(coreCalls).toEqual([]);
  });

  test("connected : données lues en direct sur le cœur, anonymes et en GET uniquement", async ({
    page,
  }) => {
    const col = await makeCollection(creator, `${tag}-ui2`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-ui-co`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "connected");
    srv = await serveDir(run.dir!, 9312);
    const calls: { method: string; url: string; auth: string | undefined }[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith("http://localhost:8200"))
        calls.push({ method: r.method(), url: r.url(), auth: r.headers()["authorization"] });
    });
    await page.goto(BUNDLE);
    await expect(page.getByRole("cell", { name: "pub-2" })).toBeVisible();
    expect(calls.length).toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.method).toBe("GET");
      expect(c.auth).toBeUndefined();
    }
    expect(calls.map((c) => new URL(c.url).pathname).sort()).toEqual(
      expect.arrayContaining([`/v1/collections/${col.id}/items`, "/v1/extensions"]),
    );
  });

  test("standalone : le conteneur démarre, sert config et connexion, agrège, refuse l'écriture", async () => {
    const col = await makeCollection(creator, `${tag}-ui4`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-ui-sa`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "standalone");
    await withStandalone(run.dir!, 8391, async (base) => {
      const conn = await (await fetch(`${base}/geostudio-connection.json`)).json();
      expect(conn.coreUrl).toBe(base);
      const cfg = await (await fetch(`${base}/geostudio-app-config.json`)).json();
      expect(cfg.dataSources[0].layer).toBe(col.id);
      const agg = await fetch(`${base}/v1/collections/${col.id}/aggregate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ aggregates: [{ fn: "count", as: "n" }] }),
      });
      expect((await agg.json()).rows[0].value).toBe(2);
      const w = await fetch(`${base}/v1/collections/${col.id}/items`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}",
      });
      expect([404, 405]).toContain(w.status);
    });
  });

  // Anciens FINDINGS, corrigés (d2669e87, b5e9bddf) : j10b-010 (routes sans /v1 : le client du shell appelle /v1/...) et
  // j10b-011 (le mini-serveur interroge la colonne « geom », le parquet écrit
  // « geometry » : GET .../items = 500). Runtime courant = volume appexport-runtime.
  test("j10b-010 : l'app autoportée affiche ses données dans le navigateur", async ({ page }) => {
    const col = await makeCollection(creator, `${tag}-ui6`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-ui-sa2`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "standalone");
    await withStandalone(run.dir!, 8392, async (base) => {
      await page.goto(`${base}/index.export.html`);
      await expect(page.getByRole("cell", { name: "pub-1" })).toBeVisible({ timeout: 20_000 });
    });
  });

  test("j10b-011 : GET /v1/collections/{id}/items du mini-serveur répond 200", async () => {
    const col = await makeCollection(creator, `${tag}-ui7`, { pub: true, rows: 2 });
    const id = await createApp(creator, `${tag}-ui-sa3`, tableApp(col.id, ["nom"]));
    const run = await runExport(creator, id, "standalone");
    await withStandalone(run.dir!, 8394, async (base) => {
      expect((await fetch(`${base}/v1/collections/${col.id}/items`)).status).toBe(200);
    });
  });
});

test.describe("j10b CORS étroit du mode Connecté", () => {
  const ORIGIN = "https://tiers.example";
  const h = { Origin: ORIGIN };

  test("lectures anonymes listées : ACAO * ; écritures et routes privées : aucun en-tête CORS", async () => {
    const col = await makeCollection(creator, `${tag}-cors1`, { pub: true });
    for (const p of [
      "/v1/collections",
      `/v1/collections/${col.id}`,
      `/v1/collections/${col.id}/schema`,
      `/v1/collections/${col.id}/items`,
      "/v1/extensions",
      "/v1/public/items",
    ]) {
      const r = await fetch(`http://localhost:8200${p}`, { headers: h });
      expect(r.headers.get("access-control-allow-origin"), p).toBe("*");
    }
    const agg = await fetch(`http://localhost:8200/v1/collections/${col.id}/aggregate`, {
      method: "POST",
      headers: { ...h, "content-type": "application/json" },
      body: JSON.stringify({ aggregates: [{ fn: "count", as: "n" }] }),
    });
    expect(agg.headers.get("access-control-allow-origin")).toBe("*");
    for (const [m, p] of [
      ["POST", "/v1/collections"],
      ["GET", "/v1/collections/candidates"],
      ["DELETE", `/v1/collections/${col.id}`],
      ["POST", `/v1/collections/${col.id}/items`],
      ["GET", "/v1/items"],
      ["GET", "/v1/me"],
      ["GET", "/v1/instance"],
      ["GET", "/v1/public/sites/x"],
    ] as const) {
      const r = await fetch(`http://localhost:8200${p}`, { method: m, headers: h });
      expect(r.headers.get("access-control-allow-origin"), `${m} ${p}`).toBeNull();
    }
  });

  test("préflight : 204 sur les chemins listés, rien sur les chemins privés", async () => {
    const ok = await fetch("http://localhost:8200/v1/collections", {
      method: "OPTIONS",
      headers: { ...h, "Access-Control-Request-Method": "GET" },
    });
    expect(ok.status).toBe(204);
    expect(ok.headers.get("access-control-allow-origin")).toBe("*");
    for (const p of ["/v1/items", "/v1/me", "/v1/app-exports", "/v1/configs"]) {
      const r = await fetch(`http://localhost:8200${p}`, {
        method: "OPTIONS",
        headers: { ...h, "Access-Control-Request-Method": "POST" },
      });
      expect(r.headers.get("access-control-allow-origin"), p).toBeNull();
    }
  });
});

test.describe("j10b téléchargement et builder", () => {
  // FINDING j10b-008 : resultUrl est présigné sur l'hôte interne du stockage.
  test("j10b-008 : l'URL de téléchargement du bundle est joignable depuis un navigateur", async () => {
    const id = await createApp(creator, `${tag}-dl`, appConfig());
    const run = await runExport(creator, id, "static");
    const job = await creator.get(`/v1/app-exports/jobs/${run.jobId}`);
    expect(job.body.status).toBe("done");
    const r = await fetch(job.body.resultUrl);
    expect(r.status).toBe(200);
  });

  test("builder : un widget formulaire déclenche l'avertissement d'écriture avant l'export", async ({
    page,
  }) => {
    const id = await createApp(
      creator,
      `${tag}-form`,
      appConfig([{ id: "f", widget: "form", x: 0, y: 0, w: 6, h: 4, props: {} }]),
    );
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${id}/edit`);
    await page.getByRole("button", { name: "Exporter", exact: true }).click();
    await page.getByRole("button", { name: "Connecté" }).click();
    await expect(page.getByRole("alert").filter({ hasText: /écriture|formulaire/i })).toBeVisible();
    await page.getByRole("button", { name: "Ne pas exporter" }).click();
    await expect(page.getByRole("button", { name: "Exporter quand même" })).toHaveCount(0);
  });
});
