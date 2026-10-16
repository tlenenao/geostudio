// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// REV-119 / GAP-25 : métriques nommées d'un dataset, créées dans l'éditeur de
// dataset puis enregistrées dans la config (PUT /configs/by-item/{id}).
test("créer une métrique nommée sur un dataset et l'enregistrer", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents",
        pk: "id",
        geometry: null,
        fields: [{ name: "montant", type: "number" }],
      },
    });
  });
  let saved: { dataset?: { metrics?: unknown } } | null = null;
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      saved = route.request().postDataJSON();
      await route.fulfill({ json: { version: 2 } });
      return;
    }
    await route.fulfill({
      json: {
        id: "cfg-dataset",
        itemId: "dataset-1",
        kind: "dataset",
        version: 1,
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "incidents", columns: {}, metrics: {} },
        },
      },
    });
  });
  await page.route("https://core.test/v1/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1",
        resourceType: "dataset",
        title: "Incidents partagés",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: "cfg-dataset",
        isPublished: false,
        keywords: [],
        permissions: { read: true, write: true, delete: true, share: true },
      },
    });
  });
  await page.route("**/datasets/dataset-1/alerts", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/datasets/dataset-1/edit");

  await page.getByLabel("Clé de la nouvelle métrique").fill("Mauvaise-Clé");
  await page.getByRole("button", { name: "Ajouter une métrique" }).click();
  await expect(page.getByText(/Clé invalide/)).toBeVisible();

  await page.getByLabel("Clé de la nouvelle métrique").fill("recettes_total");
  await page.getByRole("button", { name: "Ajouter une métrique" }).click();
  await page.getByLabel("Agrégation de la métrique recettes_total").selectOption("sum");
  await page.getByLabel("Champ de la métrique recettes_total").selectOption("montant");
  await page.getByLabel("Libellé de la métrique recettes_total").fill("Recettes totales");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await expect
    .poll(() => saved?.dataset?.metrics)
    .toMatchObject({
      recettes_total: { agg: "sum", field: "montant", label: "Recettes totales" },
    });
});
