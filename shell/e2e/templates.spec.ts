import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("creating an app from a template shows its widgets immediately in the editor", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("two-column");
  await dialog.getByLabel("Titre").fill("App depuis modèle");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await expect(page.getByText("Colonne gauche")).toBeVisible();
  await expect(page.getByText("Colonne droite")).toBeVisible();
});
