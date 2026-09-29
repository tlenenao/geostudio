import { test, expect, type Page } from "@playwright/test";
import { CORE_URL, SHELL_URL } from "../_fixtures/env";

// Visiteur anonyme : aucune connexion, aucun persona. En auth OIDC réelle,
// une page ouverte sans login est réellement anonyme.

const KEYCLOAK_AUTH = /\/realms\/geostudio\/protocol\/openid-connect\/auth/;

async function trackRequests(page: Page) {
  const seen: { url: string; status: number; auth: boolean }[] = [];
  page.on("response", (r) => {
    const req = r.request();
    if (r.url().startsWith(CORE_URL)) {
      seen.push({ url: r.url(), status: r.status(), auth: !!req.headers()["authorization"] });
    }
  });
  return seen;
}

test.describe("j01 visiteur anonyme — shell", () => {
  test("catalogue : / redirige vers Keycloak (pas de catalogue public)", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL(KEYCLOAK_AUTH);
    expect(page.url()).toContain("openid-connect/auth");
  });

  // j01-001 : /v1/public/items existe mais aucune page shell ne l'expose.
  test.fixme("j01-001 : un visiteur anonyme peut parcourir un catalogue public sans login", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForTimeout(3000);
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
  });

  for (const path of ["/items/abc", "/maps/abc", "/admin/users", "/settings", "/tasks"]) {
    test(`route protégée ${path} : redirection vers Keycloak`, async ({ page }) => {
      await page.goto(path);
      await page.waitForURL(KEYCLOAK_AUTH);
    });
  }

  test("site inconnu : message 'Page introuvable' accessible, sans redirection login", async ({
    page,
  }) => {
    const seen = await trackRequests(page);
    await page.goto("/sites/aud-j01-inexistant");
    await expect(page.getByRole("alert")).toHaveText(/Page introuvable/);
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
    const site = seen.find((s) => s.url.includes("/v1/public/sites/"));
    expect(site?.status).toBe(404);
    expect(seen.filter((s) => s.auth)).toEqual([]);
  });

  // j01-002 : soft-404 — la page introuvable garde un titre générique et n'a pas de noindex.
  test.fixme("j01-002 : la page site introuvable est marquée noindex", async ({ page }) => {
    await page.goto("/sites/aud-j01-inexistant");
    await expect(page.getByRole("alert")).toBeVisible();
    const robots = (await page.locator('meta[name="robots"]').count()) ? "x" : "";
    expect(robots).not.toBe("");
  });

  test("site : slug avec caractères spéciaux ne casse pas la page", async ({ page }) => {
    await page.goto("/sites/%3Cscript%3Ealert(1)%3C%2Fscript%3E");
    await expect(page.getByRole("alert")).toHaveText(/Page introuvable/);
  });

  test("item public inconnu : Page introuvable", async ({ page }) => {
    await page.goto("/public/items/00000000-0000-0000-0000-000000000000");
    await expect(page.getByRole("alert")).toHaveText(/Page introuvable/);
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
  });

  test("dataset public inconnu : message introuvable", async ({ page }) => {
    await page.goto("/public/datasets/aud-j01-nope");
    await expect(page.getByRole("alert")).toBeVisible();
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
  });

  // j01-003 : la page dataset publique n'a ni titre de document ni méta description.
  test.fixme("j01-003 : la page dataset publique définit un titre et une description SEO", async ({
    page,
  }) => {
    await page.goto("/public/datasets/incidents");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Incidents");
    await expect(page).toHaveTitle(/Incidents/);
  });

  // j01-004 : lecture des lignes d'une collection publique par un anonyme.
  test("dataset public 'incidents' : en-tête rendu, sans redirection login", async ({ page }) => {
    await page.goto("/public/datasets/incidents");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Incidents");
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
  });

  test.fixme("j01-004 : les lignes d'une collection publique se lisent en anonyme (pas de 500)", async ({
    request,
  }) => {
    const r = await request.get(`${CORE_URL}/v1/collections/incidents/items`);
    expect(r.status()).toBe(200);
  });

  test("embed : jeton invalide → message expiré/révoqué", async ({ page }) => {
    await page.goto("/embed/jeton-bidon");
    await expect(page.getByRole("alert")).toBeVisible();
    expect(page.url()).not.toMatch(KEYCLOAK_AUTH);
  });

  test("embed : jeton JWT forgé → message d'erreur, aucun appel authentifié", async ({ page }) => {
    const seen = await trackRequests(page);
    await page.goto(
      "/embed/eyJhbGciOiJIUzI1NiJ9.eyJzaGFyZV9saW5rX2lkIjoieCJ9.c2lnbmF0dXJlLWJpZG9u",
    );
    await expect(page.getByRole("alert")).toBeVisible();
    expect(seen.filter((s) => s.auth)).toEqual([]);
    expect(seen.find((s) => s.url.includes("/v1/share-links/"))?.status).toBe(401);
  });

  test("embed : jeton vide (/embed/) ne plante pas le shell", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/embed/");
    await page.waitForTimeout(1500);
    expect(errors).toEqual([]);
  });

  test("app runtime /apps/:pk anonyme sur item non publié : pas d'accès", async ({ page }) => {
    await page.goto("/apps/00000000-0000-0000-0000-000000000000");
    await page.waitForTimeout(2500);
    const onKeycloak = KEYCLOAK_AUTH.test(page.url());
    const hasAlert = await page.getByRole("alert").count();
    expect(onKeycloak || hasAlert > 0).toBeTruthy();
  });

  test("mobile 360px : page introuvable sans défilement horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto("/sites/aud-j01-inexistant");
    await expect(page.getByRole("alert")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
  });
});

