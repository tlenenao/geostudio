// SPDX-License-Identifier: Apache-2.0
// REV-323 (lot C) : l'onglet actif du triptyque d'un éditeur survit au rechargement (?tab=).
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ANALYST_ME } from "./mocks";

test("SQL Lab en vue étroite : l'onglet Historique est porté par l'URL et survit au rechargement", async ({
  page,
}) => {
  await page.setViewportSize({ width: 600, height: 800 });
  await mockCore(page);
  await mockMe(page, ANALYST_ME);
  await page.goto("/analytics/sql");
  await page.getByRole("tab", { name: "Historique" }).click();
  await expect(page).toHaveURL(/tab=history/);
  await page.reload();
  await expect(page.getByRole("tab", { name: "Historique", selected: true })).toBeVisible();
});
