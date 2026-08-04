// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create an arcgis-sourced dataset from a harvested layer, consume it live in an app", async ({ page }) => {
  await mockCore(page);

  await page.route("**/harvest/feature-layers*", async (route) => {
    await route.fulfill({ json: { layers: [{ id: "layer-1", title: "Bâtiments" }] } });
  });

  let datasetCreated: Record<string, unknown> | null = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      datasetCreated = body.config.dataset;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    return route.fallback();
  });

  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-1", columns: {} } },
      },
    });
  });

  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1", resourceType: "dataset", title: "Bâtiments (live)", abstract: "",
        owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset",
        isPublished: false, keywords: [],
      },
    });
  });

  // DataSourceSelect liste les datasets partagés via useItems({type:"dataset"}) :
  // on sniffe le query param en JS plutôt que dans le glob (le "?" d'un glob
  // Playwright est un joker un-caractère, pas le séparateur littéral "?query").
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "dataset") return route.fallback();
    await route.fulfill({
      json: {
        items: [{
          pk: "dataset-1", resourceType: "dataset", title: "Bâtiments (live)", abstract: "",
          owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset",
          isPublished: false,
        }],
        total: 1, page: 1, pageSize: 100,
      },
    });
  });

  await page.route("**/datasets/layer-1/arcgis/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [{ type: "Feature", id: 1, properties: { nom: "Bâtiment A" }, geometry: null }],
        numberMatched: 1, numberReturned: 1, links: [],
      },
    });
  });

  await page.route("**/datasets/layer-1/arcgis/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 1 }] } });
  });

  // 1. Créer le dataset partagé "arcgis" depuis le catalogue, à partir de la
  //    couche déjà moissonnée en mode référence (layer-1, mockée ci-dessus —
  //    le flux de moissonnage lui-même est couvert par harvest-arcgis.spec.ts).
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Type de source").selectOption("arcgis");
  await dialog.getByLabel("Couche ArcGIS").selectOption("layer-1");
  await dialog.getByLabel("Titre").fill("Bâtiments (live)");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  expect(datasetCreated).toEqual({ source: "arcgis", arcgisItemId: "layer-1", columns: {} });

  // 2. Construire une app : Table + Indicateur, tous deux liés au dataset
  //    partagé existant via l'optgroup "Datasets partagés" de DataSourceSelect
  //    — jamais en saisissant une collection, il n'y en a pas pour ce dataset.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Bâtiments live");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption("dataset:dataset-1");

  await page.getByRole("button", { name: "Indicateur" }).click();
  // Le dataset est déjà lié (via la Table) : il apparaît désormais comme une
  // source existante (index 1), plus dans l'optgroup "Datasets partagés".
  await page.getByLabel("Source de données").last().selectOption({ index: 1 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 3. Runtime : la table affiche les entités live, l'indicateur l'agrégat live
  //    — tous deux via le proxy /datasets/layer-1/arcgis/*, jamais /collections/*.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Bâtiment A" })).toBeVisible();
  await expect(page.getByText("1")).toBeVisible();
});
