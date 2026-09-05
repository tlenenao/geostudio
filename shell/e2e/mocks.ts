import type { Page } from "@playwright/test";

const ALL = [
  {
    pk: "1",
    resourceType: "app",
    title: "Alpha",
    abstract: "A",
    owner: "alice",
    thumbnailUrl: null,
    date: "2026-01-01",
    configId: null,
    isPublished: false,
    permissions: { read: true, write: true, delete: true, share: true },
  },
  {
    pk: "2",
    resourceType: "dashboard",
    title: "Beta",
    abstract: "B",
    owner: "alice",
    thumbnailUrl: null,
    date: "2026-01-01",
    configId: null,
    isPublished: false,
    permissions: { read: true, write: true, delete: true, share: true },
  },
  {
    pk: "3",
    resourceType: "dataset",
    title: "Gamma",
    abstract: "G",
    owner: "alice",
    thumbnailUrl: null,
    date: "2026-01-01",
    configId: null,
    isPublished: false,
    permissions: { read: true, write: true, delete: true, share: true },
  },
];

const DEFAULT_MAP_CONFIG = {
  kind: "map",
  map: {
    basemap: { style: "https://demotiles.maplibre.org/style.json" },
    view: { center: [2.4, 46.6], zoom: 5 },
    layers: [],
  },
} as const;

// Task 16 (SP-24 — la preuve de sortie) : une carte publiée portant une seule
// couche tuilée avec popup, servie sous l'item "map-1". Vue à zoom 0 pour
// coller à la fixture MVT (tuile 0/0/0, cf. core/scripts/dump_mvt_fixture.py).
const TILED_MAP_CONFIG = {
  kind: "map",
  map: {
    basemap: { style: "https://demotiles.maplibre.org/style.json" },
    view: { center: [0, 0], zoom: 0 },
    layers: [
      {
        id: "communes",
        title: "Communes",
        visible: true,
        kind: "vector",
        // https, pas http : isHostedCollectionUrl (MapView.tsx) compare des
        // origines complètes (protocole inclus) avant d'attacher le jeton de
        // session — même origine que VITE_CORE_URL ("https://core.test",
        // playwright.config.ts) requise pour que la tuile soit authentifiée.
        tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
        sourceLayer: "communes",
        collectionId: "communes",
        geometryKind: "polygon",
        pkColumn: "id",
        popup: { titleField: "nom", fields: [{ name: "population", label: "Habitants" }] },
      },
    ],
  },
} as const;

const DEFAULT_APP_CONFIG = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
} as const;

// Fixture canonique de GET /me — seule source de vérité pour ce payload
// (revue transverse SP-30l, finding 6 : trois copies quasi-identiques de ce
// littéral existaient, mockCore() ci-dessous et deux specs distinctes ;
// désormais toutes les trois passent par mockMe()).
//
// role/privileges (Task 17, plan roles-privileges-implementation) : remplace
// isAdmin/isAnalyst/hasAnyEditorRole, retirés du modèle Me côté cœur et
// shell. Défaut "creator" — même mapping que l'ancien hasAnyEditorRole: true
// (un éditeur, ni admin ni analyste) — miroir exact de
// BUILT_IN_ROLE_PRIVILEGES["creator"] (core/app/roles/privileges.py) et de
// la fixture `creator` de shell/src/auth/capabilities.test.ts.
const DEFAULT_ME = {
  id: "u-mock",
  username: "mockuser",
  firstName: "Mock",
  lastName: "User",
  email: null,
  tenantId: "t-mock",
  role: { id: "role-creator", name: "Créateur", slug: "creator" },
  privileges: [
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
    "automation.secrets.manage",
    "analytics.view",
    "tasks.view",
  ],
  version: "0.1.0",
  tenantSlug: "demo",
};

export function mockMe(page: Page, overrides: Partial<typeof DEFAULT_ME> = {}) {
  return page.route("**/me", async (route) => {
    await route.fulfill({ json: { ...DEFAULT_ME, ...overrides } });
  });
}

