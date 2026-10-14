// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// ARC-33 : upload d'un raster, ajout comme couche carte (rampe + étendue), tuiles servies par le
// cœur (proxy TiTiler sous can()) avec le jeton de session.
async function mockRasterFlow(page: Page) {
  let jobPolls = 0;
  // Capacité raster active (CORE_RASTER_ENABLED) : sinon le sélecteur de couches masque le raster.
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, rasterEnabled: true } });
  });
  await page.route("**/raster/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/raster-raw", key: "t-mock/x/ortho.tif" },
    });
  });
  await page.route("https://minio.test/raster-raw", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/raster/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "rjob-1" }, status: 201 });
  });
  await page.route("**/raster/uploads/rjob-1", async (route) => {
    jobPolls += 1;
    await route.fulfill({
      json:
        jobPolls < 2
          ? { status: "converting", errorMessage: null, itemId: null }
          : { status: "done", errorMessage: null, itemId: "r1" },
    });
  });
  await page.route("https://core.test/v1/items?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "raster") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          {
            pk: "r1",
            resourceType: "raster",
            title: "Ortho E2E",
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
  await page.route("https://core.test/v1/raster/r1", async (route) => {
    await route.fulfill({
      json: {
        itemId: "r1",
        srid: 4326,
        bounds: [2, 48, 3, 49],
        width: 64,
        height: 64,
        dtype: "float32",
        nodata: -9999,
        bands: [{ index: 1, min: 64, max: 4095, mean: 2000, std: 1 }],
        sizeBytes: 1,
        limitCollectionId: null,
      },
    });
  });
  await page.route("https://core.test/v1/raster/r1/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from("fake-png-tile"),
    });
  });
}

test("upload a raster, add it as a map layer, tiles resolve with the session token", async ({
  page,
}) => {
  await mockCore(page);
  await mockRasterFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const newItemDialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await newItemDialog.getByLabel("Type").selectOption("map");
  await newItemDialog.getByLabel("Titre").fill("Carte avec raster");
  await newItemDialog.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByRole("button", { name: "Nouveau raster" }).click();
  const form = page.locator("form", { has: page.getByLabel("Fichier raster (GeoTIFF)") });
  await form.getByLabel("Fichier raster (GeoTIFF)").setInputFiles({
    name: "ortho.tif",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fake raster bytes"),
  });
  await form.getByLabel("Titre", { exact: true }).fill("Ortho E2E");
  await form.getByRole("button", { name: "Importer" }).click();
  await expect(page.getByLabel("Fichier raster (GeoTIFF)")).toHaveCount(0, { timeout: 10_000 });

  await expect(page.getByLabel("Raster hébergé")).toHaveValue("r1");
  await expect(page.getByLabel("Valeur maximale")).toHaveValue("4095");
  await page.getByLabel("Rampe de couleurs").selectOption("magma");
  const tileRequest = page.waitForRequest((r) => /\/raster\/r1\/tiles\//.test(r.url()));
  await page.getByRole("button", { name: "Ajouter le raster" }).click();
  const request = await tileRequest;
  expect(request.url()).toContain("colormap_name=magma");
  expect(request.url()).toContain("rescale=64%2C4095");
  expect(request.headers()["authorization"]).toMatch(/^Bearer /);
});
