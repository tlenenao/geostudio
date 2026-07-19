// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un admin déclare une source STAC, la moissonne, et un re-moissonnage ne duplique pas", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  let harvestedItem: Record<string, unknown> | null = null;

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "stac", url: "https://stac.example.com/collections",
          mode: "reference", enabled: true, intervalMinutes: null,
          lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "stac", url: "https://stac.example.com/collections",
              mode: "reference", enabled: true, intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-19T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedItem = {
      pk: "ext-1", resourceType: "external", title: "Bâtiments (STAC distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    };
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  // Host-scoped: le shell a lui-même une route client "/items" (catalogue) —
  // un glob non scopé casserait la navigation (même rationale que
  // "/items/1"/"/items/9" ailleurs dans cette suite).
  await page.route("https://core.test/items*", async (route) => {
    const items = harvestedItem ? [harvestedItem] : [];
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await expect(page.getByRole("link", { name: "Moissonnage" })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill("https://stac.example.com/collections");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "stac", url: "https://stac.example.com/collections", mode: "reference", enabled: true,
  });
  await expect(page.getByText("https://stac.example.com/collections")).toBeVisible();

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Bâtiments (STAC distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(2);
  await page.goto("/");
  await expect(page.getByText("Bâtiments (STAC distant)")).toHaveCount(1);
});
