// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { bindTemplateSources, mockCore } from "./mocks";

// ARC-21 : panneau « Enregistrements liés » du widget Formulaire (patron entity-history.spec.ts).
test("consulter les enregistrements liés d'une entité", async ({ page }) => {
  await mockCore(page);
  const relation = {
    id: "r1",
    name: "proprietaires",
    cardinality: "one_to_many",
    parentCollectionId: "incidents",
    childCollectionId: "owners",
    onDelete: "restrict",
  };
  await page.route("**/collections/incidents/relations", async (route) => {
    await route.fulfill({ json: [relation] });
  });
  await page.route("**/collections/incidents/items/1/related/r1", async (route) => {
    await route.fulfill({
      json: {
        relation,
        direction: "children",
        collectionId: "owners",
        features: [{ id: 7, properties: { nom: "Mme Durand" } }],
        numberReturned: 1,
        numberMatched: 1,
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await bindTemplateSources(dialog);
  await dialog.getByLabel("Titre").fill("Liés");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Sélectionner Formulaire" }).click();
  await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
  await expect(page.getByLabel("Label du champ titre")).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("titre").fill("Fuite d'eau");
  await page.getByLabel("gravite").selectOption("haute");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();
  await page.getByText("Fuite d'eau").click();

  const toggle = page.getByRole("button", { name: "Enregistrements liés" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(page.getByText("proprietaires (1)")).toBeVisible();
  await expect(page.getByText("Mme Durand")).toBeVisible();
});
