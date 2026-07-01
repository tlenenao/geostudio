import type { Page } from "@playwright/test";

const ALL = [
  { pk: "1", resource_type: "app", title: "Alpha", abstract: "A", owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
  { pk: "2", resource_type: "dashboard", title: "Beta", abstract: "B", owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
];

export async function mockGeoNode(page: Page) {
  const deleted = new Set<string>();

  await page.route("**/api/v2/resources*", async (route) => {
    const resources = ALL.filter((r) => !deleted.has(r.pk));
    await route.fulfill({
      json: { total: resources.length, page: 1, page_size: 12, resources },
    });
  });

  await page.route("**/api/v2/resources/1", async (route) => {
    await route.fulfill({ json: { resource: ALL[0] } });
  });

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      json: { id: "cfg-9", kind: "app", itemId: "9", version: 1, config: {} },
    });
  });

  await page.route("**/api/v2/resources/9", async (route) => {
    await route.fulfill({
      json: {
        resource: { pk: "9", resource_type: "app", title: "Créée", abstract: "",
          owner: { username: "mockuser" }, thumbnail_url: null, date: "2026-01-01" },
      },
    });
  });

  await page.route("**/configs/by-item/**", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    const pk = route.request().url().split("/").pop() ?? "";
    deleted.add(pk);
    await route.fulfill({ status: 204, body: "" });
  });
}
