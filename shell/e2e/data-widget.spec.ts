import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("bind a features source to a List widget → runtime shows a record", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App données");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a features data source and name its collection.
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");

  // Add a List widget and bind it to the source.
  await page.getByRole("button", { name: "Liste" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ titre").fill("nom");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime shows a record from the bound source.
  await page.goto("/apps/9");
  await expect(page.getByText("Parc du Test")).toBeVisible();
});
