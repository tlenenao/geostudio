// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, le publier, le consulter en anonyme", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // 1. Créer un Site depuis le catalogue.
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("site");
  await page.getByLabel("Titre").fill("Mon Portail");
  await expect(page.getByLabel("Slug")).toHaveValue("mon-portail");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/site-1\/edit$/);

  // 2. Publier — même choreographie que publication.spec.ts.
  await page.goto("/items/site-1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 3. Consultation publique anonyme, par slug.
  await page.goto("/sites/mon-portail");
  await expect(page.getByText("Bienvenue sur le portail")).toBeVisible();
  await expect(page.getByText(/introuvable/i)).toHaveCount(0);
});

test("un site non publié / inexistant → introuvable sans fuite", async ({ page }) => {
  await mockCore(page);
  await page.goto("/sites/inexistant");
  await expect(page.getByText(/introuvable/i)).toBeVisible();
});
