import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockXlsxIngestionFlow(page: Page) {
  let jobPolls = 0;
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({
      json: { uploadUrl: "https://minio.test/upload-xlsx", key: "t/abc-villes.xlsx" },
    });
  });
  await page.route("https://minio.test/upload-xlsx", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/uploads/inspect", async (route) => {
    await route.fulfill({ json: { layers: [], fields: ["nom", "lat", "lon"] } });
  });
  await page.route("**/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-xlsx" } });
  });
  await page.route("**/uploads/job-xlsx", async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
      });
    } else {
      await route.fulfill({
        json: { status: "done", errorMessage: null, collectionId: "ingest_xlsx", itemId: "91" },
      });
    }
  });
  await page.route("https://core.test/v1/items/91", async (route) => {
    await route.fulfill({
      json: {
        pk: "91",
        resourceType: "map",
        title: "Villes XLSX",
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
    if (!route.request().url().endsWith("/91") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-91",
        itemId: "91",
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
                title: "Villes XLSX",
                visible: true,
                kind: "feature",
                url: "https://core.test/v1/collections/ingest_xlsx/items",
              },
            ],
          },
        },
      },
    });
  });
}

test("importer un XLSX avec colonnes lat/lon détectées crée une carte sans saisie manuelle", async ({
  page,
}) => {
  await mockCore(page);
  await mockXlsxIngestionFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "villes.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("fake-xlsx-bytes"),
  });
  await page.getByLabel("Titre de la collection").fill("Villes XLSX");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await expect(page).toHaveURL(/\/maps\/91$/, { timeout: 10_000 });
});
