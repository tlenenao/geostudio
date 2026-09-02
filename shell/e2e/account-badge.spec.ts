// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME, ANALYST_ME, CREATOR_ME, READER_ME } from "./mocks";

const CASES: Array<{
  profile: string;
  overrides: { role: { id: string; name: string; slug: string }; privileges: string[] };
  badge: string;
}> = [
  {
    profile: "administrateur",
    overrides: ADMIN_ME,
    badge: "Administrateur",
  },
  {
    profile: "analyste",
    overrides: ANALYST_ME,
    badge: "Analyste",
  },
  {
    profile: "créateur",
    // Explicite (pas juste {}) : ce cas doit rester correct même si le
    // défaut partagé de mockMe() (DEFAULT_ME, mocks.ts) venait à changer de
    // rôle par défaut.
    overrides: CREATOR_ME,
    badge: "Créateur",
  },
  {
    profile: "lecteur (simulé — aucun privilège)",
    overrides: READER_ME,
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
