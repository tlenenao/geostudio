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
