import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("adding a page and a Navigation widget lets the runtime navigate between pages", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App pages");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a second page (this materializes the implicit first page as "page-1")
  // then switch back to editing the first page.
  await page.getByRole("button", { name: "Ajouter une page" }).click();
  await page.getByRole("button", { name: "Ouvrir la page page-1" }).click();

  // Add a Navigation widget to page 1.
  await page.getByRole("button", { name: "Navigation" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: page 1 shows a Navigation menu; clicking "Page 2" navigates the URL.
  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Page 2" })).toBeVisible();
  await page.getByRole("button", { name: "Page 2" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/[^/]+$/);
});
