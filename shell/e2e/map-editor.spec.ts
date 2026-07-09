import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create a Map → add a layer → save → canvas mounts", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/maps\/77$/);

  // The real MapLibre canvas mounts (Chromium has WebGL).
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Add a layer from the picker, then save.
  await page.getByRole("button", { name: /Communes/ }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // No error alert after saving.
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);
});
