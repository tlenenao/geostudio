// SPDX-License-Identifier: Apache-2.0

import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// D6 : bouton « Annuler l'export » du menu Explorer pendant un export
// asynchrone (202 + sondage). Mêmes conventions que dataset-export.spec.ts :
// l'app est construite via la vraie UI du builder.

async function createApp(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

test("annuler un export asynchrone depuis le menu Explorer", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", (route) =>
    route.fulfill({
      json: {
        collection: "analytics",
        pk: "id",
        geometry: { column: "geometry", type: "Point", srid: 4326 },
        fields: [{ name: "region", type: "string" }],
      },
    }),
  );
  await page.route("**/collections/analytics/items*", (route) =>
    route.fulfill({
      json: { type: "FeatureCollection", features: [{ id: 1, properties: { region: "Nord" } }] },
    }),
  );
  await page.route("**/configs/by-item/dataset-1", (route) =>
    route.fulfill({
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
    }),
  );
  await page.route("**/collections/analytics/export/items*", (route) =>
    route.fulfill({ status: 202, json: { jobId: "j1" } }),
  );
  await page.route("**/collections/analytics/export/jobs/j1", (route) =>
    route.fulfill({ json: { id: "j1", status: "running" } }),
  );
  let cancelCalls = 0;
  await page.route("**/collections/analytics/export/jobs/j1/cancel", (route) => {
    cancelCalls += 1;
    return route.fulfill({ json: { id: "j1", status: "cancelled" } });
  });

  await createApp(page, "Export annulable");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page
    .getByLabel(/Collection de la source/)
    .last()
    .fill("analytics");
  await page
    .getByRole("button", { name: /Promouvoir en jeu de données partagé/ })
    .last()
    .click();
  await expect(page.getByText("Jeu de données partagé actif")).toHaveCount(1);
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  await page.getByRole("button", { name: "Explorer" }).click();
  await page.getByRole("button", { name: "Exporter en CSV" }).click();
  await page.getByRole("button", { name: "Annuler l'export" }).click();
  await expect(page.getByText("Export annulé.")).toBeVisible();
  expect(cancelCalls).toBe(1);
});
