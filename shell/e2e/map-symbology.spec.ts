// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// La preuve de sortie du plan SP-25 : un auteur configure 5 classes de
// quantiles sur une couche tuilée, enregistre, recharge la page — et le
// rendu (les classes calculées, gelées dans la config sauvegardée) survit
// sans qu'aucun nouvel appel /aggregate ne soit émis. Reprend telle quelle
// la mécanique de map-popup.spec.ts (SP-24) : même fixture MVT, même route
// de tuiles, même flux de navigation que map-editor.spec.ts pour créer une
// carte et y ajouter la couche "Communes".
test("author 5 quantile classes on a tiled layer, save, reload, and the rendered colors survive with no new aggregate call", async ({
  page,
}) => {
  await mockCore(page);
  // Toute tuile demandée renvoie la même fixture (cf. map-popup.spec.ts) —
  // seul le rendu du canvas nous intéresse ici, pas le contenu des tuiles.
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  await page.route("**/collections/*/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: "value",
        rows: [{ value: 0, min: 0, q1: 20, q2: 40, q3: 60, q4: 80, max: 100 }],
      },
    });
  });

  // Navigation identique à map-editor.spec.ts : créer une carte, ajouter la
  // couche tuilée "Communes" depuis le LayerPicker.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte symbologie");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByRole("button", { name: /Communes/ }).click();
  // SP-36 : couvre le cas partagé jamais testé avant ce plan — couche
  // "vector" (pas seulement "feature" comme dans
  // map-feature-layer-symbology.spec.ts). exact:true est nécessaire : le
  // bouton source du LayerPicker ci-dessus a pour texte accessible complet
  // "Communes vector" (le kind est concaténé au titre dans le bouton),
  // jamais "Communes" seul — mais une ambiguïté réelle existe : la liste de
  // sources du LayerPicker garde un <li>Communes</li> (source déjà ajoutée,
  // affiché différemment) en plus du <span> de titre dans LayersPanel — d'où
  // .first() (violation de strict mode observée à l'exécution, cf. rapport).
  await expect(page.getByText("Communes", { exact: true }).first()).toBeVisible();

  // Configurer la symbologie via l'UI réelle (MapSymbologyEditor.tsx).
  await page.getByLabel("Champ couleur").fill("population");
  await page.getByLabel("Type de couleur").selectOption("numeric");
  await page.getByLabel("Méthode de classification").selectOption("quantile");
  await page.getByLabel("Nombre de classes").fill("5");
  await page.getByLabel("Palette").selectOption("sequential-blue");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText(/0\.0.*100\.0/)).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  // À partir d'ici, tout nouvel appel /aggregate est un bug : le domaine et
  // les seuils calculés doivent être gelés dans la config enregistrée, pas
  // recalculés à chaque chargement.
  let aggregateCallsAfterSave = 0;
  page.on("request", (req) => {
    if (req.url().includes("/aggregate")) aggregateCallsAfterSave++;
  });

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText(/0\.0.*100\.0/)).toBeVisible();
  expect(aggregateCallsAfterSave).toBe(0);
});
