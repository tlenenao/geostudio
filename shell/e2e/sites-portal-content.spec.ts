// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, y ajouter Hero+RichSection+Gallery, publier, consulter en anonyme", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // 1. Créer un Site depuis le catalogue.
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("site");
  await page.getByLabel("Titre").fill("Mon Portail");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/site-1\/edit$/);

  // 2. Ajouter Hero + RichSection + Gallery depuis la palette, puis Enregistrer.
  await page.getByRole("button", { name: "Hero" }).click();
  await page.getByLabel("Titre du bandeau").fill("Bienvenue sur mon portail");

  await page.getByRole("button", { name: "Section riche" }).click();
  await page.getByLabel("Markdown").fill("## À propos\n\nTexte **important**.");

  await page.getByRole("button", { name: "Galerie" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 3. Publier.
  await page.goto("/items/site-1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 4. Consultation publique anonyme : Hero, Markdown rendu, galerie des items publiés.
  await page.goto("/sites/mon-portail");
  await expect(page.getByText("Bienvenue sur mon portail")).toBeVisible();
  await expect(page.getByRole("heading", { name: "À propos" })).toBeVisible();
  await expect(page.getByText("important")).toBeVisible();
  await expect(page.getByText("Carte des risques")).toBeVisible();
  // Aucun item non publié ("Alpha", fixture du mock générique, n'est jamais servi par /public/items).
  await expect(page.getByText("Alpha")).toHaveCount(0);

  // 5. Cliquer la vignette → vue publique per-item, rendue par AppRenderer runtime.
  await page.getByRole("link", { name: /Carte des risques/ }).click();
  await expect(page).toHaveURL(/\/public\/items\/8$/);
  await expect(page.getByText("Detail de l'article")).toBeVisible();
});
