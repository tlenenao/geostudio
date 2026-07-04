import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("a per-breakpoint position is applied by the runtime at the matching viewport", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App responsive");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Text widget (lands at column 0).
  await page.getByRole("button", { name: "Texte" }).click();

  // Switch to the sm breakpoint and nudge the widget one column right.
  await page.getByRole("button", { name: "Éditer en sm" }).click();
  await page.getByLabel(/^Sélectionner widget-/).click();
  await page.getByLabel(/Déplacer widget-.* à droite/).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Narrow viewport → runtime auto-detects sm → widget at its sm column (1).
  await page.setViewportSize({ width: 500, height: 800 });
  await page.goto("/apps/9");
  await expect(page.locator("[data-breakpoint='sm']")).toBeVisible();
  await expect(page.locator("[data-col]").first()).toHaveAttribute("data-col", "1");

  // Wide viewport → runtime auto-detects lg → base column (0), unchanged.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.reload();
  await expect(page.locator("[data-breakpoint='lg']")).toBeVisible();
  await expect(page.locator("[data-col]").first()).toHaveAttribute("data-col", "0");
});
