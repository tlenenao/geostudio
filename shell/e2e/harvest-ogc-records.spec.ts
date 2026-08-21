// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const OGC_URL = "https://records.example.com/api";

test("un admin déclare une source OGC API - Records, la moissonne, et l'item apparaît au catalogue, cherchable", async ({
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
          type: "ogc-records",
          url: OGC_URL,
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
                type: "ogc-records",
                url: OGC_URL,
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
    harvestedById.set("rec-1", {
      pk: "rec-1",
      resourceType: "external",
      title: "Sentiers de randonnée (OGC Records distant)",
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
  await dialog.getByLabel("URL").fill(OGC_URL);
  await dialog.getByLabel("Type").selectOption("ogc-records");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "ogc-records",
      url: OGC_URL,
      mode: "reference",
      enabled: true,
    });

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Sentiers de randonnée (OGC Records distant)")).toBeVisible();
  // .last(), not the default first match: the catalog's "Type" <select>
  // (SP-23, chantier 4.15) always renders an <option value="external">Externe</option>
  // ahead of the item grid in DOM order — .last() lands on the item's own
  // badge instead.
  await expect(page.getByText("Externe").last()).toBeVisible();

  const request = page.waitForRequest(
    (req) => req.url().includes("/items?") && req.url().includes("q=Sentiers"),
  );
  await page.getByRole("textbox", { name: "Rechercher" }).fill("Sentiers");
  await request;
  await expect(page.getByText("Sentiers de randonnée (OGC Records distant)")).toBeVisible();
});