// Fixture canonique de GET /items/{pk} — un vrai cœur renvoie TOUJOURS un
// bloc `permissions` (SP-29a), jamais absent. Sans ce défaut par défaut, un
// mock d'item construit à la main sert une forme que le cœur ne produit
// jamais dès qu'une page consomme `hasPermission(item, ...)` — classe de
// défaut documentée F-tests-06 (revue SP-42), qui a cassé 8 tests E2E dès
// que DatasetEditPage a gagné un tel garde. Défaut "propriétaire" (les
// quatre permissions à true) : les specs qui veulent un rôle restreint
// passent `overrides.permissions`.
const DEFAULT_ITEM_PERMISSIONS = { read: true, write: true, delete: true, share: true };

export function mockItemDetail(page: Page, pk: string, overrides: Record<string, unknown> = {}) {
  return page.route(`https://core.test/items/${pk}`, async (route) => {
    await route.fulfill({
      json: {
        pk,
        resourceType: "dataset",
        title: "",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: null,
        isPublished: false,
        keywords: [],
        permissions: DEFAULT_ITEM_PERMISSIONS,
        ...overrides,
      },
    });
  });
}

// Fixture canonique du payload de collection servi par _collection_json()
// (core/app/collections/routes.py) — SP-43 Étape 3, même patron que
// mockMe() (SP-30l) pour la dérive équivalente sur GET /me. Les 23 clés
// doivent rester synchronisées avec core/tests/test_collections_json_contract.py
// (EXPECTED_KEYS) — un futur champ ajouté côté cœur doit être ajouté ici
// ET dans ce test Python, sinon cette fixture redevient incomplète comme
// les 3 littéraux qu'elle remplace (cf. spec SP-43 §1.5).
const DEFAULT_COLLECTION = {
  id: "points_interet",
  title: "Points d'intérêt",
  description: "",
  tableName: "points_interet",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 0,
  owner: "mockuser",
  attachmentFields: [] as { key: string; label: string }[],
  license: "",
  licenseUri: "",
  producer: "",
  contact: "",
  updateFrequency: "",
  lineage: "",
  language: "",
  version: "",
  temporalStart: null as string | null,
  temporalEnd: null as string | null,
};

export function mockCollection(overrides: Partial<typeof DEFAULT_COLLECTION> = {}) {
  return { ...DEFAULT_COLLECTION, ...overrides };
}

// Quatre profils canoniques (Task 17, plan roles-privileges-implementation) —
// mêmes valeurs que BUILT_IN_ROLE_PRIVILEGES (core/app/roles/privileges.py)
// et les fixtures admin/creator/analyst/reader de
// shell/src/auth/capabilities.test.ts. Les specs qui ont besoin d'un rôle
// différent du défaut ("creator", cf. DEFAULT_ME ci-dessus) passent
// mockMe(page, ADMIN_ME) / mockMe(page, ANALYST_ME) / mockMe(page, READER_ME)
// plutôt que de composer leur propre littéral role/privileges.
export const ADMIN_ME = {
  role: { id: "role-admin", name: "Administrateur", slug: "admin" },
  privileges: [
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
    "automation.secrets.manage",
    "analytics.view",
    "analytics.sql_lab.access",
    "tasks.view",
    "tasks.view_all",
    "admin.users.manage",
    "admin.roles.manage",
    "admin.harvest.manage",
    "admin.collections.manage",
    "admin.extensions.manage",
    "admin.secrets.manage",
    "settings.instance.manage",
  ],
};

export const CREATOR_ME = {
  role: { id: "role-creator", name: "Créateur", slug: "creator" },
  privileges: [
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
    "automation.secrets.manage",
    "analytics.view",
    "tasks.view",
  ],
};

export const ANALYST_ME = {
  role: { id: "role-analyst", name: "Analyste", slug: "analyst" },
  privileges: ["data.view", "analytics.view", "analytics.sql_lab.access", "tasks.view"],
};

