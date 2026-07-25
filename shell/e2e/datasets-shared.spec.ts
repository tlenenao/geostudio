// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create a dataset, edit a column label, then promote an app's inline source", async ({ page }) => {
  await mockCore(page);

  let datasetCreated = false;
  let datasetColumns: Record<string, unknown> = {};
  let promotePostedCollectionId: string | null = null;

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          { id: "parcs", title: "Parcs", description: "", tableName: "parcs", isPublic: true, editable: true, geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 3, owner: "alice" },
        ],
      },
    });
  });

  await page.route("**/collections/parcs/schema", async (route) => {
    await route.fulfill({
      json: { collection: "parcs", pk: "id", geometry: null, fields: [{ name: "nom", type: "string", required: true }] },
    });
  });

  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      const body = await route.request().postDataJSON();
      datasetColumns = body.dataset.columns;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: body.dataset } });
      return;
    }
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: datasetColumns } },
      },
    });
  });

  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Parcs partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      datasetCreated = true;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    return route.fallback();
  });

  // 1. Créer un Dataset partagé depuis le catalogue.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("parcs");
  await dialog.getByLabel("Titre").fill("Parcs partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  expect(datasetCreated).toBe(true);

  // 2. Éditer le libellé d'une colonne et sauvegarder.
  await page.getByLabel("Libellé de nom").fill("Nom du parc");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();
  await expect.poll(() => datasetColumns).toMatchObject({ nom: { label: "Nom du parc" } });

  // 3. Promouvoir une source inline depuis un nouvel App.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Carte des parcs");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      promotePostedCollectionId = body.config.dataset.collectionId;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset-2", kind: "dataset", itemId: "dataset-2" } });
      return;
    }
    return route.fallback();
  });

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).click();

  await expect(page.getByText("Dataset partagé actif")).toBeVisible();
  expect(promotePostedCollectionId).toBe("parcs");
});
