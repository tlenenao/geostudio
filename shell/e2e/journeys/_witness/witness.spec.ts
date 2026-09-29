import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";

// Parcours témoin (mode mock) : prouve que la config journeys atteint la
// stack RÉELLE (shell servi sur :8300, cœur sur :8200), sans mock réseau.
test.describe("témoin stack réelle (auth mock)", () => {
  test("le cœur répond et le shell affiche le catalogue", async ({ page, request }) => {
    const health = await request.get(`${CORE_URL}/health`);
    expect(health.ok()).toBeTruthy();

    // Anti faux positif : le cœur doit répondre 2xx sur /v1/ et la bannière de
    // perte de connexion ne doit pas apparaître.
    const coreOk = page.waitForResponse((r) => r.url().startsWith(`${CORE_URL}/v1/`) && r.ok(), {
      timeout: 15_000,
    });
    await page.goto("/");
    await coreOk;
    await expect(page.getByText(/catalogue|catalog/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Connexion au serveur perdue")).not.toBeVisible();
  });

  test("aucune requête réseau n'est interceptée (pas de mock)", async ({ page }) => {
    const hosts = new Set<string>();
    page.on("request", (r) => hosts.add(new URL(r.url()).host));
    await page.goto("/");
    await expect(page.getByText(/catalogue|catalog/i).first()).toBeVisible({ timeout: 15_000 });
    expect([...hosts].some((h) => h.startsWith("core.test"))).toBe(false);
    // Preuve positive : le vrai cœur a bien été atteint.
    expect(hosts.has(new URL(CORE_URL).host)).toBe(true);
    expect(stamp("witness")).toMatch(/^aud-witness-[0-9a-z]+$/);
  });
});
