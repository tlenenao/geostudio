// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, y ajouter un DatasetCard lié à une collection publique, publier, consulter et télécharger en anonyme", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");

  // 1. Créer un Site.
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page
    .getByRole("dialog", { name: "Nouvel élément" })
    .getByLabel("Type")
    .selectOption("site");
  await page.getByLabel("Titre").fill("Portail Parcs");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/site-1\/edit$/);

  // 2. Source de données -> collection publique "parcs".
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");

  // 3. Ajouter la Fiche jeu de données, la lier à la source.
  await page.getByRole("button", { name: "Fiche jeu de données" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 4. Publier.
  await page.goto("/items/site-1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 5. Consultation anonyme du site : la fiche affiche titre + nombre d'entités.
  await page.goto("/sites/portail-parcs");
  await expect(page.getByRole("heading", { name: "Parcs" })).toBeVisible();
  await expect(page.getByText(/2 entités/)).toBeVisible();

  // 6. Clic "Voir le jeu de données" -> page dataset publique complète.
  await page.getByRole("link", { name: "Voir le jeu de données" }).click();
  await expect(page).toHaveURL(/\/public\/datasets\/parcs$/);
  await expect(page.getByRole("heading", { name: "Parcs" })).toBeVisible();
  await expect(page.getByText("Parcs publics de la ville")).toBeVisible();
  await expect(page.getByText("Parc du Test")).toBeVisible(); // aperçu Table

  // 7. Téléchargement GeoJSON (lien direct, toujours disponible).
  const [geojsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Télécharger GeoJSON" }).click(),
  ]);
  expect(geojsonDownload.suggestedFilename()).toBe("parcs.geojson");

  // 8. Téléchargement CSV (sous le seuil de 10000 -> bouton actif).
  const [csvDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Télécharger CSV" }).click(),
  ]);
  expect(csvDownload.suggestedFilename()).toBe("parcs.csv");
});

test("une collection non publique via /public/datasets/:id rend « introuvable », sans fuite d'existence", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/collections/incidents", async (route) => {
    // "incidents" est privée dans la fixture partagée (isPublic:false) — même
    // route que get_readable_collection retournerait pour un visiteur anonyme:
    // 404, jamais 403.
    await route.fulfill({ status: 404, json: { detail: "collection not found" } });
  });
  await page.goto("/public/datasets/incidents");
  await expect(page.getByRole("alert")).toContainText(/introuvable/i);
});
