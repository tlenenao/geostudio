// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un auteur crée une story cartographique depuis le gabarit et la parcourt par chapitres", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // Créer une app depuis le gabarit « Story cartographique ».
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("story-cartographique");
  await dialog.getByLabel("Titre").fill("Ma story");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Le panneau Navigation expose le mode story.
  await expect(page.getByLabel("Mode de navigation")).toHaveValue("story");

  // Enregistrer puis ouvrir en runtime.
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.goto("/apps/9");

  // Chapitre 1 : Précédent désactivé, narratif du chapitre 1 visible.
  await expect(page.getByText("Chapitre 1 / 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Précédent" })).toBeDisabled();
  await expect(page.getByText("Introduction")).toBeVisible();

  // Suivant → chapitre 2.
  await page.getByRole("button", { name: "Suivant" }).click();
  await expect(page.getByText("Chapitre 2 / 3")).toBeVisible();
  await expect(page.getByText("Développement")).toBeVisible();

  // Suivant → chapitre 3, Suivant désormais désactivé.
  await page.getByRole("button", { name: "Suivant" }).click();
  await expect(page.getByText("Chapitre 3 / 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Suivant" })).toBeDisabled();

  // Précédent revient au chapitre 2.
  await page.getByRole("button", { name: "Précédent" }).click();
  await expect(page.getByText("Chapitre 2 / 3")).toBeVisible();
});
