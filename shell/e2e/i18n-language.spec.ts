// SPDX-License-Identifier: Apache-2.0
// AUD-019 / D8 : mécanisme de langue (préférence, chunk anglais, <html lang>).
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

test("la préférence stockée affiche l'interface en anglais, lang posé sur <html>", async ({
  page,
}) => {
  await mockCore(page);
  await page.addInitScript(() => localStorage.setItem("gs.locale", "en"));
  await page.goto("/settings");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "English" })).toBeChecked();
});

test("choisir English dans Paramètres recharge en anglais et persiste", async ({ page }) => {
  await mockCore(page);
  await page.goto("/settings");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await page.getByRole("radio", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Language" })).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("radio", { name: "English" })).toBeChecked();
});
