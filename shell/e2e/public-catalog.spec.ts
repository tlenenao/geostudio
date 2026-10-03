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
