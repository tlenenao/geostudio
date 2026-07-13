import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("searching in the layer picker filters collections by title", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  const search = page.getByRole("searchbox", { name: /rechercher une source de couche/i });
  await search.fill("incid");

  await expect(page.getByRole("button", { name: /Incidents voirie/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Communes/ })).not.toBeVisible();
});