test.describe("j01 visiteur anonyme — API publique", () => {
  test("GET /v1/public/items : catalogue vide valide", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/public/items`);
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toMatchObject({ items: [], total: 0, page: 1, pageSize: 12 });
  });

  test("GET /v1/public/items : filtres type/tag inconnus → 200 vide", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/public/items?type=map&tag=zzz&page=3`);
    expect(r.status()).toBe(200);
    expect((await r.json()).items).toEqual([]);
  });

  // j01-005 : erreur de validation non RFC 7807.
  test.fixme("j01-005 : une erreur de validation renvoie un problème RFC 7807", async ({
    request,
  }) => {
    const r = await request.get(`${CORE_URL}/v1/public/items?pageSize=0`);
    expect(r.status()).toBe(422);
    expect(r.headers()["content-type"]).toContain("application/problem+json");
  });

  test("routes privées : 401 sans jeton (items, me, configs) ; config par item → 404 opaque", async ({
    request,
  }) => {
    for (const p of ["/v1/items", "/v1/items/facets", "/v1/me", "/v1/configs/abc"]) {
      const r = await request.get(`${CORE_URL}${p}`);
      expect(r.status(), p).toBe(401);
    }
    // Volontaire (GAP-19) : sans jeton invité valide, 404 et non 401.
    expect((await request.get(`${CORE_URL}/v1/configs/by-item/x`)).status()).toBe(404);
  });

  test("item public / site / config publique inconnus → 404", async ({ request }) => {
    for (const p of [
      "/v1/public/items/nope",
      "/v1/public/sites/nope",
      "/v1/public/sites/nope/social-preview",
      "/v1/public/configs/by-item/nope",
    ]) {
      const r = await request.get(`${CORE_URL}${p}`);
      expect(r.status(), p).toBe(404);
    }
  });

  test("sitemap.xml : XML valide (urlset vide) et type application/xml", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/public/sitemap.xml`);
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toContain("application/xml");
    expect(await r.text()).toContain("<urlset");
  });

  test("robots.txt : pointe vers le sitemap du domaine public", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/public/robots.txt`);
    const txt = await r.text();
    expect(txt).toContain("User-agent: *");
    expect(txt).toContain(`Sitemap: ${SHELL_URL}/sitemap.xml`);
  });

  // j01-006 : HEAD refusé sur sitemap/robots.
  test.fixme("j01-006 : HEAD /sitemap.xml et /robots.txt répondent 200", async ({ request }) => {
    for (const p of ["sitemap.xml", "robots.txt"]) {
      const r = await request.head(`${CORE_URL}/v1/public/${p}`);
      expect(r.status(), p).toBe(200);
    }
  });

  test("lien de partage : jeton inconnu → 401 sans fuite d'information", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/share-links/aud-j01-bidon`);
    expect(r.status()).toBe(401);
    expect((await r.json()).detail).toBe("invalid or expired share link");
  });

  test("lien de partage : jeton pathologique (très long / encodé) → 401/404, jamais 500", async ({
    request,
  }) => {
    for (const tok of ["a".repeat(8000), "%00", "..%2F..%2Fetc", "e30.e30.e30"]) {
      const r = await request.get(`${CORE_URL}/v1/share-links/${tok}`);
      expect(r.status(), tok.slice(0, 20)).toBeLessThan(500);
    }
  });

  test("collections publiques : liste et détail lisibles sans jeton", async ({ request }) => {
    const r = await request.get(`${CORE_URL}/v1/collections`);
    expect(r.status()).toBe(200);
    for (const c of (await r.json()).collections) {
      expect(c.isPublic).toBe(true);
      expect(c.permissions.write).toBe(false);
      expect(c.permissions.delete).toBe(false);
      expect(c.permissions.share).toBe(false);
    }
  });

  test("écriture anonyme refusée (POST collection, POST feature, POST config)", async ({
    request,
  }) => {
    for (const [p, body] of [
      ["/v1/collections", { id: "aud-j01" }],
      ["/v1/collections/incidents/items", { type: "Feature", geometry: null, properties: {} }],
      ["/v1/configs", { title: "x" }],
    ] as const) {
      const r = await request.post(`${CORE_URL}${p}`, { data: body });
      expect([401, 403], p).toContain(r.status());
    }
  });

  test("STAC / DCAT publics répondent sans jeton", async ({ request }) => {
    for (const p of ["/v1/stac", "/v1/stac/collections", "/v1/dcat/catalog"]) {
      const r = await request.get(`${CORE_URL}${p}`);
      expect(r.status(), p).toBe(200);
    }
  });

  test("balayage anonyme : 60 requêtes /v1/public/items sans 429 (aucun rate limit cœur)", async ({
    request,
  }) => {
    const codes = new Set<number>();
    for (let i = 0; i < 60; i++) {
      codes.add((await request.get(`${CORE_URL}/v1/public/items?pageSize=100000`)).status());
    }
    expect([...codes]).toEqual([200]);
  });
});
