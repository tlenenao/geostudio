import { test, expect, type Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";

// REV-164 (b) / runbook 2026-07-24 §7 : reconnexion OIDC RÉELLE après restauration.
// Piloté par scripts/replay/restore-oidc.sh (jamais lancé seul par `npm run e2e:oidc` : sans
// RESTORE_PHASE, les deux tests sont ignorés).
// RESTORE_PHASE=before : alice crée une carte. RESTORE_PHASE=after : même compte, après sinistre.
const ALICE = { username: "alice", password: "Demo1234!" };
const PHASE = process.env.RESTORE_PHASE;
const ID_FILE = process.env.RESTORE_ID_FILE ?? "../.replay-results/restore-item-id";

test.setTimeout(120_000);

// Même contournement CORS que copilot-oidc.spec.ts : pas de Traefik sur localhost, le cœur
// n'expose aucun CORS global.
async function allowCrossOriginCore(page: Page) {
  const cors = {
    "access-control-allow-origin": "http://localhost:8300",
    "access-control-allow-headers": "authorization, content-type, if-match",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "access-control-expose-headers": "etag, location",
  };
  await page.route(/:8200\/v1\//, async (route) => {
    if (route.request().method() === "OPTIONS")
      return route.fulfill({ status: 204, headers: cors });
    try {
      const res = await route.fetch();
      await route.fulfill({ response: res, headers: { ...res.headers(), ...cors } });
    } catch {
      // page fermée en cours de requête : rien à relayer
    }
  });
}

// Un échec ici après restauration = « signal le plus grave » du runbook §7 : le message
// Keycloak réel est consigné par Playwright, ne jamais conclure « probablement OK ».
async function login(page: Page): Promise<{ authorization: string; coreUrl: string }> {
  await allowCrossOriginCore(page);
  const bearer = page.waitForRequest(
    (r) => /\/v1\//.test(r.url()) && Boolean(r.headers().authorization),
    { timeout: 60_000 },
  );
  // Preuve de reconnexion : le cœur accepte le jeton (200 sur /v1/me) ; et le premier login d'un
  // compte neuf ne se dispute plus avec nos propres appels REST.
  const me = page.waitForResponse((r) => /\/v1\/me$/.test(r.url()) && r.ok(), {
    timeout: 60_000,
  });
  await page.goto("/");
  await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
  await page.fill('input[name="username"]', ALICE.username);
  await page.fill('input[name="password"]', ALICE.password);
  await page.click('input[type="submit"], button[type="submit"]');
  const req = await bearer;
  await me;
  return { authorization: req.headers().authorization, coreUrl: new URL(req.url()).origin };
}

test("phase before : alice crée une carte", async ({ page }) => {
  test.skip(PHASE !== "before");
  const { authorization, coreUrl } = await login(page);
  const r = await page.request.post(`${coreUrl}/v1/configs`, {
    headers: { authorization },
    data: {
      title: `restore-164-${Date.now()}`,
      config: {
        version: 1,
        kind: "map",
        map: {
          basemap: { style: "https://demotiles.maplibre.org/style.json" },
          view: { center: [2.55, 46.275], zoom: 8 },
          layers: [],
        },
      },
    },
  });
  expect(r.status()).toBe(201);
  writeFileSync(ID_FILE, (await r.json()).itemId);
});

test("phase after : même compte, reconnexion OIDC complète, carte visible", async ({ page }) => {
  test.skip(PHASE !== "after");
  const { authorization, coreUrl } = await login(page);
  const id = readFileSync(ID_FILE, "utf8").trim();
  const r = await page.request.get(`${coreUrl}/v1/items/${id}`, { headers: { authorization } });
  expect(r.status()).toBe(200);
});
