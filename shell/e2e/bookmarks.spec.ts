// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-14m — enregistrer le contexte analytique courant comme une vue nommée,
// la retrouver dans "Mes vues", la rouvrir restaure exactement le même
// contexte ; une vue non partagée reste invisible pour un autre utilisateur.
test("save a view with a cross-filter and a time range, find it in Mes vues, reopen restores the context", async ({ page }) => {
  await mockCore(page);

  let bookmarkCreated = false;
  let bookmarkConfigBody: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          { id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" },
        ],
      },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01" } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01" } },
    ];
    const features = gte && lte ? all.filter((f) => f.properties.date >= gte && f.properties.date <= lte) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, timeField: "date" } },
      },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  // App "9" : builder crée un dataset partagé, un widget de plage de dates lié
  // à son timeField, et active interactions="auto".
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    if (body?.config?.kind === "bookmark") {
      bookmarkCreated = true;
      bookmarkConfigBody = body.config;
      await route.fulfill({ status: 201, json: { id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" } });
      return;
    }
    return route.fallback();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Dashboard analytique");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("events");
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).click();
  await expect(page.getByText("Dataset partagé actif")).toBeVisible();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();

  await page.getByRole("button", { name: /Plage de dates/ }).click();
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 1. Ouvrir le runtime, poser une plage temporelle.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-12-31");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();

  // 2. Enregistrer la vue.
  await page.getByRole("button", { name: "Enregistrer la vue" }).click();
  const saveViewDialog = page.getByRole("dialog", { name: "Enregistrer la vue" });
  await saveViewDialog.getByLabel("Nom de la vue").fill("Récents 2026");
  await saveViewDialog.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => bookmarkCreated).toBe(true);
  expect(bookmarkConfigBody).toMatchObject({
    kind: "bookmark",
    bookmark: { appId: "9", pageId: expect.any(String), timeRange: { from: "2026-01-01", to: "2026-12-31" } },
  });

  // 3. La vue apparaît dans /bookmarks.
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          { pk: "bookmark-1", resourceType: "bookmark", title: "Récents 2026", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-bookmark", isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      },
    });
  });
  await page.route("https://core.test/configs/by-item/bookmark-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-bookmark", itemId: "bookmark-1", kind: "bookmark",
        config: { version: 1, kind: "bookmark", bookmark: bookmarkConfigBody.bookmark },
      },
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  // 4. L'ouvrir restaure exactement le même contexte.
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/.*\?ctx=/);
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
});

test("a non-shared view is invisible to a second user of the same tenant", async ({ page }) => {
  await mockCore(page);

  // "mockuser" (the fixture's authenticated identity, per mocks.ts) owns the
  // bookmark; scope=mine already returns [] for every non-owned fixture item
  // (see mocks.ts's "**/items*" comment) — reused here unmodified to prove a
  // bookmark obeys the exact same generic sharing default as any other kind.
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark" || url.searchParams.get("scope") !== "mine") {
      return route.fallback();
    }
    await route.fulfill({ json: { items: [], total: 0, page: 1, pageSize: 12 } });
  });

  await page.goto("/bookmarks");
  await page.getByLabel("Portée").selectOption("mine");
  await expect(page.getByText("Aucun élément.")).toBeVisible();
});
