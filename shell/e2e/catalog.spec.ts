import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("login (mock) → list → open item", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await expect(page.getByText("GeoStudio")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  await page.getByRole("button", { name: /ouvrir/i }).first().click();
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await expect(page.getByRole("button", { name: /éditeur/i })).toBeDisabled();
});

test("create an App → lands on its detail page", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Titre").fill("Créée");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/items\/9$/);
  await expect(page.getByRole("heading", { name: "Créée" })).toBeVisible();
});

test("delete an item from the catalog", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).first().click();
  await page.getByRole("button", { name: /^supprimer$/i }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});

test("delete from the detail page returns to the catalog", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await page.getByRole("button", { name: /ouvrir/i }).first().click();
  await expect(page).toHaveURL(/\/items\/1$/);
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: /^supprimer$/i }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});

test("filters the catalog to my items (empty for the mock user)", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByLabel("Portée").selectOption("mine");
  await expect(page.getByText("Aucun élément")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});
