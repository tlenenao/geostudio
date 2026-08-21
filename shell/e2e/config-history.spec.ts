// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("restaurer une version antérieure depuis le builder d'app", async ({ page }) => {
  await mockCore(page);
  await page.goto("/apps/1/edit");

  await expect(page.getByText("Historique")).toBeVisible();
  await expect(page.getByText(/Version 2/)).toBeVisible();

  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Restaurer" }).click();

  // La config rechargée après rollback est celle de la version 1 : son
  // widget porte un titre différent de celui de la version courante.
  await expect(page.getByText("Titre version 1")).toBeVisible();
  // L'undo est vidé : la restauration n'est pas annulable localement.
  await expect(page.getByRole("button", { name: "Annuler" })).toBeDisabled();
});
