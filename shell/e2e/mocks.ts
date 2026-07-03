import type { Page } from "@playwright/test";

const ALL = [
  { pk: "1", resource_type: "app", title: "Alpha", abstract: "A", owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
  { pk: "2", resource_type: "dashboard", title: "Beta", abstract: "B", owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
];

const DEFAULT_MAP_CONFIG = {
  kind: "map",
  map: {
    basemap: { style: "https://demotiles.maplibre.org/style.json" },
    view: { center: [2.4, 46.6], zoom: 5 },
    layers: [],
  },
} as const;

const DEFAULT_APP_CONFIG = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
} as const;

export async function mockGeoNode(page: Page) {
  const deleted = new Set<string>();
  // Stateful store: keyed by item id, holds the last PUT body per item.
  const savedConfigs = new Map<string, unknown>();

  await page.route("**/api/v2/resources*", async (route) => {
    const url = new URL(route.request().url());
    const owner = url.searchParams.get("filter{owner.username.in}");
    const visible = ALL.filter((r) => !deleted.has(r.pk));
    // Alpha/Beta are owned by "alice"; the mock user is "mockuser".
    const resources = owner ? visible.filter((r) => r.owner.username === owner) : visible;
    await route.fulfill({
      json: { total: resources.length, page: 1, page_size: 12, resources },
    });
  });

  await page.route("**/api/v2/users/me", async (route) => {
    await route.fulfill({
      json: { user: { username: "mockuser", first_name: "Mock", last_name: "User" } },
    });
  });

  await page.route("**/api/v2/resources/1", async (route) => {
    await route.fulfill({ json: { resource: ALL[0] } });
  });

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "map") {
      // Map creation path — return itemId "77" so the test lands on /maps/77.
      await route.fulfill({
        status: 201,
        json: { id: "cfg-1", kind: "map", itemId: "77" },
      });
    } else {
      // App/dashboard creation path — keep the existing response unchanged.
      await route.fulfill({
        json: { id: "cfg-9", kind: "app", itemId: "9", version: 1, config: {} },
      });
    }
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
    const method = route.request().method();
    const itemId = route.request().url().split("/").pop() ?? "";

    if (method === "DELETE") {
      deleted.add(itemId);
      await route.fulfill({ status: 204, body: "" });
    } else if (method === "GET") {
      if (itemId === "77") {
        // Map item — return stored config if present, else default map config.
        const stored = savedConfigs.get("77");
        await route.fulfill({
          json: {
            id: "cfg-1",
            itemId: "77",
            kind: "map",
            config: stored ?? DEFAULT_MAP_CONFIG,
          },
        });
      } else {
        // App/dashboard items (9, 1, …) — return stored config if present, else empty app config.
        const stored = savedConfigs.get(itemId);
        await route.fulfill({
          json: {
            id: `cfg-${itemId}`,
            itemId,
            kind: "app",
            config: stored ?? DEFAULT_APP_CONFIG,
          },
        });
      }
    } else if (method === "PUT") {
      const body = await route.request().postDataJSON();
      if (itemId === "77") {
        savedConfigs.set("77", body);
        await route.fulfill({
          json: {
            id: "cfg-1",
            itemId: "77",
            kind: "map",
            config: { kind: "map", map: body.map },
          },
        });
      } else {
        // App/dashboard items — echo the full PUT body back as the config, store for future GETs.
        savedConfigs.set(itemId, body);
        await route.fulfill({
          json: { id: `cfg-${itemId}`, itemId, kind: "app", config: body },
        });
      }
    } else {
      await route.fallback();
    }
  });

  // Martin vector-tile catalog — exposes the "Communes" layer source.
  await page.route("**/catalog", async (route) => {
    await route.fulfill({
      json: { tiles: { communes: { description: "Communes" } } },
    });
  });

  // Feature-serv OGC API collections — return empty list (no feature layers needed).
  await page.route("**/collections.json", async (route) => {
    await route.fulfill({
      json: { collections: [] },
    });
  });
}
