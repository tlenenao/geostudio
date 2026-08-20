// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockTileset3DUploadFlow(page: Page) {
  let jobPolls = 0;
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, tileset3dEnabled: true } });
  });
  await page.route("**/tileset3d/uploads/job-1/parts/1/presign", async (route) => {
    await route.fulfill({ json: { uploadUrl: "https://minio.test/tileset3d-part-1" } });
  });
  await page.route("https://minio.test/tileset3d-part-1", async (route) => {
    await route.fulfill({ status: 200, headers: { ETag: '"etag-1"' }, body: "" });
  });
  await page.route("**/tileset3d/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" } });
  });
  await page.route("**/tileset3d/uploads/job-1/complete", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/tileset3d/uploads/job-1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({ json: { status: "finalizing", errorMessage: null, itemId: null } });
    } else {
      await route.fulfill({ json: { status: "done", errorMessage: null, itemId: "t1" } });
    }
  });
  await page.route("https://core.test/items?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "tileset3d") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          {
            pk: "t1",
            resourceType: "tileset3d",
            title: "Ville de test E2E",
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
  await page.route("https://core.test/tileset3d/t1/tileset.json", async (route) => {
    await route.fulfill({
      json: {
        asset: { version: "1.0" },
        geometricError: 500,
        root: {
          boundingVolume: { region: [0, 0, 0, 0, 0, 0] },
          geometricError: 500,
          refine: "ADD",
          children: [],
        },
      },
    });
  });
}

test("upload a tileset, add it to a map via LayerPicker, the proxy request succeeds", async ({
  page,
}) => {
  await mockCore(page);
  await mockTileset3DUploadFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau tileset 3D" }).click();
  await page.getByLabel("Archive du tileset (.zip)").setInputFiles({
    name: "city.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("PK\x03\x04fake"),
  });
  await page.getByLabel("Titre").fill("Ville de test E2E");
  // "Importer" (non-exact) would also match the header's "Importer un
  // fichier" trigger button, which stays in the DOM behind the dialog
  // overlay — scope to the exact submit button's accessible name, same
  // disambiguation ingestion.spec.ts already applies for the same reason.
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Nouveau tileset 3D" })).toHaveCount(0, {
    timeout: 10_000,
  });

  // "Nouveau" (non-exact) would also match the "Nouveau tileset 3D" trigger
  // button, which — unlike in map-editor.spec.ts, where tileset3dEnabled
  // defaults to false — is actually rendered here since this spec turns
  // the capability on.
  await page.getByRole("button", { name: "Nouveau", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte avec tileset hébergé");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page
    .getByRole("searchbox", { name: "Rechercher une source de couche" })
    .fill("Ville de test E2E");
  const tilesetRequest = page.waitForResponse("https://core.test/tileset3d/t1/tileset.json");
  await page.getByRole("button", { name: /Ville de test E2E/ }).click();
  const response = await tilesetRequest;
  expect(response.status()).toBe(200);
});
