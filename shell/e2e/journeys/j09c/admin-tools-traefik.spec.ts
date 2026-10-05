import { expect, test } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor } from "../j09b/helpers";

// REV-274 (a) / j09-016 : CORE_ADMIN_TOOLS_ENABLED derrière Traefik, parcours NAVIGATEUR de bout
// en bout (lancement -> redirection 302 du cœur -> cookie posé par le navigateur -> Martin).
// j08b couvre le même contrat en HTTP brut (fetch) ; ici c'est le navigateur qui suit la chaîne.
// Passerelle : Traefik en HTTPS sur localhost (certificat auto-signé de la stack d'audit).
const GATEWAY = process.env.ADMIN_GATEWAY_URL ?? "https://localhost";

test.use({ ignoreHTTPSErrors: true });

test("le navigateur suit l'URL de lancement : cookie gs_admin_session durci, Martin servi", async ({
  browser,
}) => {
  const admin = await apiFor("admin");
  const launch = await admin.send("POST", "/v1/admin-tools/launch/martin");
  expect(launch.status).toBe(200);
  expect(launch.body.url).toContain("/v1/admin-tools/session/martin?_at=");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  await page.goto(launch.body.url);
  await expect(page).toHaveURL(new RegExp(`^${GATEWAY}/admin/martin/`));

  const cookie = (await context.cookies()).find((c) => c.name === "gs_admin_session");
  expect(cookie, "cookie gs_admin_session posé").toBeTruthy();
  expect(cookie!.httpOnly).toBe(true);
  expect(cookie!.secure).toBe(true);
  expect(cookie!.sameSite).toBe("Strict");
  expect(cookie!.path).toBe("/admin");

  const catalog = await context.request.get(`${GATEWAY}/admin/martin/catalog`);
  expect(catalog.status()).toBe(200);
  await context.close();
});

test("sans cookie la passerelle refuse (forwardAuth 403) ; jeton falsifié refusé (401)", async ({
  playwright,
}) => {
  const anon = await playwright.request.newContext({ ignoreHTTPSErrors: true });
  expect((await anon.get(`${GATEWAY}/admin/martin/catalog`, { maxRedirects: 0 })).status()).toBe(
    403,
  );
  const forged = await anon.get(`${CORE_URL}/v1/admin-tools/session/martin?_at=falsifie`, {
    maxRedirects: 0,
  });
  expect(forged.status()).toBe(401);
  await anon.dispose();
});
