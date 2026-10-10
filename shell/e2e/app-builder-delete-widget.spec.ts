import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a widget can be removed from the canvas and the removal is undoable", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte", exact: true }).click();
  const select = page.getByRole("button", { name: /^Sélectionner / });
  await expect(select).toBeVisible();
  // Attendre au-delà de la fenêtre de coalescing d'undo (400ms, SP-19) : sans
  // ce délai, l'ajout et la suppression tombent dans le même burst d'undo et
  // Ctrl+Z réapplique la même config (0 widget) au lieu de restaurer le
  // widget ajouté — confirmé par exécution réelle de ce test sans le délai.
  await page.waitForTimeout(500);
  await select.click();
  await page.getByRole("button", { name: /^Supprimer / }).click();
  await expect(select).toHaveCount(0);

  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button", { name: /^Sélectionner / })).toBeVisible();
});

test("REV-285 h : supprimer le 1er de deux widgets ne renumérote pas le survivant", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte", exact: true }).click();
  await page.getByRole("button", { name: "Texte", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner Texte 2/ })).toBeVisible();
  await page.getByRole("button", { name: /^Sélectionner Texte 1/ }).click();
  await page.getByRole("button", { name: /^Supprimer / }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner Texte 1/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Sélectionner Texte 2/ })).toBeVisible();
});
