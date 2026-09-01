// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe } from "./mocks";

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
    // Explicite (pas juste {}) : le défaut partagé de mockMe() a
    // hasAnyEditorRole: true (cf. mocks.ts), donc ce cas doit le désarmer
    // lui-même pour rester le profil "aucun rôle" qu'il prétend tester.
    overrides: { isAdmin: false, isAnalyst: false, hasAnyEditorRole: false },
    badge: "Lecteur",
  },
];

for (const { profile, overrides, badge } of CASES) {
  test(`le badge de rôle affiche « ${badge} » pour un compte ${profile}`, async ({ page }) => {
    await mockCore(page);
    await mockMe(page, overrides);
    await page.goto("/");
    await page.getByRole("button", { name: "Compte" }).click();
    await expect(page.getByText(badge, { exact: true })).toBeVisible();
  });
}
