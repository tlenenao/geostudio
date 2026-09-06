// SPDX-License-Identifier: Apache-2.0

import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// Mêmes conventions que analytics-context.spec.ts (SP-14b/14d) : construit
// l'app via la vraie UI du builder, jamais en injectant du JSON brut.

async function createApp(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill(title);
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

async function addFeaturesSource(page: Page, collection: string) {
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page
    .getByLabel(/Collection de la source/)
    .last()
    .fill(collection);
}

async function promoteLastSource(page: Page, expectedActiveCount: number) {
  await page
    .getByRole("button", { name: /Promouvoir en dataset partagé/ })
    .last()
    .click();
  await expect(page.getByText("Dataset partagé actif")).toHaveCount(expectedActiveCount);
}

test("exporter un widget table en CSV depuis une app en mode runtime", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "analytics",
        pk: "id",
        geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "region", type: "string" }],
      },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({
      json: { type: "FeatureCollection", features: [{ id: 1, properties: { region: "Nord" } }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset",
        itemId: "dataset-1",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: {
            source: "collection",
            collectionId: "analytics",
            columns: {},
            timeField: null,
            reactsToExtent: false,
          },
        },
      },
    });
  });
  await page.route("**/collections/analytics/export/items*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("format")).toBe("csv");
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": 'attachment; filename="analytics.csv"',
        "Access-Control-Expose-Headers": "Content-Disposition",
      },
      body: "region\nNord\n",
    });
  });

  await createApp(page, "Export table");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Explorer" }).click();
  await page.getByRole("button", { name: "Exporter en CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("analytics.csv");
});

test("exporter depuis DatasetEditPage en XLSX", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          {
            id: "villes",
            title: "Villes",
            description: "",
            tableName: "villes",
            isPublic: true,
            editable: true,
            geometryType: "Point",
            srid: 4326,
            pkColumn: "id",
            permissions: { read: true, write: true, delete: false, share: false },
            featureCount: 1,
            owner: "mockuser",
          },
        ],
      },
    });
  });
  await page.route("**/collections/villes/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "villes",
        pk: "id",
        geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "nom", type: "string" }],
      },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset",
        itemId: "dataset-1",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "villes", columns: {} },
        },
      },
    });
  });
  await page.route("https://core.test/v1/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1",
        resourceType: "dataset",
        title: "Villes partagées",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: "cfg-dataset",
        isPublished: false,
        keywords: [],
      },
    });
  });
  await page.route("**/collections/villes/export/items*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("format")).toBe("xlsx");
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="villes.xlsx"',
        "Access-Control-Expose-Headers": "Content-Disposition",
      },
      body: Buffer.from("fake-xlsx-bytes"),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("villes");
  await dialog.getByLabel("Titre").fill("Villes partagées");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter en XLSX" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("villes.xlsx");
});
