/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect, request, type APIRequestContext } from "@playwright/test";
import { apiFor, type Api } from "./helpers";

// Passerelle /admin/grafana EN FONCTIONNEMENT (Grafana du profil observability, derrière Traefik
// https://localhost avec le cookie gs_admin_session). Complète j08b (simple 200 sur la racine).
test.setTimeout(120_000);

let admin: Api;

test.beforeAll(async () => {
  admin = await apiFor("admin");
});

async function launch(): Promise<{ url: string; cookie: string }> {
  const l = await admin.send("POST", "/v1/admin-tools/launch/grafana");
  expect(l.status).toBe(200);
  const r = await fetch(l.body.url, { redirect: "manual" });
  const cookie = /gs_admin_session=([^;]+)/.exec(r.headers.get("set-cookie") ?? "")?.[1] ?? "";
  return { url: l.body.url, cookie };
}

async function gw(cookie?: string): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: "https://localhost",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: cookie ? { cookie: `gs_admin_session=${cookie}` } : {},
  });
}

test("Grafana derrière la passerelle : santé, dashboards GeoStudio provisionnés, sources Prometheus/Loki, 403 sans cookie", async () => {
  const { cookie } = await launch();
  const anon = await gw();
  expect((await anon.get("/admin/grafana/api/health")).status()).toBe(403);
  const ctx = await gw(cookie);
  const h = await ctx.get("/admin/grafana/api/health");
  expect(h.status()).toBe(200);
  expect((await h.json()).database).toBe("ok");
  const s = await ctx.get("/admin/grafana/api/search?type=dash-db");
  const titles = ((await s.json()) as any[]).map((d) => d.title);
  for (const t of ["Cœur", "Jobs", "Martin (tuiles)", "Postgres"]) {
    expect(titles.some((x) => x.includes(t))).toBe(true);
  }
  for (const uid of ["prometheus", "loki"]) {
    const r = await ctx.get(`/admin/grafana/api/datasources/uid/${uid}/health`);
    expect(r.status(), uid).toBe(200);
  }
  const jobs = await (
    await ctx.get("/admin/grafana/api/datasources/proxy/uid/prometheus/api/v1/label/job/values")
  ).json();
  expect(jobs.data).toEqual(expect.arrayContaining(["martin", "postgres"]));
  await ctx.dispose();
  await anon.dispose();
});

// Finding j09b-007 : Grafana du profil observability tourne en accès anonyme avec le rôle Admin
// d'organisation ; la passerelle ne filtre que « avoir le privilège settings.instance.manage ».
// Tout porteur de ce privilège peut donc créer une source de données Grafana vers n'importe quel
// service interne (proxy Grafana) : ici MinIO, sans aucun identifiant.
test("j09b-007 : un porteur de la passerelle n'est pas administrateur Grafana (pas de création de source vers un service interne)", async () => {
  const { cookie } = await launch();
  const ctx = await gw(cookie);
  const name = `aud-j09b-ssrf-${Date.now().toString(36)}`;
  const created = await ctx.post("/admin/grafana/api/datasources", {
    data: { name, type: "prometheus", access: "proxy", url: "http://minio:9000" },
  });
  try {
    expect(created.status()).toBe(403);
  } finally {
    await ctx.delete(`/admin/grafana/api/datasources/name/${name}`);
    await ctx.dispose();
  }
});

test("Grafana dans un navigateur : le dashboard GeoStudio Cœur s'affiche sous le sous-chemin /admin/grafana", async ({
  browser,
}) => {
  const { cookie } = await launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addCookies([
    {
      name: "gs_admin_session",
      value: cookie,
      domain: "localhost",
      path: "/admin",
      secure: true,
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);
  const page = await context.newPage();
  const statuses: number[] = [];
  page.on("response", (r) => {
    if (r.url().startsWith("https://localhost/admin/grafana")) statuses.push(r.status());
  });
  await page.goto("https://localhost/admin/grafana/d/geostudio-core/geostudio-e28094-coeur");
  await expect(page.getByText("GeoStudio — Cœur").first()).toBeVisible({ timeout: 30_000 });
  expect(statuses.filter((s) => s === 429 || s >= 500)).toEqual([]);
  await context.close();
});

// Finding j09b-008 : le middleware csp-dynamic (script-src 'self') s'applique aussi à Grafana, dont
// la page embarque des <script nonce=""> en ligne : en mode enforce (défaut de production) ils
// sont bloqués. En report-only (stack d'audit) le navigateur journalise les violations.
test("j09b-008 : Grafana se charge sans violation de la CSP posée par la passerelle", async ({
  browser,
}) => {
  const { cookie } = await launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await context.addCookies([
    {
      name: "gs_admin_session",
      value: cookie,
      domain: "localhost",
      path: "/admin",
      secure: true,
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);
  const page = await context.newPage();
  const violations: string[] = [];
  page.on("console", (m) => {
    if (/content security policy/i.test(m.text())) violations.push(m.text().slice(0, 160));
  });
  await page.goto("https://localhost/admin/grafana/d/geostudio-core/geostudio-e28094-coeur");
  await page.waitForTimeout(5_000);
  await context.close();
  expect(violations).toEqual([]);
});

test("jeton de lancement : refusé (401) une fois ses 60 s écoulées, alors qu'il est accepté juste après sa création", async () => {
  test.setTimeout(150_000);
  const fresh = await admin.send("POST", "/v1/admin-tools/launch/grafana");
  const stale = await admin.send("POST", "/v1/admin-tools/launch/grafana");
  expect((await fetch(fresh.body.url, { redirect: "manual" })).status).toBe(302);
  await new Promise((r) => setTimeout(r, 65_000));
  expect((await fetch(stale.body.url, { redirect: "manual" })).status).toBe(401);
});
