// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

function meRoute(page: Page, overrides: Record<string, boolean>) {
  return page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: false,
        version: "0.1.0",
        tenantSlug: "demo",
        ...overrides,
      },
    });
  });
}

const CASES: Array<{ profile: string; overrides: Record<string, boolean>; badge: string }> = [
  {
    profile: "administrateur",
    overrides: { isAdmin: true, isAnalyst: true, hasAnyEditorRole: true },
    badge: "Administrateur",
  },
  {
    profile: "analyste",
    overrides: { isAnalyst: true, hasAnyEditorRole: true },
    badge: "Analyste",
  },
  {
    profile: "créateur",
    overrides: { hasAnyEditorRole: true },
    badge: "Créateur",
  },
  {
    profile: "lecteur (simulé — aucun rôle éditeur, ni admin, ni analyste)",
    overrides: {},
    badge: "Lecteur",
  },
];

for (const { profile, overrides, badge } of CASES) {
  test(`le badge de rôle affiche « ${badge} » pour un compte ${profile}`, async ({ page }) => {
    await mockCore(page);
    await meRoute(page, overrides);
    await page.goto("/");
    await page.getByRole("button", { name: "Compte" }).click();
    await expect(page.getByText(badge, { exact: true })).toBeVisible();
  });
}