export const READER_ME = {
  role: { id: "role-reader", name: "Lecteur", slug: "reader" },
  privileges: [] as string[],
};

export async function mockCore(page: Page) {
  const deleted = new Set<string>();
  // Stateful store: keyed by item id, holds the last PUT body per item.
  const savedConfigs = new Map<string, unknown>();
  let published = false;
  // Item 1 (Alpha) — title tracking for edit test (SP-30b/Task 6). Hoisted
  // here (rather than left next to the "/items/1" route below) so it's
  // declared before any route-handler closure that reads it — a future spec
  // ordering that made a route fire during the earlier declaration would
  // otherwise hit the TDZ (final review of SP-30b, finding 3).
  let item1Title = "Alpha";

  // Config history / restore (Task 18) — item "1" (Alpha) carries a
  // two-version story: the config served by GET /configs/by-item/1 starts
  // as "version 2" (current), and POST /configs/{id}/rollback with
  // {version: 1} flips this flag so subsequent GETs return "version 1"
  // instead — the same stateful-swap style already used for `published`/
  // `sitePublished` above.
  let rolledBackToVersion1 = false;
  const APP_CONFIG_V2 = {
    ...DEFAULT_APP_CONFIG,
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Titre version 2" } },
      ],
    },
  } as const;
  const APP_CONFIG_V1 = {
    ...DEFAULT_APP_CONFIG,
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Titre version 1" } },
      ],
    },
  } as const;

  // Site portal (SP-16a) — state for the created-then-published site.
  let siteSlug: string | null = null;
  let sitePublished = false;
  const SITE_APP_CONFIG = {
    version: 1,
    kind: "site",
    theme: {},
    dataSources: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 0,
          w: 4,
          h: 2,
          props: { text: "Bienvenue sur le portail" },
        },
      ],
    },
    messages: [],
    pages: [],
  } as const;

  // Content widgets (SP-16b) — a second published item, distinct from the
  // site itself, for the Gallery to list and link to.
  const GALLERY_ITEM = {
    pk: "8",
    resourceType: "app",
    title: "Carte des risques",
    abstract: "Resume des risques",
    owner: "mockuser",
    thumbnailUrl: null,
    date: "2026-01-01",
    configId: null,
    isPublished: true,
    permissions: { read: true, write: true, delete: true, share: true },
    keywords: ["risques"],
  } as const;
  const GALLERY_ITEM_CONFIG = {
    version: 1,
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 0,
          w: 4,
          h: 2,
          props: { text: "Detail de l'article" },
        },
      ],
    },
  } as const;

  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    const scope = url.searchParams.get("scope");
    const type = url.searchParams.get("type");
    // Honour `type` (revue finale de branche, M2). LayerPicker fires a
    // hosted-tileset3d lookup (`?type=tileset3d`) against this same generic
    // endpoint whenever it renders; answering it with every fixture item
    // regardless of type conjures phantom LayerSources sharing another
    // source's title — exactly what broke harvest-wms.spec.ts, which had to
    // patch its own local override the same way. Fixed here so the default
    // handler stops being armed for the next spec.
    const visible = ALL.filter((r) => !deleted.has(r.pk) && (!type || r.resourceType === type));
    const items = scope === "mine" ? [] : visible;
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await mockMe(page);

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

  // SP-42, revue de la dernière passe de correctifs (point 2, Critical) :
  // MapEditorPage/AppBuilderPage/PipelineBuilderPage/ReportEditPage appellent
  // désormais toutes useItem(pk) (GET /items/{pk}) pour verrouiller
  // Enregistrer sur permissions.write. "**/items*" ci-dessus (liste) ne
  // matche jamais un id imbriqué : son dernier segment est un `*` simple, qui
  // ne traverse pas "/" — un id qui n'a pas sa propre route dédiée plus bas
  // (seuls "1"/"9"/"site-1" en ont une) restait donc totalement non mocké,
  // et itemQuery finissait en erreur/jamais résolu. Filet générique — item
  // propriétaire par défaut (permissions.write=true) pour ne rien changer au
  // comportement des specs pré-existantes qui n'affirment pas sur les
  // permissions elles-mêmes. Enregistré AVANT les routes spécifiques
  // ci-dessous : en dernier arrivé gagne (Playwright), "1"/"9"/"site-1"
  // gardent leur propre réponse avec état (titre édité, etc.), ce filet ne
  // sert que les ids qu'aucune spec ne mocke explicitement (ex. "77",
  // "map-1", "pipe-1").
  await page.route(/https:\/\/core\.test\/items\/[^/?]+(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url());
    const pk = url.pathname.split("/").pop()!;
    await route.fulfill({
      json: {
        pk,
        resourceType: "map",
        title: pk,
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: `cfg-${pk}`,
        isPublished: false,
        keywords: [],
        permissions: { read: true, write: true, delete: true, share: true },
        license: "",
        language: "fr",
      },
    });
  });

  // Scoped to the cœur's host (not "**/items/1"): the shell's own client-side
  // route is also "/items/1" (same path, different origin — localhost:4173
  // vs. https://core.test), so a path-only glob here would also intercept
  // the browser's document navigation to that page and break rendering.
  await page.route("https://core.test/items/1", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = await route.request().postDataJSON();
      if (typeof body.title === "string") item1Title = body.title;
    }
    await route.fulfill({
      json: {
        ...ALL[0],
        title: item1Title,
      },
    });
  });

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "site") {
      siteSlug = body.slug ?? "mon-portail";
      await route.fulfill({
        status: 201,
        json: { id: "cfg-site", kind: "site", itemId: "site-1" },
      });
    } else if (body?.config?.kind === "map") {
      // Map creation path — return itemId "77" so the test lands on /maps/77.
      await route.fulfill({
        status: 201,
        json: { id: "cfg-1", kind: "map", itemId: "77" },
      });
    } else if (body?.config?.kind === "dataset") {
      await route.fulfill({
        status: 201,
        json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" },
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
        pk: "9",
        resourceType: "app",
        title: "Créée",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: null,
        isPublished: published,
        permissions: { read: true, write: true, delete: true, share: true },
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
      } else if (itemId === "map-1") {
        // Published map with a tiled layer + popup (Task 16, SP-24 output
        // proof) — see map-popup.spec.ts.
        await route.fulfill({
          json: {
            id: "cfg-map-1",
            itemId: "map-1",
            kind: "map",
            config: TILED_MAP_CONFIG,
          },
        });
      } else {
        // App/dashboard items (9, 1, …) — return stored config if present, else empty app config.
        // Item "1" carries the config-history/rollback story (Task 18):
        // starts at APP_CONFIG_V2, switches to APP_CONFIG_V1 once
        // rolledBackToVersion1 is set by the rollback route below.
        const stored = savedConfigs.get(itemId);
        const config =
          itemId === "1"
            ? rolledBackToVersion1
              ? APP_CONFIG_V1
              : (stored ?? APP_CONFIG_V2)
            : (stored ?? DEFAULT_APP_CONFIG);
        await route.fulfill({
          json: {
            id: `cfg-${itemId}`,
            itemId,
            kind: "app",
            config,
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

  // Config history (Task 18) — listConfigRevisions/rollbackConfig resolve
  // the config id via GET /configs/by-item/{pk} first (handled above), then
  // hit these two routes keyed by that config id (e.g. "cfg-1"). Two
  // revisions is enough to exercise the "current has no button, the other
  // does" logic in ConfigHistoryPanel.
  await page.route("**/configs/*/revisions", async (route) => {
    await route.fulfill({
      json: [
        { version: 2, created_at: "2026-01-02T00:00:00Z" },
        { version: 1, created_at: "2026-01-01T00:00:00Z" },
      ],
    });
  });

  await page.route("**/configs/*/rollback", async (route) => {
    const body = await route.request().postDataJSON();
    if (body?.version === 1) rolledBackToVersion1 = true;
    await route.fulfill({ status: 204, body: "" });
  });

  // Martin vector-tile catalog — exposes the "Communes" layer source.
  await page.route("**/catalog", async (route) => {
    await route.fulfill({
      json: { tiles: { communes: { description: "Communes" } } },
    });
  });

  // Cœur OGC API collections — filtered by `q` when present (LayerPicker
  // search, Task 11/12), all visible collections otherwise (real backend
  // behavior: core/app/collections/routes.py's list_collections passes
  // q=None straight through to list_visible_collections, which returns
  // everything unfiltered — it does not gate on q being present).
  //
  // Task 16 (SP-24) found and fixed a stale divergence here: this route used
  // to return `[]` by default ("matching the pre-Task-12 behavior for every
  // spec that never searches the LayerPicker" — back when a since-removed
  // martin-catalog route was the *actual* unconditional source of the
  // "Communes" layer-picker entry). Task 15 ("propose une seule entrée
  // tuilée par collection", commit 57fc36c) dropped that redundant
  // martin-catalog call from listLayerSources (itemClient.ts) — collections
  // now flow through this route alone — but never updated this mock's
  // default to match, silently breaking map-editor.spec.ts's un-searched
  // "click Communes" step. Surfaced by running the full E2E suite here for
  // the first time since that commit, exactly the SP-23 task 18 precedent.
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
      : ALL_COLLECTIONS;
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
        id: "parcs",
        title: "Parcs",
        description: "Parcs publics de la ville",
        tableName: "parcs",
        isPublic: true,
        editable: false,
        geometryType: null,
        srid: null,
        pkColumn: "id",
        permissions: { read: true, write: false, delete: false, share: false },
        featureCount: 2,
      },
    });
  });

  await page.route("**/collections/parcs/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "parcs",
        pk: "id",
        geometry: null,
        fields: [{ name: "nom", type: "string", required: true }],
      },
    });
  });

  // Collection "incidents" — schéma introspecté, permission d'écriture, et
  // CRUD complet avec état en mémoire (pour que la Table reflète les écritures
  // du Formulaire au fil du scénario "déclarer un incident").
  const incidentRecords = new Map<
    string,
    { properties: Record<string, unknown>; geometry: unknown }
  >();
  let nextIncidentId = 1;

  await page.route("**/collections/incidents", async (route) => {
    await route.fulfill({
      json: {
        id: "incidents",
        title: "Incidents",
        description: "",
        tableName: "incidents",
        isPublic: false,
        editable: true,
        geometryType: null,
        srid: null,
        pkColumn: "id",
        permissions: { read: true, write: true, delete: false, share: false },
      },
    });
  });

  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents",
        pk: "id",
        geometry: null,
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
            type: "Feature",
            id: Number(id),
            properties: r.properties,
            geometry: r.geometry,
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
        pk: "site-1",
        resourceType: "site",
        slug: siteSlug,
        title: "Mon Portail",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: null,
        isPublished: sitePublished,
        permissions: { read: true, write: true, delete: true, share: true },
      },
    });
  });

  // Public consultation by slug — 200 only when published and slug matches,
  // 404 otherwise (never 403 — anonymous access is the point).
  await page.route("https://core.test/public/sites/*", async (route) => {
    const wanted = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").pop() ?? "",
    );
    if (sitePublished && wanted === siteSlug) {
      await route.fulfill({
        json: {
          pk: "site-1",
          resourceType: "site",
          slug: siteSlug,
          title: "Mon Portail",
          abstract: "",
          owner: "mockuser",
          thumbnailUrl: null,
          date: "2026-01-01",
          configId: null,
          isPublished: true,
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
      json: {
        id: "cfg-site",
        itemId: "site-1",
        kind: "site",
        version: 1,
        config: savedConfigs.get("site-1") ?? SITE_APP_CONFIG,
      },
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
