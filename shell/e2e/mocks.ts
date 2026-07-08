import type { Page } from "@playwright/test";

const ALL = [
  { pk: "1", resourceType: "app", title: "Alpha", abstract: "A", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false },
  { pk: "2", resourceType: "dashboard", title: "Beta", abstract: "B", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false },
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

export async function mockCore(page: Page) {
  const deleted = new Set<string>();
  // Stateful store: keyed by item id, holds the last PUT body per item.
  const savedConfigs = new Map<string, unknown>();
  let published = false;

  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    const scope = url.searchParams.get("scope");
    const visible = ALL.filter((r) => !deleted.has(r.pk));
    // Fixture reality: every item in ALL is owned by "alice"; the mock auth
    // user is "mockuser" (see useAuth.ts's MOCK_STATE) — so scope=mine is
    // always empty for this fixture, matching the pre-migration mock's
    // behavior for the "mockuser" case.
    const items = scope === "mine" ? [] : visible;
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: { id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User", email: null, tenantId: "t-mock" },
    });
  });

  // Scoped to the cœur's host (not "**/items/1"): the shell's own client-side
  // route is also "/items/1" (same path, different origin — localhost:4173
  // vs. https://core.test), so a path-only glob here would also intercept
  // the browser's document navigation to that page and break rendering.
  await page.route("https://core.test/items/1", async (route) => {
    await route.fulfill({ json: ALL[0] });
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
      // App/dashboard creation path — persist the posted config so a later
      // GET (e.g. opening the editor right after creation) reflects it,
      // the same way the PUT handler already does for saves.
      savedConfigs.set("9", body.config);
      await route.fulfill({
        json: { id: "cfg-9", kind: body.config.kind, itemId: "9", version: 1, config: body.config },
      });
    }
  });

  // Same host-scoping rationale as "/items/1" above — the shell also has a
  // client-side route "/items/9".
  await page.route("https://core.test/items/9", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = await route.request().postDataJSON();
      if (typeof body.isPublished === "boolean") published = body.isPublished;
    }
    await route.fulfill({
      json: {
        pk: "9", resourceType: "app", title: "Créée", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: published,
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

  // Feature-serv items for the "villes" collection — a statistics source
  // aggregates these client-side (groupBy region, split annee → 2 series).
  await page.route("**/collections/villes/items.json*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", annee: "2025", pop: 10 } },
          { id: 2, properties: { region: "Nord", annee: "2026", pop: 12 } },
          { id: 3, properties: { region: "Sud", annee: "2025", pop: 5 } },
          { id: 4, properties: { region: "Sud", annee: "2026", pop: 7 } },
        ],
      },
    });
  });

  // Feature-serv items endpoint for the "parcs" collection — filters by the
  // `nom` query param so setFilter can be observed end-to-end.
  await page.route("**/collections/parcs/items.json*", async (route) => {
    const url = new URL(route.request().url());
    const nom = url.searchParams.get("nom");
    const all = [
      { id: 1, properties: { nom: "Parc du Test" } },
      { id: 2, properties: { nom: "Bois Test" } },
    ];
    const features = nom ? all.filter((f) => f.properties.nom === nom) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
}
