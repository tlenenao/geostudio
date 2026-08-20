// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const PORTAL = "https://demo.data.gouv.fr";

test("un admin déclare une source CKAN en référencement, la moissonne, et l'item apparaît au catalogue, cherchable", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1",
          type: "ckan",
          url: PORTAL,
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [
              {
                id: "src-1",
                type: "ckan",
                url: PORTAL,
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
                lastStatus: runCount > 0 ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("pkg-tableur", {
      pk: "ext-ckan-1",
      resourceType: "external",
      title: "Recensement des commerces (CKAN distant)",
      abstract: "",
      owner: "mockuser",
      thumbnailUrl: null,
      date: "2026-01-01",
      configId: null,
      isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "ckan",
      url: PORTAL,
      mode: "reference",
      enabled: true,
    });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Recensement des commerces (CKAN distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  const request = page.waitForRequest(
    (req) => req.url().includes("/items?") && req.url().includes("q=commerces"),
  );
  await page.getByRole("textbox", { name: "Rechercher" }).fill("commerces");
  await request;
  await expect(page.getByText("Recensement des commerces (CKAN distant)")).toBeVisible();
});

test("un admin déclare une source CKAN en copie, la moissonne, et la collection importée est cherchable avec sa couche", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1",
          type: "ckan",
          url: PORTAL,
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [
              {
                id: "src-1",
                type: "ckan",
                url: PORTAL,
                mode: "copy",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: runCount > 0 ? "2026-07-24T10:00:00Z" : null,
                lastStatus: runCount > 0 ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set("pkg-sentiers", {
      pk: "col-item-1",
      resourceType: "map",
      title: "Sentiers de randonnée (CKAN, copie)",
      abstract: "",
      owner: "mockuser",
      thumbnailUrl: null,
      date: "2026-01-01",
      configId: "cfg-col-1",
      isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/items/col-item-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "col-item-1",
        resourceType: "map",
        title: "Sentiers de randonnée (CKAN, copie)",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: "cfg-col-1",
        isPublished: false,
      },
    });
  });

  await page.route("**/configs/by-item/**", async (route) => {
    if (!route.request().url().endsWith("/col-item-1") || route.request().method() !== "GET") {
      return route.fallback();
    }
    await route.fulfill({
      json: {
        id: "cfg-col-1",
        itemId: "col-item-1",
        kind: "map",
        config: {
          kind: "map",
          theme: {},
          dataSources: [],
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [2.3, 48.8], zoom: 10 },
            layers: [
              {
                id: "l1",
                title: "Sentiers de randonnée (CKAN, copie)",
                visible: true,
                kind: "feature",
                url: "https://core.test/collections/ingest_ckan/items",
              },
            ],
          },
        },
      },
    });
  });

  // 1) Déclarer et moissonner la source CKAN en mode copie
  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
  await dialog.getByLabel("Mode").selectOption("copy");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "ckan",
      url: PORTAL,
      mode: "copy",
      enabled: true,
    });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  // 2) La collection importée est cherchable au catalogue
  await page.goto("/");
  await expect(page.getByText("Sentiers de randonnée (CKAN, copie)")).toBeVisible();

  const request = page.waitForRequest(
    (req) => req.url().includes("/items?") && req.url().includes("q=randonn"),
  );
  await page.getByRole("textbox", { name: "Rechercher" }).fill("randonn");
  await request;
  await page.getByRole("button", { name: "Ouvrir" }).click();

  // 3) La carte s'ouvre avec la couche de la collection importée (features accessibles)
  await expect(page).toHaveURL(/\/maps\/col-item-1$/);
  await expect(
    page.getByRole("button", { name: "Retirer Sentiers de randonnée (CKAN, copie)" }),
  ).toBeVisible();
});
