// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer une règle d'alerte et voir son état firing sur DatasetEditPage", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [{
          id: "incidents", title: "Incidents", description: "", tableName: "incidents", isPublic: true, editable: true,
          geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 3, owner: "mockuser",
        }],
      },
    });
  });
  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: { collection: "incidents", pk: "id", geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "category", type: "string" }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "incidents", columns: {} } },
      },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Incidents partagés", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });
  await page.route("**/datasets/dataset-1/alerts", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: [{ itemId: "alert-1", title: "Trop d'incidents" }] });
  });
  await page.route("**/alerts/alert-1/evaluations", async (route) => {
    await route.fulfill({
      json: [{ id: "eval-1", value: 3, state: "firing", transitioned: true, error: null, createdAt: "2026-08-07T00:00:00Z" }],
    });
  });
  let createdAlertConfig: unknown = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    if (body.config.kind === "alert") {
      createdAlertConfig = body;
      await route.fulfill({ status: 201, json: { id: "cfg-alert", kind: "alert", itemId: "alert-1" } });
      return;
    }
    return route.fallback();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("incidents");
  await dialog.getByLabel("Titre").fill("Incidents partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);

  await page.getByLabel("Nom de la règle").fill("Trop d'incidents");
  await page.getByLabel("Condition (expression)").fill("value > 2");
  await page.getByLabel("URL du webhook").fill("https://example.test/hook");
  await page.getByRole("button", { name: "Créer la règle" }).click();

  await expect(page.getByText("Trop d'incidents")).toBeVisible();
  await expect(page.getByText(/firing/i)).toBeVisible();
  expect(createdAlertConfig).not.toBeNull();
  // Vérifie que le POST /configs porte bien les valeurs saisies dans le
  // formulaire, pas seulement qu'un POST a eu lieu (cf. itemClient.ts's
  // createAlertRuleItem: { title, config: { version, kind, alert } }).
  expect(createdAlertConfig).toMatchObject({
    title: "Trop d'incidents",
    config: {
      kind: "alert",
      alert: {
        condition: { expr: "value > 2" },
        channels: [{ kind: "webhook", url: "https://example.test/hook" }],
      },
    },
  });
});
