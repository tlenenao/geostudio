// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// P35.01 : catalogue consultable sans connexion, alimenté par /v1/public/items.
test("catalogue public : liste, filtre par type, ouverture d'un site par son slug", async ({
  page,
}) => {
  await mockCore(page);
  const seen: string[] = [];
  await page.route("https://core.test/v1/public/items?*", async (route) => {
    const url = new URL(route.request().url());
    seen.push(url.searchParams.get("type") ?? "");
    const all = [
      { pk: "s1", resourceType: "site", title: "Portail ouvert", slug: "portail-ouvert" },
      { pk: "m1", resourceType: "map", title: "Carte ouverte" },
    ];
    const type = url.searchParams.get("type");
    const items = (type ? all.filter((i) => i.resourceType === type) : all).map((i) => ({
      abstract: "",
      owner: "alice",
      thumbnailUrl: null,
      date: "",
      configId: null,
      isPublished: true,
      keywords: [],
      license: "",
      language: "fr",
      permissions: { read: true, write: false, delete: false, share: false },
      ...i,
    }));
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/public");
  await expect(page.getByRole("heading", { level: 1, name: "Catalogue public" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Carte ouverte" })).toBeVisible();

  await page.getByLabel("Type").selectOption("map");
  await expect(page.getByRole("heading", { name: "Portail ouvert" })).toHaveCount(0);
  expect(seen).toContain("map");

  await page.getByLabel("Type").selectOption("site");
  await page.getByRole("button", { name: /Ouvrir/ }).click();
  await expect(page).toHaveURL(/\/sites\/portail-ouvert$/);
});

test("AUD-075 : une carte publiée s'ouvre sans connexion (plus d'« introuvable »)", async ({
  page,
}) => {
  await mockCore(page);
  const item = {
    pk: "m1",
    resourceType: "map",
    title: "Carte ouverte",
    abstract: "",
    owner: "alice",
    thumbnailUrl: null,
    date: "",
    configId: "cfg-m",
    isPublished: true,
    keywords: [],
    license: "",
    language: "fr",
    permissions: { read: true, write: false, delete: false, share: false },
  };
  await page.route("https://core.test/v1/public/items/m1", (r) => r.fulfill({ json: item }));
  await page.route("https://core.test/v1/public/configs/by-item/m1", (r) =>
    r.fulfill({
      json: {
        id: "cfg-m",
        itemId: "m1",
        kind: "map",
        version: 1,
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://core.test/style.json" },
            view: { center: [2.4, 46.6], zoom: 5 },
            layers: [],
          },
        },
      },
    }),
  );
  await page.goto("/public/items/m1");
  await expect(page.getByRole("heading", { level: 1, name: "Carte ouverte" })).toBeAttached();
  await expect(page.getByText(/introuvable/i)).toHaveCount(0);
});
