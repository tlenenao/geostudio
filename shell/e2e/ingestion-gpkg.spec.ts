import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockGpkgIngestionFlow(page: Page) {
  let jobPolls = 0;
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-gpkg", key: "t/abc-multi.gpkg" },
    });
  });
  await page.route("https://minio.test/upload-gpkg", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads/inspect", async (route) => {
    await route.fulfill({
      json: {
        layers: [
          { name: "villes", featureCount: 2, geometryType: "Point" },
          { name: "routes", featureCount: 5, geometryType: "LineString" },
        ],
      },
    });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-gpkg" } });
  });
  await page.route("**/uploads/job-gpkg", async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
      });
    } else {
      await route.fulfill({
        json: { status: "done", errorMessage: null, collectionId: "ingest_multi", itemId: "88" },
      });
    }
  });
  await page.route("https://core.test/items/88", async (route) => {
    await route.fulfill({
      json: {
        pk: "88", resourceType: "map", title: "Réseau", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false,
      },
    });
  });
  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/88") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-88", itemId: "88", kind: "map",
        config: {
          kind: "map", theme: {}, dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [1.5, 45.5], zoom: 10 },
            layers: [{
              id: "l1", title: "Réseau", visible: true, kind: "feature",
              url: "https://core.test/collections/ingest_multi/items",
            }],
          },
        },
      },
    });
  });
}

test("importer un GeoPackage à plusieurs couches force la sélection d'une couche", async ({ page }) => {
  await mockCore(page);
  await mockGpkgIngestionFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "multi.gpkg",
    mimeType: "application/geopackage+sqlite3",
    buffer: Buffer.from("fake-gpkg-bytes"),
  });
  await page.getByLabel("Titre de la collection").fill("Réseau");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page.getByLabel("Couche à importer")).toBeVisible();
  await page.getByLabel("Couche à importer").selectOption("routes");
  await page.getByRole("button", { name: "Continuer" }).click();

  await expect(page).toHaveURL(/\/maps\/88$/, { timeout: 10_000 });
});
