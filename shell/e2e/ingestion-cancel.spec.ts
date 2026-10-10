// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// D6 : bouton « Annuler l'import » pendant le suivi d'un import de fichier.
test("annuler un import en attente ferme le tiroir et confirme par un toast", async ({ page }) => {
  await mockCore(page);
  await page.route("**/uploads/presign", (route) =>
    route.fulfill({ json: { uploadUrl: "https://minio.test/up-c", key: "t/c-villes.geojson" } }),
  );
  await page.route("https://minio.test/up-c", (route) => route.fulfill({ status: 200, body: "" }));
  await page.route("**/uploads", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({ json: { jobId: "job-c" } });
  });
  await page.route("**/uploads/job-c", (route) =>
    route.fulfill({
      json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
    }),
  );
  let cancelCalls = 0;
  await page.route("**/uploads/job-c/cancel", (route) => {
    cancelCalls += 1;
    return route.fulfill({
      json: { status: "cancelled", errorMessage: null, collectionId: null, itemId: null },
    });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "villes.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from('{"type":"FeatureCollection","features":[]}'),
  });
  await page.getByLabel("Titre de la collection").fill("Villes");
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page.getByRole("button", { name: "Annuler l'import" }).click();
  await expect(page.getByText("Import annulé.")).toBeVisible();
  await expect(page.getByRole("dialog")).toBeHidden();
  expect(cancelCalls).toBe(1);
});
