import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a static data source's records feed a widget bound to it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  const propsPanel = page.locator("aside").filter({ hasText: "Sources de données" });
  await propsPanel.getByRole("button", { name: "Ajouter une source" }).click();
  await propsPanel.getByLabel(/Type de la source/).selectOption("static");
  await propsPanel.getByRole("button", { name: "Ajouter un enregistrement" }).click();
  const area = propsPanel.getByLabel(/Propriétés de l'enregistrement/);
  await area.fill('{"titre":"Premier enregistrement"}');
  await area.blur();

  await page.getByRole("button", { name: "Liste" }).click();
  const widgetPropsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await widgetPropsPanel.getByLabel("Source de données").selectOption({ index: 1 });
  await widgetPropsPanel.getByLabel("Champ titre").fill("titre");

  await expect(page.locator("main").getByText("Premier enregistrement")).toBeVisible();
});
