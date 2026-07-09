import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("setting a theme color in the editor applies it in the runtime", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App thème");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Bouton widget (its background is driven by --gs-color-primary).
  await page.getByRole("button", { name: "Bouton" }).click();

  // Set the theme's primary color to a distinctive value.
  await page.getByLabel("Couleur primaire").fill("#ff0000");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: the button's real computed background reflects the theme.
  await page.goto("/apps/9");
  const button = page.getByRole("button", { name: "Bouton" });
  await expect(button).toBeVisible();
  const bg = await button.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).toBe("rgb(255, 0, 0)");
});
