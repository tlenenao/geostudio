import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("Filtre widget filters a bound List through the action bus", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App actions");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Data source
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");

  // List bound to the source
  await page.getByRole("button", { name: "Liste" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ titre").fill("nom");

  // Filtre widget on field "nom"
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("nom");

  // Wire Filtre.changed → Liste.setFilter
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Liste" });
  await page.getByLabel("Action").selectOption("setFilter");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: both records show first
  await page.goto("/apps/9");
  await expect(page.getByText("Parc du Test")).toBeVisible();
  await expect(page.getByText("Bois Test")).toBeVisible();

  // Typing the filter narrows the list to the matching record
  await page.getByLabel("Valeur du filtre").fill("Parc du Test");
  await expect(page.getByText("Bois Test")).toBeHidden();
  await expect(page.getByText("Parc du Test")).toBeVisible();
});
