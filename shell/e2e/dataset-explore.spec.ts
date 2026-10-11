// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// REV-117 : bouton « Explorer » de la fiche publique d'un jeu de données.
test("explorer une collection publique : profil des colonnes en un clic", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/parcs/profile", async (route) => {
    await route.fulfill({
      json: {
        rowCount: 2,
        sampled: false,
        truncatedColumns: false,
        pending: false,
        asOf: "2026-10-10T10:00:00+00:00",
        columns: [
          {
            name: "nom",
            type: "string",
            nonNull: 2,
            nulls: 0,
            distinct: 2,
            topValues: [{ value: "Parc du Test", count: 1 }],
          },
        ],
        geometry: null,
      },
    });
  });
  await page.goto("/public/datasets/parcs");
  await expect(page.getByRole("heading", { name: "Parcs" })).toBeVisible();
  await page.getByRole("button", { name: "Explorer" }).click();
  await expect(page.getByRole("rowheader", { name: "nom" })).toBeVisible();
  await expect(page.getByText(/Parc du Test \(1\)/)).toBeVisible();
});
