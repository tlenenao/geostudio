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

  // Site portal (SP-16a) — state for the created-then-published site.
  let siteSlug: string | null = null;
  let sitePublished = false;
  const SITE_APP_CONFIG = {
    version: 1, kind: "site", theme: {}, dataSources: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bienvenue sur le portail" } },
    ] },
    messages: [], pages: [],
  } as const;

  // Content widgets (SP-16b) — a second published item, distinct from the
  // site itself, for the Gallery to list and link to.
  const GALLERY_ITEM = {
    pk: "8", resourceType: "app", title: "Carte des risques", abstract: "Resume des risques",
    owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: null,
    isPublished: true, keywords: ["risques"],
  } as const;
  const GALLERY_ITEM_CONFIG = {
    version: 1, kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Detail de l'article" } },
    ] },
  } as const;

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
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: false,
      },
    });
  });

  // Instance info (SP-9 démo lecture seule) — AppLayout appelle
  // GET /instance sans condition sur chaque page via useInstanceInfo().
  // Défaut readOnly: false pour que toute spec pré-existante (qui ne
  // surcharge jamais cette route) se comporte exactement comme avant.
  // La spec dédiée au mode lecture seule surcharge cette route elle-même.
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false } });
  });

  // Extensions registry (SP-8b) — AppBuilderPage/AppRuntimePage call
  // GET /extensions unconditionally on mount; default to none active so
  // every pre-existing spec (which never registers an extension) behaves
  // exactly as before. Specs that need one or more active extensions
  // override this route themselves.
  //
  // Host-scoped (not "**/extensions*"): the shell's own client-side route
  // "/admin/extensions" (SP-8c admin page) also matches a path-only glob
  // ending in "extensions*" — that would intercept the browser's document
  // navigation to that page and break rendering, same rationale as
  // "/items/1"/"/items/9" below.
  await page.route("https://core.test/extensions*", async (route) => {
    await route.fulfill({ json: { extensions: [] } });
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
    if (body?.config?.kind === "site") {
      siteSlug = body.slug ?? "mon-portail";
      await route.fulfill({ status: 201, json: { id: "cfg-site", kind: "site", itemId: "site-1" } });
    } else if (body?.config?.kind === "map") {
      // Map creation path — return itemId "77" so the test lands on /maps/77.
      await route.fulfill({
        status: 201,
        json: { id: "cfg-1", kind: "map", itemId: "77" },
      });
    } else if (body?.config?.kind === "dataset") {
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
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
    // .split("?")[0] before .pop(): AppRuntimePage appends "?mode=runtime"
    // (SP-10a), which would otherwise leak into the id and miss every
    // savedConfigs lookup keyed by the plain item id.
    const itemId = route.request().url().split("?")[0].split("/").pop() ?? "";

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

  // Cœur OGC API collections — filtered by `q` when present (LayerPicker
  // search, Task 11/12); default `q=null` → `[]`, matching the pre-Task-12
  // behavior for every spec that never searches the LayerPicker.
  const ALL_COLLECTIONS = [
    { id: "communes", title: "Communes", featureCount: 12 },
    { id: "incidents", title: "Incidents voirie", featureCount: 3 },
  ];

  // Host-scoped (not "**/collections*"): the shell's own client-side route
  // "/admin/collections" (SP-9 admin page) also matches a path-only glob
  // ending in "collections*" — that would intercept the browser's document
  // navigation to that page and break rendering, same rationale as
  // "**/extensions*" above and "/items/1"/"/items/9" below.
  //
  // Trailing "*" is required: the LayerPicker search issues
  // "/collections?q=…", and a bare pattern anchored at the end of the URL
  // does not match once a query string is appended — it would silently fall
  // through to the real network in the browser. The "*" only matches
  // non-"/" characters, so it still can't swallow the more specific
  // "**/collections/villes/items*" etc. routes below.
  await page.route("https://core.test/collections*", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const collections = q
      ? ALL_COLLECTIONS.filter((c) => c.title.toLowerCase().includes(q.toLowerCase()))
      : [];
    await route.fulfill({ json: { collections } });
  });

  // Cœur couches raster externes (SP-12e) — LayerPicker 3ᵉ source. Défaut vide :
  // toute spec pré-existante (qui ne moissonne aucune couche raster) se comporte
  // comme avant. La spec harvest-wms surcharge cette route.
  await page.route("https://core.test/harvest/layers*", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const all = [] as { id: string; title: string; kind: "raster"; tilesUrl: string }[];
    const layers = q ? all.filter((l) => l.title.toLowerCase().includes(q.toLowerCase())) : all;
    await route.fulfill({ json: { layers } });
  });

  // Cœur items for the "villes" collection — used by regular (non-statistics) data sources.
  await page.route("**/collections/villes/items*", async (route) => {
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

  // POST /collections/villes/aggregate (SP-11b) — le cœur agrège désormais
  // côté serveur (DuckDB) ; le mock renvoie directement la forme large déjà
  // pivotée (groupBy region, split annee → 2 series), même contrat que
  // l'ancienne agrégation client qu'il remplace.
  await page.route("**/collections/villes/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: "region",
        rows: [
          { region: "Nord", "2025": 10, "2026": 12 },
          { region: "Sud", "2025": 5, "2026": 7 },
        ],
      },
    });
  });

  // Cœur items endpoint for the "parcs" collection — filters by the `nom`
  // query param so setFilter can be observed end-to-end.
  await page.route("**/collections/parcs/items*", async (route) => {
    const url = new URL(route.request().url());
    const nom = url.searchParams.get("nom");
    const all = [
      { id: 1, properties: { nom: "Parc du Test" } },
      { id: 2, properties: { nom: "Bois Test" } },
    ];
    const features = nom ? all.filter((f) => f.properties.nom === nom) : all;
    await route.fulfill({
      headers: { "Content-Disposition": 'attachment; filename="parcs.geojson"' },
      json: { type: "FeatureCollection", features },
    });
  });

  // Collection detail + schema for "parcs" (SP-16c) — a genuinely public
  // collection (unlike "incidents", kept private above for the incident-form
  // scenario), reusing the existing "**/collections/parcs/items*" fixture.
  await page.route("**/collections/parcs", async (route) => {
    await route.fulfill({
      json: {
        id: "parcs", title: "Parcs", description: "Parcs publics de la ville", tableName: "parcs",
        isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
        canWrite: false, featureCount: 2,
      },
    });
  });

  await page.route("**/collections/parcs/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "parcs", pk: "id", geometry: null,
        fields: [{ name: "nom", type: "string", required: true }],
      },
    });
  });

  // Collection "incidents" — schéma introspecté, permission d'écriture, et
  // CRUD complet avec état en mémoire (pour que la Table reflète les écritures
  // du Formulaire au fil du scénario "déclarer un incident").
  const incidentRecords = new Map<string, { properties: Record<string, unknown>; geometry: unknown }>();
  let nextIncidentId = 1;

  await page.route("**/collections/incidents", async (route) => {
    await route.fulfill({
      json: {
        id: "incidents", title: "Incidents", description: "", tableName: "incidents",
        isPublic: false, editable: true, geometryType: null, srid: null, pkColumn: "id",
        canWrite: true,
      },
    });
  });

  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents", pk: "id", geometry: null,
        fields: [
          { name: "titre", type: "string", required: true, maxLength: 120 },
          { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
        ],
      },
    });
  });

  await page.route("**/collections/incidents/items*", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        json: {
          type: "FeatureCollection",
          features: [...incidentRecords.entries()].map(([id, r]) => ({
            type: "Feature", id: Number(id), properties: r.properties, geometry: r.geometry,
          })),
        },
      });
    } else if (method === "POST") {
      const body = await route.request().postDataJSON();
      const id = String(nextIncidentId++);
      incidentRecords.set(id, { properties: body.properties, geometry: body.geometry });
      await route.fulfill({ status: 201, json: { id: Number(id) } });
    } else {
      await route.fallback();
    }
  });

  await page.route("**/collections/incidents/items/*", async (route) => {
    const method = route.request().method();
    const id = route.request().url().split("/").pop() ?? "";
    if (method === "PUT") {
      const body = await route.request().postDataJSON();
      incidentRecords.set(id, { properties: body.properties, geometry: body.geometry });
      await route.fulfill({ status: 204, body: "" });
    } else if (method === "DELETE") {
      incidentRecords.delete(id);
      await route.fulfill({ status: 204, body: "" });
    } else {
      await route.fallback();
    }
  });

  // Site portal (SP-16a) — appended last so these precise routes win over
  // the generic "**/items*" / "**/configs" / "**/configs/by-item/**"
  // handlers registered above (Playwright runs the last-registered matching
  // handler first).

  // PATCH publish of the site item — host-scoped like "/items/1"/"/items/9"
  // above: the shell's own client-side route is also "/items/site-1".
  await page.route("https://core.test/items/site-1", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = await route.request().postDataJSON();
      if (typeof body?.isPublished === "boolean") sitePublished = body.isPublished;
    }
    await route.fulfill({
      json: {
        pk: "site-1", resourceType: "site", slug: siteSlug, title: "Mon Portail",
        abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
        configId: null, isPublished: sitePublished,
      },
    });
  });

  // Public consultation by slug — 200 only when published and slug matches,
  // 404 otherwise (never 403 — anonymous access is the point).
  await page.route("https://core.test/public/sites/*", async (route) => {
    const wanted = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    if (sitePublished && wanted === siteSlug) {
      await route.fulfill({
        json: {
          pk: "site-1", resourceType: "site", slug: siteSlug, title: "Mon Portail",
          abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
          configId: null, isPublished: true,
        },
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: "site not found" } });
    }
  });

  // Public config for the site item — getPublicAppConfig unwraps `data.config`.
  // Serves whatever was actually PUT through the builder (savedConfigs, set by
  // the generic "**/configs/by-item/**" handler above) so that content widgets
  // added via the palette in a test genuinely round-trip to the public view —
  // not a fixture disconnected from what the test actually saved.
  await page.route("https://core.test/public/configs/by-item/site-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-site", itemId: "site-1", kind: "site", version: 1, config: savedConfigs.get("site-1") ?? SITE_APP_CONFIG },
    });
  });

  // Public items list (SP-16b) — Gallery's data source. Always returns the
  // one fixed published item; the site itself is not included (the fixture
  // only needs to prove the Gallery→vignette→PublicItemPage path).
  await page.route("https://core.test/public/items*", async (route) => {
    await route.fulfill({ json: { items: [GALLERY_ITEM], total: 1, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/public/configs/by-item/8", async (route) => {
    await route.fulfill({
      json: { id: "cfg-8", itemId: "8", kind: "app", version: 1, config: GALLERY_ITEM_CONFIG },
    });
  });
}
