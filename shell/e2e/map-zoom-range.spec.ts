// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const POINTS = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [2.3, 46.6] } },
  ],
};

// AUD-051 : la plage d'échelle d'une couche se règle dans l'éditeur, part au PUT et survit au
// rechargement (piège n°5 : chemin de lecture).
test("layer zoom range round-trips through save and reload", async ({ page }) => {
  await mockCore(page);
  await page.route("https://external.test/zoom.geojson", (route) =>
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
  await dialog.getByLabel("Titre").fill("Carte à échelle");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Titre de la couche GeoJSON").fill("Points");
  await page.getByLabel("URL du GeoJSON").fill("https://external.test/zoom.geojson");
  await page.getByRole("button", { name: "Ajouter la couche" }).click();

  await page.getByLabel("Zoom min").fill("6");
  await page.getByLabel("Zoom max").fill("12");

  const put = page.waitForRequest((r) => r.method() === "PUT" && r.url().includes("/configs/"));
  await page.getByRole("button", { name: "Enregistrer" }).click();
  const body = JSON.stringify((await put).postDataJSON());
  expect(body).toContain('"minZoom":6');
  expect(body).toContain('"maxZoom":12');

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByLabel("Zoom min")).toHaveValue("6");
  await expect(page.getByLabel("Zoom max")).toHaveValue("12");
});
