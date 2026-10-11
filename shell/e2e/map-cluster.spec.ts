// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

// 2 000 points serrés : de quoi faire un vrai regroupement dans MapLibre.
const POINTS = {
  type: "FeatureCollection",
  features: Array.from({ length: 2000 }, (_, i) => ({
    type: "Feature",
    properties: { n: i },
    geometry: {
      type: "Point",
      coordinates: [2.3 + (i % 50) * 0.001, 46.6 + Math.floor(i / 50) * 0.001],
    },
  })),
};

// ARC-01 : l'option de regroupement se règle dans l'éditeur, est acceptée à
// l'enregistrement (PUT) et survit au rechargement (piège n°5).
test("cluster option round-trips through save and reload", async ({ page }) => {
  await mockCore(page);
  await page.route("https://external.test/dense.geojson", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/geo+json",
      body: JSON.stringify(POINTS),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte dense");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Titre de la couche GeoJSON").fill("Points denses");
  await page.getByLabel("URL du GeoJSON").fill("https://external.test/dense.geojson");
  await page.getByRole("button", { name: "Ajouter la couche" }).click();

  await page.getByRole("checkbox", { name: "Regrouper les points" }).check();
  await page.getByLabel("Rayon de regroupement (pixels)").fill("70");

  const put = page.waitForRequest((r) => r.method() === "PUT" && r.url().includes("/configs/"));
  await page.getByRole("button", { name: "Enregistrer" }).click();
  const body = (await put).postDataJSON();
  expect(JSON.stringify(body)).toContain('"cluster":{"radius":70}');
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Regrouper les points" })).toBeChecked();
  await expect(page.getByLabel("Rayon de regroupement (pixels)")).toHaveValue("70");
});
