// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCollection, mockCore } from "./mocks";

// REV-309 : GET /collections plafonne à 100 résultats ; au-delà, la collection
// de base de la requête visuelle se trouve par la recherche ?q= côté cœur.
const ALL = Array.from({ length: 150 }, (_, i) =>
  mockCollection({
    id: `zone-${i + 1}`,
    title: `Zone ${i + 1}`,
    tableName: `zone_${i + 1}`,
    isPublic: true,
    geometryType: null,
    srid: null,
    permissions: { read: true, write: true, delete: false, share: false },
    featureCount: 1,
  }),
);

test("plus de 100 collections : la base se trouve par la recherche", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
  });
  await page.route("https://core.test/v1/collections*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q")?.toLowerCase();
    const limit = Number(url.searchParams.get("limit") ?? 100);
    const rows = (q ? ALL.filter((c) => c.title.toLowerCase().includes(q)) : ALL).slice(0, limit);
    await route.fulfill({ json: { collections: rows } });
  });

  await page.goto("/datasets/visual-query/new");
  await expect(page.getByRole("option", { name: "Zone 100", exact: true })).toBeAttached();
  await expect(page.getByRole("option", { name: "Zone 150", exact: true })).toHaveCount(0);

  await page.getByLabel("Rechercher parmi les collections").fill("Zone 150");
  await expect(page.getByRole("option", { name: "Zone 150", exact: true })).toBeAttached();
  await page.getByLabel("Collection de base").selectOption("zone-150");
  await expect(page.getByLabel("Collection de base")).toHaveValue("zone-150");
});
