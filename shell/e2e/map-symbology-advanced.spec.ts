// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// La preuve de sortie du chantier 4.4 du plan d'action : un auteur pose un
// contour, une opacité et une étiquette sur une couche tuilée, enregistre,
// recharge la page — et les quatre valeurs reviennent identiques. Reprend la
// mécanique de map-symbology.spec.ts (SP-25) : même fixture MVT, même route
// de tuiles, même flux de navigation pour créer une carte et y ajouter la
// couche "Communes". Le rendu des glyphes n'est volontairement PAS asserté
// (dépend du service de glyphes du fond de carte, ressource réseau) — Task 14
// couvre déjà en unitaire le cas « style sans glyphs ».
test("un contour, une opacité et une étiquette survivent à l'enregistrement et au rechargement", async ({
  page,
}) => {
  await mockCore(page);
  // La bibliothèque d'icônes du tenant est interrogée par l'éditeur dès son
  // montage : sans cette route, la requête part vers un hôte non routé.
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  // Tuiles de la couche : même fixture que map-symbology.spec.ts.
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  // PAS `/maps/map-1` : ce chemin sert TILED_MAP_CONFIG en dur et ignore
  // savedConfigs (mocks.ts:320-330), donc le tour save → reload → assert ne
  // peut pas y passer. On crée la carte par l'UI, exactement comme
  // map-symbology.spec.ts, et on travaille sur le /maps/77 obtenu.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte symbologie avancée");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Ajoute la couche "Communes" depuis le LayerPicker — son éditeur de
  // symbologie apparaît immédiatement en ligne (LayersPanel.tsx).
  await page.getByRole("button", { name: /Communes/ }).click();

  // Contour : bouton "Ajouter un contour" (couleur fixe par défaut), puis
  // épaisseur et style.
  await page.getByRole("button", { name: "Ajouter un contour" }).click();
  await page.getByLabel("Épaisseur de contour (px)").fill("3");
  await page.getByLabel("Style de contour").selectOption("dashed");

  // Opacité : un input[type=range], Playwright gère `.fill()` sur un range.
  await page.getByLabel("Opacité").fill("60");

  // Étiquette.
  await page.getByRole("button", { name: "Ajouter une étiquette" }).click();
  await page.getByLabel("Gabarit d'étiquette").fill("${record.nom}");

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Réouvrir l'éditeur de la couche rechargée : "Communes" porte désormais
  // déjà la symbologie sauvegardée, donc les sections contour/étiquette sont
  // affichées d'emblée (pas de bouton "Ajouter…" à recliquer).
  await expect(page.getByLabel("Épaisseur de contour (px)")).toHaveValue("3");
  await expect(page.getByLabel("Style de contour")).toHaveValue("dashed");
  await expect(page.getByLabel("Opacité")).toHaveValue("60");
  await expect(page.getByLabel("Gabarit d'étiquette")).toHaveValue("${record.nom}");
});
