import { test, expect, type Page } from "@playwright/test";

// P07 (RC-6) : tours de copilote sous OIDC RÉEL (Keycloak), LLM fake
// (CORE_LLM_PROVIDER=fake, câblé dans le .env du job CI shell-e2e-oidc).
// Les E2E historiques passent par `mock-mcp-token` et ne voyaient pas que
// signinSilent() démontait le shell (j11-007).

const ALICE = { username: "alice", password: "Demo1234!" };

test.setTimeout(240_000);

// En prod le shell et le cœur sont servis sous la même origine (Traefik) ; le
// job CI n'a pas Traefik : le navigateur appelle le cœur (:8200) depuis :8300 et
// le cœur n'expose volontairement aucun CORS global. On le simule côté test.
async function allowCrossOriginCore(page: Page) {
  const cors = {
    "access-control-allow-origin": "http://localhost:8300",
    "access-control-allow-headers": "authorization, content-type, if-match",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "access-control-expose-headers": "etag, location",
  };
  await page.route(/:8200\/v1\//, async (route) => {
    if (route.request().method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: cors });
    }
    const res = await route.fetch();
    return route.fulfill({ response: res, headers: { ...res.headers(), ...cors } });
  });
}

async function login(page: Page): Promise<{ authorization: string; coreUrl: string }> {
  await allowCrossOriginCore(page);
  // Le jeton REST vit en mémoire : on le récupère sur le premier appel au cœur.
  const bearer = page.waitForRequest(
    (r) => /\/v1\//.test(r.url()) && Boolean(r.headers().authorization),
    { timeout: 60_000 },
  );
  await page.goto("/");
  await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
  await page.fill('input[name="username"]', ALICE.username);
  await page.fill('input[name="password"]', ALICE.password);
  await page.click('input[type="submit"], button[type="submit"]');
  const req = await bearer;
  return { authorization: req.headers().authorization, coreUrl: new URL(req.url()).origin };
}

function audOf(jwt: string): string[] {
  const payload = JSON.parse(Buffer.from(jwt.split(".")[1], "base64url").toString());
  return ([] as string[]).concat(payload.aud ?? []);
}

async function ask(page: Page, message: string) {
  const turn = page.waitForResponse((r) => r.url().includes("/v1/copilot/turn"));
  await page.getByLabel("Message au copilote").fill(message);
  await page.getByRole("button", { name: "Envoyer" }).click();
  return turn;
}

test("copilote sous OIDC réel : brouillon intact, jeton d'audience MCP, 25 tours sans 422", async ({
  page,
}) => {
  const { authorization, coreUrl } = await login(page);
  const created = await page.request.post(`${coreUrl}/v1/configs`, {
    headers: { authorization },
    data: {
      title: "copilot-oidc",
      config: { version: 1, kind: "app", layout: { type: "grid", items: [] } },
    },
  });
  expect(created.status()).toBe(201);
  const { itemId } = await created.json();

  // Lien direct : la route demandée survit à l'aller-retour Keycloak (j02-004).
  await page.goto(`/apps/${itemId}/edit`);
  await page.waitForURL(new RegExp(`/apps/${itemId}/edit$`), { timeout: 60_000 });
  expect(page.url()).not.toMatch(/[?&](code|state)=/);

  await page.getByRole("button", { name: "Texte" }).click();
  const widgets = page.getByRole("button", { name: /^Sélectionner widget-/ });
  await expect(widgets).toHaveCount(1);

  // 3 tours : aucun remontage, brouillon et conversation conservés.
  for (let i = 1; i <= 3; i++) {
    const res = await ask(page, `tour ${i}`);
    expect(res.status()).toBe(200);
    if (i === 1) {
      const sent = res.request().postDataJSON();
      expect(audOf(sent.mcpToken)).toContain("geostudio-mcp");
    }
    await expect(page.getByText(`tour ${i}`, { exact: true })).toBeVisible();
    await expect(widgets).toHaveCount(1);
  }
  await expect(page.getByText("tour 1", { exact: true })).toBeVisible();

  // 25 tours de plus (28 au total) : fenêtre glissante, jamais de 422.
  for (let i = 4; i <= 28; i++) {
    const res = await ask(page, `tour ${i}`);
    expect(res.status(), `tour ${i}`).not.toBe(422);
    expect(res.status(), `tour ${i}`).toBe(200);
  }
  await expect(widgets).toHaveCount(1);
});
