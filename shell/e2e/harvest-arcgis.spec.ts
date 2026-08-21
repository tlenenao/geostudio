// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const FS = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer";

test("un admin déclare une source ArcGIS, la moissonne, et un re-moissonnage ne duplique pas", async ({
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
  // Magasin honnête, keyé par id externe (pk) : le handler "/run" UPSERT
  // dedans plutôt que de réassigner un objet unique — même patron que
  // harvest-stac.spec.ts, l'assertion sans-doublon reste non tautologique.
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1",
          type: "arcgis",
          url: FS,
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
                type: "arcgis",
                url: FS,
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: runCount > 0 ? "2026-07-22T10:00:00Z" : null,
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
    harvestedById.set(`${FS}/0`, {
      pk: `${FS}/0`,
      resourceType: "external",
      title: "Bâtiments (ArcGIS distant)",
      abstract: "",
      owner: "mockuser",
      thumbnailUrl: null,
      date: "2026-01-01",
      configId: null,
      isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  // Host-scoped: le shell a lui-même une route client "/items" (catalogue) —
  // un glob non scopé casserait la navigation (même rationale que
  // "/items/1"/"/items/9" ailleurs dans cette suite).
  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await expect(page.getByRole("link", { name: "Moissonnage" })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(FS);
  await dialog.getByLabel("Type").selectOption("arcgis");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "arcgis",
      url: FS,
      mode: "reference",
      enabled: true,
    });
  await expect(page.getByText(FS)).toBeVisible();

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Bâtiments (ArcGIS distant)")).toBeVisible();
  // .last(), not the default first match: the catalog's "Type" <select>
  // (SP-23, chantier 4.15) always renders an <option value="external">Externe</option>
  // ahead of the item grid in DOM order — .last() lands on the item's own
  // badge instead.
  await expect(page.getByText("Externe").last()).toBeVisible();

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(2);
  await page.goto("/");
  // Magasin mocké keyé par external_id : re-lancer la même source garde le
  // catalogue à une seule carte (assertion sans-doublon non tautologique).
  await expect(page.getByText("Bâtiments (ArcGIS distant)")).toHaveCount(1);
});
