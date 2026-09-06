import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockIngestionFlow(page: Page) {
  let jobPolls = 0;
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" },
    });
  });
  await page.route("https://minio.test/upload-1", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" } });
  });
  await page.route("**/uploads/job-1", async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
      });
    } else {
      await route.fulfill({
        json: { status: "done", errorMessage: null, collectionId: "ingest_abc", itemId: "78" },
      });
    }
  });
  await page.route("https://core.test/v1/items/78", async (route) => {
    await route.fulfill({
      json: {
        pk: "78",
        resourceType: "map",
        title: "Villes importées",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: null,
        isPublished: false,
      },
    });
  });
  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/78") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-78",
        itemId: "78",
        kind: "map",
        config: {
          kind: "map",
          theme: {},
          dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [1.5, 45.5], zoom: 10 },
            layers: [
              {
                id: "l1",
                title: "Villes importées",
                visible: true,
                kind: "feature",
                url: "https://core.test/v1/collections/ingest_abc/items",
              },
            ],
          },
        },
      },
    });
  });
}

test("importer un GeoJSON crée une carte accessible sans intervention manuelle", async ({
  page,
}) => {
  await mockCore(page);
  await mockIngestionFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "villes.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from('{"type":"FeatureCollection","features":[]}'),
  });
  await page.getByLabel("Titre de la collection").fill("Villes importées");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page).toHaveURL(/\/maps\/78$/, { timeout: 10_000 });
});

test("un job en erreur affiche le message et permet de recommencer", async ({ page }) => {
  await mockCore(page);
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-2", key: "t/def-broken.geojson" },
    });
  });
  await page.route("https://minio.test/upload-2", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-2" } });
  });
  await page.route("**/uploads/job-2", async (route) => {
    await route.fulfill({
      json: { status: "error", errorMessage: "JSON invalide", collectionId: null, itemId: null },
    });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "broken.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from("not json"),
  });
  await page.getByLabel("Titre de la collection").fill("Casse");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("JSON invalide");
  await expect(page.getByRole("button", { name: "Importer", exact: true })).toBeEnabled();
});
