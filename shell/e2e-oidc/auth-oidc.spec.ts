import { test, expect } from "@playwright/test";

const ALICE = { username: "alice", password: "Demo1234!" };

test.describe("authentification OIDC réelle (Keycloak)", () => {
  test("connexion redirige vers Keycloak puis revient authentifié", async ({ page }) => {
    await page.goto("/");
    // Non authentifié : oidc-client-ts redirige vers Keycloak.
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
    await page.fill('input[name="username"]', ALICE.username);
    await page.fill('input[name="password"]', ALICE.password);
    await page.click('input[type="submit"], button[type="submit"]');
    // Retour sur le shell, authentifié.
    await page.waitForURL("http://localhost:8300/**");
    await expect(page.getByText(/catalogue|catalog/i)).toBeVisible({ timeout: 15_000 });
  });

  test("déconnexion efface la session", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
    await page.fill('input[name="username"]', ALICE.username);
    await page.fill('input[name="password"]', ALICE.password);
    await page.click('input[type="submit"], button[type="submit"]');
    await page.waitForURL("http://localhost:8300/**");

    // Sélecteur vérifié contre le code réel (shell/src/shell/chrome/AccountMenu.tsx,
    // introduit par SP-29a) : le bouton "Déconnexion" est désormais dans le
    // Popover du badge de compte (déclencheur aria-label "Compte",
    // account.menu), plus un <button> direct de AppLayout.tsx — même
    // patron que shell/e2e/account-badge.spec.ts.
    await page.getByRole("button", { name: "Compte" }).click();
    await page.getByRole("button", { name: /déconnexion|logout/i }).click();
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth|localhost:8300\/?$/);
  });
});
