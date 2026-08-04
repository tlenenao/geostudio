// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("Onglets switches which nested widget is visible", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App onglets");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Onglets" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });

  // Onglet 1 (par défaut) reçoit un Texte "Contenu A".
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Contenu A");

  // Un 2e onglet est ajouté, vide.
  await propsPanel.getByRole("button", { name: "Ajouter un onglet" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByText("Contenu A")).toBeVisible();
  await page.getByRole("button", { name: "Onglet 2" }).click();
  await expect(page.getByText("Contenu A")).toBeHidden();
});

test("Bouton opens a Modale via the action bus, and Escape closes it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App modale");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByLabel("Libellé du bouton").fill("Ouvrir");

  await page.getByRole("button", { name: "Modale" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await propsPanel.getByLabel("Titre de la modale").fill("Détail");
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Corps modale");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Modale" });
  await page.getByLabel("Action", { exact: true }).selectOption("open");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("dialog", { name: "Détail" })).not.toBeVisible();
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page.getByRole("dialog", { name: "Détail" })).toBeVisible();
  await expect(page.getByText("Corps modale")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Détail" })).not.toBeVisible();
});

test("Bouton opens a Tiroir via the action bus, and Escape closes it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App tiroir");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByLabel("Libellé du bouton").fill("Ouvrir");

  await page.getByRole("button", { name: "Tiroir" }).click();
  const propsPanel = page.locator("aside").filter({ hasText: "Propriétés" });
  await propsPanel.getByLabel("Titre du tiroir").fill("Filtres");
  await propsPanel.getByRole("button", { name: "Texte" }).click();
  await propsPanel.getByLabel("Texte du widget").fill("Corps tiroir");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Tiroir" });
  await page.getByLabel("Action", { exact: true }).selectOption("open");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("dialog", { name: "Filtres" })).not.toBeVisible();
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page.getByRole("dialog", { name: "Filtres" })).toBeVisible();
  await expect(page.getByText("Corps tiroir")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Filtres" })).not.toBeVisible();
});
