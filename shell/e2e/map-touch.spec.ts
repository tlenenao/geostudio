// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// Tâche 36 (plan Vague C, SP-C6, D16) : audit tactile de la carte.
//
// Ne tourne que sous le projet Playwright "mobile-touch" (`playwright.config.ts`,
// `hasTouch: true`, viewport iPhone 13) — `locator.tap()` lève sans ce
// contexte tactile. Patron repris de `map-popup.spec.ts` (mockCore, tuile
// MVT fixture servie sous "communes", item publié "map-1", clic sur un
// quadrant du canvas plutôt que son centre exact et `toPass` pour absorber
// le chargement asynchrone de la tuile) : même config de carte
// (`TILED_MAP_CONFIG` dans mocks.ts), donc même défaut connu de la fixture
// (un fin seam non rempli traverse le centre du canvas à cette combinaison
// viewport/zoom, cf. commentaire de map-popup.spec.ts).
test("le tap sur une entité tuilée ouvre son popup", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  const popup = page.getByRole("dialog", { name: "Attributs de l'entité" });
  await expect(async () => {
    await canvas.tap({ position: { x: box.width / 4, y: box.height / 4 } });
    await expect(popup).toBeVisible({ timeout: 300 });
  }).toPass({ timeout: 10_000 });
});

// D16 (proposition WCAG 2.5.5, cible tactile AA) : chaque bouton de la barre
// d'outils de mesure/croquis doit offrir au moins 24x24px. "Mesurer" est le
// premier bouton du panneau (`MapMeasureSketchToolbar.tsx`), toujours rendu
// (barre non conditionnée à un mode actif).
test("le bouton « Mesurer » a une cible tactile d'au moins 24x24px", async ({ page }) => {
  await mockCore(page);
  await page.goto("/maps/map-1");
  const button = page.getByRole("button", { name: /mesure/i });
  await expect(button).toBeVisible();
  const box = await button.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(24);
  expect(box?.height).toBeGreaterThanOrEqual(24);
});
