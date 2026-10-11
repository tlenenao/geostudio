// SPDX-License-Identifier: Apache-2.0
// REV-317 : 401 persistant (t02-008) et worker arrêté observable (t02-013).
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("t02-008 : un 401 persistant invite à se reconnecter", async ({ page }) => {
  await mockCore(page);
  await page.route("**/v1/items?*", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/problem+json",
      body: JSON.stringify({ title: "Unauthorized", detail: "invalid token" }),
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: /session a expiré/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Se reconnecter" })).toBeVisible();
});

test("t02-013 : un import en attente derrière un worker arrêté l'indique", async ({ page }) => {
  await mockCore(page);
  await page.route("**/health", (route) =>
    route.fulfill({
      json: { status: "ok", jobsBacklog: { todo: 1, oldestTodoAgeSeconds: 600 } },
    }),
  );
  await page.route("**/uploads/presign", (route) =>
    route.fulfill({ json: { uploadUrl: "https://minio.test/up-w", key: "t/w.geojson" } }),
  );
  await page.route("https://minio.test/up-w", (route) => route.fulfill({ status: 200, body: "" }));
  await page.route("**/uploads", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ json: { jobId: "job-w" } })
      : route.fallback(),
  );
  await page.route("**/uploads/job-w", (route) =>
    route.fulfill({
      json: { status: "pending", errorMessage: null, collectionId: null, itemId: null },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Importer un fichier" }).click();
  await page.getByLabel("Fichier à importer").setInputFiles({
    name: "w.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from('{"type":"FeatureCollection","features":[]}'),
  });
  await page.getByLabel("Titre de la collection").fill("Attente");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: /traitement en arrière-plan/ }),
  ).toBeVisible();
});
