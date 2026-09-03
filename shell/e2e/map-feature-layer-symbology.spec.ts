// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const POI_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { categorie: "banc" },
      geometry: { type: "Point", coordinates: [2.4, 46.6] },
    },
    {
      type: "Feature",
      properties: { categorie: "arbre" },
      geometry: { type: "Point", coordinates: [2.5, 46.7] },
    },
    {
      type: "Feature",
      properties: { categorie: "banc" },
      geometry: { type: "Point", coordinates: [2.6, 46.8] },
    },
  ],
};

// Preuve de sortie SP-28 : une couche ajoutée par une simple URL GeoJSON (pas
// de collection derrière) reçoit une symbologie catégorielle dans l'éditeur
// de cartes — le domaine est calculé depuis l'URL mockée ci-dessous,
// jamais via le cœur (aucune route /aggregate n'est enregistrée ici).
test("add a layer by GeoJSON URL and style it categorically from its own data", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://external.test/poi.geojson", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/geo+json",
      body: JSON.stringify(POI_GEOJSON),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte POI");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Titre de la couche GeoJSON").fill("Points d'intérêt");
  await page.getByLabel("URL du GeoJSON").fill("https://external.test/poi.geojson");
  await page.getByRole("button", { name: "Ajouter la couche" }).click();
  // SP-36 (docs/superpowers/specs/2026-09-03-sp36-layerspanel-titre-flex-wrap-design.md) :
  // le <span class="truncate"> du titre de couche s'effondrait à une largeur
  // de 0px pour les couches vector/feature (flex-wrap manquant sur le <li>
  // parent de LayersPanel.tsx) — corrigé. Assertion directe, plus besoin du
  // bouton "Retirer …" comme preuve indirecte.
  await expect(page.getByText("Points d'intérêt", { exact: true }).first()).toBeVisible();

  await page.getByLabel("Champ couleur").fill("categorie");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText("banc")).toBeVisible();
  await expect(page.getByText("arbre")).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Points d'intérêt", { exact: true }).first()).toBeVisible();
});
