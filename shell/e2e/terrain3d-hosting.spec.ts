// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockTerrain3DUploadFlow(page: Page) {
  let jobPolls = 0;
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, terrain3dEnabled: true } });
  });
  // Route dédiée terrain3d (jamais la générique **/uploads/presign) : c'est
  // la seule qui signe dans le bucket que le worker de conversion lit.
  await page.route("**/terrain3d/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/terrain3d-raw", key: "t-mock/x/dem.tif" },
    });
  });
  await page.route("https://minio.test/terrain3d-raw", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/terrain3d/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" }, status: 201 });
  });
  await page.route("**/terrain3d/uploads/job-1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({ json: { status: "converting", errorMessage: null, itemId: null } });
    } else {
      await route.fulfill({ json: { status: "done", errorMessage: null, itemId: "d1" } });
    }
  });
  await page.route("https://core.test/v1/items?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "terrain3d") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          {
            pk: "d1",
            resourceType: "terrain3d",
            title: "Relief du massif E2E",
            abstract: "",
            owner: "mockuser",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 200,
      },
    });
  });
  await page.route("https://core.test/v1/terrain3d/d1/tiles/*/*/*.png", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from("fake-png-tile"),
    });
  });
}

test("upload a DEM, select it as hosted terrain, tiles resolve", async ({ page }) => {
  await mockCore(page);
  await mockTerrain3DUploadFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const newItemDialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await newItemDialog.getByLabel("Type").selectOption("map");
  await newItemDialog.getByLabel("Titre").fill("Carte avec terrain hébergé");
  await newItemDialog.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Activer le terrain 3D").check();
  await page.getByRole("button", { name: "Nouveau DEM" }).click();
  // Terrain3DUploadButton converti Dialog→Panel en ligne par SP-30c : plus de
  // role="dialog" à localiser. Scopé au <form> du panneau (pas un locator
  // englobant sur un rôle inexistant) : le panneau Couches de l'éditeur de
  // carte a aussi un champ "Titre du tileset 3D" (correspondance substring
  // non exacte) plus un autre champ "Titre" nu ailleurs sur la page, donc un
  // lookup non scopé heurte une violation de mode strict — même
  // justification de désambiguïsation que tileset3d.spec.ts documente pour
  // "Importer". Le <form> est identifié par son descendant unique (le champ
  // fichier), sans dépendre d'un rôle/testid sur le Panel lui-même (qui n'en
  // a aucun, cf. ui/kit/Panel.tsx).
  const demForm = page.locator("form", { has: page.getByLabel("Fichier DEM (GeoTIFF)") });
  await demForm.getByLabel("Fichier DEM (GeoTIFF)").setInputFiles({
    name: "dem.tif",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fake dem bytes"),
  });
  await demForm.getByLabel("Titre", { exact: true }).fill("Relief du massif E2E");
  await demForm.getByRole("button", { name: "Importer" }).click();
  // Le panneau ferme (close() réinitialise `open` à false côté composant) :
  // le champ fichier du formulaire disparaît du DOM.
  await expect(page.getByLabel("Fichier DEM (GeoTIFF)")).toHaveCount(0, { timeout: 10_000 });

  const tileRequest = page.waitForResponse((r) => /\/terrain3d\/d1\/tiles\/.+\.png$/.test(r.url()));
  await page.getByLabel("DEM hébergé").selectOption("d1");
  const response = await tileRequest;
  expect(response.status()).toBe(200);
});
