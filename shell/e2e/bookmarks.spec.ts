// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCollection, mockCore } from "./mocks";

// SP-14m — enregistrer le contexte analytique courant comme une vue nommée,
// la retrouver dans "Mes vues", la rouvrir restaure exactement le même
// contexte ; une vue non partagée reste invisible pour un autre utilisateur.
test("save a view with a cross-filter and a time range, find it in Mes vues, reopen restores the context", async ({
  page,
}) => {
  await mockCore(page);

  let bookmarkCreated = false;
  let bookmarkConfigBody: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          mockCollection({
            id: "events",
            title: "Événements",
            tableName: "events",
            isPublic: true,
            geometryType: null,
            srid: null,
            permissions: { read: true, write: true, delete: false, share: false },
            featureCount: 2,
          }),
        ],
      },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "events",
        pk: "id",
        geometry: null,
        fields: [
          { name: "nom", type: "string" },
          { name: "date", type: "string" },
          { name: "score", type: "number" },
        ],
      },
    });
  });
  // "score" (numérique) porte le cross-filter : le curseur ("Curseur" widget)
  // le filtre par plage (score__gte/score__lte), en plus de la plage
  // temporelle sur "date" déjà exercée par ce test.
  await page.route("**/collections/events/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const scoreGte = url.searchParams.get("score__gte");
    const scoreLte = url.searchParams.get("score__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01", score: 10 } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01", score: 90 } },
    ];
    const features = all.filter((f) => {
      if (gte && f.properties.date < gte) return false;
      if (lte && f.properties.date > lte) return false;
      if (scoreGte && f.properties.score < Number(scoreGte)) return false;
      if (scoreLte && f.properties.score > Number(scoreLte)) return false;
      return true;
    });
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  // Bornes min/max du curseur (requête statistics du widget sliderFilter).
  await page.route("**/collections/events/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "group", rows: [{ group: "Total", min: 10, max: 90 }] },
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
          dataset: { source: "collection", collectionId: "events", columns: {}, timeField: "date" },
        },
      },
    });
  });
  await page.route("https://core.test/v1/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1",
        resourceType: "dataset",
        title: "Événements partagés",
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

  // App "9" : builder crée un dataset partagé, un widget de plage de dates lié
  // à son timeField, et active interactions="auto".
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      await route.fulfill({
        status: 201,
        json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" },
      });
      return;
    }
    if (body?.config?.kind === "bookmark") {
      bookmarkCreated = true;
      bookmarkConfigBody = body.config;
      await route.fulfill({
        status: 201,
        json: { id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" },
      });
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

  // Deux sources sur "events", promues chacune en dataset partagé (même
  // datasetId "dataset-1" côté mock, cf. le commentaire de
  // analytics-context.spec.ts) : le curseur origine le cross-filter depuis la
  // première, la table le lit sur la seconde. derivePatch()
  // (lib/analyticsPatch.ts) n'applique un cross-filter qu'aux sources dont
  // l'id diffère de son originSourceId — lier curseur et table à la même
  // source ne l'exercerait donc jamais.
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page
    .getByLabel(/Collection de la source/)
    .last()
    .fill("events");
  await page
    .getByRole("button", { name: /Promouvoir en dataset partagé/ })
    .last()
    .click();
  await expect(page.getByText("Dataset partagé actif")).toHaveCount(1);

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page
    .getByLabel(/Collection de la source/)
    .last()
    .fill("events");
  await page
    .getByRole("button", { name: /Promouvoir en dataset partagé/ })
    .last()
    .click();
  await expect(page.getByText("Dataset partagé actif")).toHaveCount(2);

  await page.getByLabel("Interactions automatiques (cross-filter)").check();

  await page.getByRole("button", { name: /Plage de dates/ }).click();

  await page.getByRole("button", { name: "Curseur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du curseur").fill("score");
  await page.getByLabel("Libellé du curseur").fill("Score");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 1. Ouvrir le runtime, poser un cross-filter (curseur) puis une plage
  // temporelle.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();

  const minInput = page.getByLabel("Borne minimale");
  await expect(minInput).toHaveValue("10");
  const crossFilteredReq = page.waitForRequest(
    (r) => r.url().includes("/collections/events/items") && r.url().includes("score__gte=50"),
  );
  await minInput.evaluate((el: HTMLInputElement) => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )!.set!;
    setter.call(el, "50");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await crossFilteredReq;
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();

  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-12-31");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();

  // 2. Enregistrer la vue.
  await page.getByRole("button", { name: "Enregistrer la vue" }).click();
  const saveViewDialog = page.getByRole("dialog", { name: "Enregistrer la vue" });
  await saveViewDialog.getByLabel("Nom de la vue").fill("Récents 2026");
  await saveViewDialog.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => bookmarkCreated).toBe(true);
  expect(bookmarkConfigBody).toMatchObject({
    kind: "bookmark",
    bookmark: {
      appId: "9",
      pageId: expect.any(String),
      timeRange: { from: "2026-01-01", to: "2026-12-31" },
      crossFilter: {
        "dataset-1": {
          field: "score",
          value: { from: "50", to: "90" },
          originSourceId: expect.any(String),
        },
      },
    },
  });

  // 3. La vue apparaît dans /bookmarks.
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          {
            pk: "bookmark-1",
            resourceType: "bookmark",
            title: "Récents 2026",
            abstract: "",
            owner: "mockuser",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: "cfg-bookmark",
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      },
    });
  });
  await page.route("https://core.test/v1/configs/by-item/bookmark-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-bookmark",
        itemId: "bookmark-1",
        kind: "bookmark",
        config: { version: 1, kind: "bookmark", bookmark: bookmarkConfigBody.bookmark },
      },
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  // 4. L'ouvrir restaure exactement le même contexte — plage temporelle et
  // cross-filter, pas seulement la première.
  const reopenedReq = page.waitForRequest(
    (r) =>
      r.url().includes("/collections/events/items") &&
      r.url().includes("score__gte=50") &&
      r.url().includes("date__gte=2026-01-01"),
  );
  await page.getByRole("button", { name: "Ouvrir" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/.*\?ctx=/);
  await reopenedReq;
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
  await expect(page.getByText("Score (50 – 90)")).toBeVisible();
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
