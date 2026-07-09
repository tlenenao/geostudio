import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create an App → add a Text widget → save → runtime shows it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  // Scope to the dialog to avoid collision with the catalog's "Type" filter select.
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Text widget from the palette and edit its text.
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Bonjour le monde");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Open the runtime and verify the saved text renders.
  await page.goto("/apps/9");
  await expect(page.getByText("Bonjour le monde")).toBeVisible();
});
