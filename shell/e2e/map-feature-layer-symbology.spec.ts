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
  // On confirme l'ajout via le bouton "Retirer <titre>" plutôt que le texte
  // du titre lui-même : pour une couche vector/feature (éditeur toujours
  // déplié, pas d'accordéon), la ligne <li> est un flex-row sans retour à la
  // ligne où le panneau d'édition (`basis-full`) revendique toute la largeur
  // disponible — le <span class="truncate"> du titre, seul élément flexible
  // avec min-width auto ramené à 0 par `overflow: hidden`, se retrouve
  // rendu à une largeur de 0px (visible dans le DOM, invisible à l'écran).
  // C'est un détail de mise en page préexistant, partagé avec les couches
  // "vector" (ex. "Communes" dans map-symbology.spec.ts, qui ne teste jamais
  // la visibilité du titre après ajout) — hors périmètre de cette tâche.
  // Le bouton "Retirer …" porte le même titre dans son aria-label et n'est
  // pas soumis à cet écrasement (il n'est pas flex-1).
  await expect(page.getByRole("button", { name: "Retirer Points d'intérêt" })).toBeVisible();

  await page.getByLabel("Champ couleur").fill("categorie");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText("banc")).toBeVisible();
  await expect(page.getByText("arbre")).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retirer Points d'intérêt" })).toBeVisible();
});
