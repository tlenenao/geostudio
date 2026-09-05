// SPDX-License-Identifier: Apache-2.0
import { Blob as NodeBlob } from "node:buffer";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import {
  createItemClient,
  FeatureValidationError,
  SqlQueryError,
  toFrontLayer,
  type RawMapLayer,
} from "./itemClient";
import type { DataSource } from "./types";
import { OWNER_PERMISSIONS } from "../auth/permissions";

// jsdom's Blob shim (used by this test environment) has no .text()/.arrayBuffer();
// Node's own Blob (from node:buffer) does — swap it in so exportDataSource tests
// can read the fetched blob's content. No effect in real browsers.
if (typeof (globalThis.Blob?.prototype as { text?: unknown } | undefined)?.text !== "function") {
  (globalThis as unknown as { Blob: typeof Blob }).Blob = NodeBlob as unknown as typeof Blob;
}

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    coreUrl: "https://core.test",
    getToken: () => token,
  });
}

test("listItems sends the bearer token and scope", async () => {
  let auth: string | null = null;
  let url: string | null = null;
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      auth = request.headers.get("authorization");
      url = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  await makeClient("abc").listItems({ scope: "shared", type: "app" });
  expect(auth).toBe("Bearer abc");
  expect(url).toContain("scope=shared");
  expect(url).toContain("type=app");
});

test("getItem returns the item as-is (core owner is already a flat string)", async () => {
  const item = await makeClient().getItem("7");
  expect(item.pk).toBe("7");
  expect(item.owner).toBe("alice");
});

test("getItem missing returns 404 and throws", async () => {
  await expect(makeClient().getItem("404")).rejects.toThrow(/404/);
});

test("getMe maps camelCase fields, dropping id/email/tenantId", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges: ["catalog.manage", "maps.manage"],
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me).toEqual({
    username: "alice",
    firstName: "Alice",
    lastName: "Martin",
    role: { id: "role-1", name: "Créateur", slug: "creator" },
    privileges: ["catalog.manage", "maps.manage"],
  });
});

test("getMe surfaces the caller's privileges", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-2", name: "Administrateur", slug: "admin" },
        privileges: ["admin.roles.manage", "admin.users.manage"],
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me.role.slug).toBe("admin");
  expect(me.privileges).toContain("admin.roles.manage");
});

test("createConfigItem does not send owner in the request body", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        { id: "cfg-1", itemId: "99", kind: "app", version: 1, config: {} },
        { status: 201 },
      );
    }),
  );
  const item = await makeClient().createConfigItem({
    kind: "app",
    title: "My App",
    owner: "alice",
  });
  expect(body).not.toHaveProperty("owner");
  expect(item.owner).toBe("alice");
  expect(item.pk).toBe("99");
});

test("createConfigItem defaults interactions to auto for a new app", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "cfg-1", kind: "app", itemId: "1" }, { status: 201 });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "Test", owner: "alice" });
  expect((posted!.config as Record<string, unknown>).interactions).toBe("auto");
});

test("updateItem sends the patch camelCase, unchanged", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/items/:pk", async ({ params, request }) => {
      body = await request.json();
      return HttpResponse.json({
        pk: String(params.pk),
        resourceType: "app",
        title: "Renamed",
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "",
        configId: null,
        isPublished: true,
      });
    }),
  );
  const item = await makeClient().updateItem("7", { title: "Renamed", isPublished: true });
  expect(body).toEqual({ title: "Renamed", isPublished: true });
  expect(item.title).toBe("Renamed");
});

test("uploadThumbnail POSTs multipart form data", async () => {
  let method: string | null = null;
  server.use(
    http.post("https://core.test/items/:pk/thumbnail", ({ request }) => {
      method = request.method;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().uploadThumbnail("7", new File(["x"], "thumb.png", { type: "image/png" }));
  expect(method).toBe("POST");
});

test("deleteItem tolerates a 404 as success", async () => {
  server.use(
    http.delete(
      "https://core.test/configs/by-item/:pk",
      () => new HttpResponse(null, { status: 404 }),
    ),
  );
  await expect(makeClient().deleteItem("nope")).resolves.toBeUndefined();
});

test("listGroups maps name to title", async () => {
  const groups = await makeClient().listGroups();
  expect(groups).toEqual([
    { id: "10", title: "Équipe A" },
    { id: "11", title: "Équipe B" },
  ]);
});

test("getSharing passes through the core's Sharing shape directly", async () => {
  const sharing = await makeClient().getSharing("7");
  expect(sharing).toEqual({ public: true, groups: [{ groupId: "10", role: "editor" }] });
});

test("setSharing PUTs the sharing object as-is", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/items/:pk/sharing", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().setSharing("7", {
    public: false,
    groups: [{ groupId: "10", role: "viewer" }],
  });
  expect(body).toEqual({ public: false, groups: [{ groupId: "10", role: "viewer" }] });
});

test("listLayerSources returns one tiled entry per core collection, and no Martin source", async () => {
  // Martin sort du sélecteur (spec SP-24 §3.7) : il se connecte en
  // propriétaire des tables, donc hors RLS, et n'a aucune notion de
  // collection. Une même collection n'apparaît plus qu'une fois.
  let auth: string | null = null;
  server.use(
    http.get("https://core.test/collections", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        collections: [
          { id: "communes", title: "Communes", geometryType: "Polygon", pkColumn: "id" },
          { id: "sans_geom", title: "Sans géométrie", geometryType: null, pkColumn: "id" },
        ],
      });
    }),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
  );
  const sources = await makeClient("abc").listLayerSources();
  expect(auth).toBe("Bearer abc");
  expect(sources.map((s) => s.service)).not.toContain("martin");
  const communes = sources.find((s) => s.id === "communes")!;
  expect(communes).toMatchObject({
    service: "core",
    kind: "vector",
    collectionId: "communes",
    geometryKind: "polygon",
    pkColumn: "id",
    tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
  });
  expect(communes.sourceLayer).toBe("communes");
});

test("a collection without geometry type yields no geometryKind rather than a wrong one", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [{ id: "sans_geom", title: "Sans géométrie", geometryType: null }],
      }),
    ),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources.find((s) => s.id === "sans_geom")?.geometryKind).toBeUndefined();
});

test("the Martin catalog is never fetched any more", async () => {
  server.use(
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
  );
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  await makeClient().listLayerSources();
  const urls = fetchSpy.mock.calls.map(([u]) => String(u));
  fetchSpy.mockRestore();
  expect(urls.some((u) => u.includes("/catalog"))).toBe(false);
});

test("listActiveExtensions maps the core's /extensions response to ExtensionManifest[]", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
            events: ["changed"],
            actions: ["reset"],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
          },
        ],
      });
    }),
  );
  const result = await makeClient("abc").listActiveExtensions();
  expect(auth).toBe("Bearer abc");
  expect(result).toEqual([
    {
      type: "acme.gauge",
      tag: "gauge-extension-widget",
      label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js",
      props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
      events: ["changed"],
      actions: ["reset"],
      defaultSize: { w: 2, h: 2 },
      permissions: { collections: "all" },
    },
  ]);
});

test("listLayerSources still returns core collections when another layer service fails", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [{ id: "public.parcs", title: "Parcs" }] }),
    ),
    http.get("https://core.test/harvest/layers", () => new HttpResponse(null, { status: 500 })),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources).toHaveLength(1);
  expect(sources[0].service).toBe("core");
});

test("listLayerSources passes q to /collections", async () => {
  let collectionsUrl: string | null = null;
  server.use(
    http.get("https://core.test/collections", ({ request }) => {
      collectionsUrl = request.url;
      return HttpResponse.json({ collections: [{ id: "c1", title: "Communes" }] });
    }),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
  );
  const sources = await makeClient().listLayerSources({ q: "commun" });
  expect(collectionsUrl).toContain("q=commun");
  expect(sources.find((s) => s.id === "c1")).toBeDefined();
});

test("listLayerSources throws when all services fail", async () => {
  server.use(
    http.get("https://core.test/collections", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/harvest/layers", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/items", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(makeClient().listLayerSources()).rejects.toThrow();
});

test("createMapItem posts a map skeleton and returns a map Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: "map", itemId: "77" }, { status: 201 });
    }),
  );
  const item = await makeClient().createMapItem({ title: "Carte", owner: "alice" });
  expect(body.config.kind).toBe("map");
  expect(body.config.map.layers).toEqual([]);
  expect(item).toMatchObject({ pk: "77", resourceType: "map", title: "Carte", configId: "cfg-1" });
});

test("getMapConfig reads and maps the builder map config", async () => {
  // ConfigRead nests the builder config under "config"; the map is config.map.
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "a",
                title: "A",
                visible: true,
                kind: "feature",
                url: "https://fs/a",
                tilesUrl: null,
                sourceLayer: null,
                opacity: null,
                deckType: null,
                dataUrl: null,
                paint: null,
                props: null,
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.zoom).toBe(8);
  expect(cfg.layers[0]).toEqual({
    id: "a",
    title: "A",
    visible: true,
    kind: "feature",
    url: "https://fs/a",
  });
});

// SP-24 Task 16 regression: getMapConfig used to drop popup/collectionId/
// geometryKind/pkColumn on load (toFrontLayer never read them off the raw
// server JSON), even though the server round-trips them fine and MapView
// requires layer.popup to be truthy to ever open a popup on click — a
// freshly-loaded map with a saved popup config could never show one.
test("getMapConfig reads popup/collectionId/geometryKind/pkColumn on a vector layer", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "communes",
                title: "Communes",
                visible: true,
                kind: "vector",
                tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
                sourceLayer: "communes",
                collectionId: "communes",
                geometryKind: "polygon",
                pkColumn: "id",
                popup: { titleField: "nom", fields: [{ name: "population", label: "Habitants" }] },
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "communes",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "communes",
    collectionId: "communes",
    geometryKind: "polygon",
    pkColumn: "id",
    popup: { titleField: "nom", fields: [{ name: "population", label: "Habitants" }] },
  });
});

// SP-25 Task 12 regression: same class of bug as the popup one above
// (SP-24 Task 16) — toFrontLayer never read symbology off the raw server
// JSON either, so a map saved with a configured symbology silently lost it
// back to empty/default on reload.
test("getMapConfig reads symbology on a vector layer", async () => {
  const symbology = {
    color: {
      field: "population",
      mode: "numeric" as const,
      classification: { method: "quantile" as const, classes: 5 },
      palette: "sequential-blue" as const,
      domain: { kind: "numeric-classed" as const, breaks: [10, 20, 30, 40, 50] },
      computedAt: "2026-08-23T00:00:00.000Z",
    },
  };
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "communes",
                title: "Communes",
                visible: true,
                kind: "vector",
                tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
                sourceLayer: "communes",
                collectionId: "communes",
                geometryKind: "polygon",
                pkColumn: "id",
                symbology,
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "communes",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "communes",
    collectionId: "communes",
    geometryKind: "polygon",
    pkColumn: "id",
    symbology,
  });
});

test("getMapConfig reads popup on a feature (GeoJSON) layer", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "a",
                title: "A",
                visible: true,
                kind: "feature",
                url: "https://fs/a",
                popup: { titleField: "nom" },
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "a",
    title: "A",
    visible: true,
    kind: "feature",
    url: "https://fs/a",
    popup: { titleField: "nom" },
  });
});

// SP-28 Task 3 regression: same class of bug as popup (SP-24 Task 16) and
// symbology (SP-25 Task 12) above — toFrontLayer never read renderAs off the
// raw server JSON either, so a point layer styled as "circle" fell back to
// MapView's default "fill" on reload and rendered nothing visible.
test("getMapConfig reads renderAs on a feature (GeoJSON) layer", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "a",
                title: "A",
                visible: true,
                kind: "feature",
                url: "https://fs/a",
                renderAs: "circle",
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "a",
    title: "A",
    visible: true,
    kind: "feature",
    url: "https://fs/a",
    renderAs: "circle",
  });
});

test("getMapConfig reads collectionId/pkColumn on a feature (GeoJSON) layer", async () => {
  // SP-42 F-shell-carte-01 (4e occurrence du piège n°5) : toFrontLayer()
  // restaure déjà collectionId/pkColumn pour une couche vector ; la couche
  // feature les perdait au rechargement, cassant les pièces jointes/
  // cross-filter d'une couche GeoJSON qui les porte.
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "a",
                title: "A",
                visible: true,
                kind: "feature",
                url: "https://fs/a",
                collectionId: "communes",
                pkColumn: "id",
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "a",
    title: "A",
    visible: true,
    kind: "feature",
    url: "https://fs/a",
    collectionId: "communes",
    pkColumn: "id",
  });
});

// SP-43 Étape 2 : test caractéristique — pour chaque kind de MapLayer, un
// RawMapLayer avec TOUS ses champs optionnels renseignés doit survivre
// intégralement à toFrontLayer(). Filet contre une 5e perte de champ
// silencieuse (les 4 précédentes : popup, symbology, renderAs,
// collectionId/pkColumn — cf. les 4 tests de régression ci-dessus).
describe("toFrontLayer characteristic test — no optional field is ever dropped", () => {
  test("vector: every optional field survives", () => {
    const raw: RawMapLayer = {
      id: "v1",
      title: "V",
      visible: true,
      kind: "vector",
      tilesUrl: "https://t",
      sourceLayer: "s",
      paint: { "fill-color": "#fff" },
      collectionId: "c1",
      geometryKind: "polygon",
      pkColumn: "id",
      popup: { titleField: "nom", fields: [] },
      symbology: { kind: "categorical", field: "type", categories: [] } as never,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.paint).toEqual(raw.paint);
    expect(out.collectionId).toBe(raw.collectionId);
    expect(out.geometryKind).toBe(raw.geometryKind);
    expect(out.pkColumn).toBe(raw.pkColumn);
    expect(out.popup).toEqual(raw.popup);
    expect(out.symbology).toEqual(raw.symbology);
  });

  test("feature: every optional field survives", () => {
    const raw: RawMapLayer = {
      id: "f1",
      title: "F",
      visible: true,
      kind: "feature",
      url: "https://fs/a",
      paint: { "fill-color": "#000" },
      collectionId: "c2",
      pkColumn: "fid",
      popup: { titleField: "nom", fields: [] },
      renderAs: "circle",
      symbology: { kind: "categorical", field: "type", categories: [] } as never,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.paint).toEqual(raw.paint);
    expect(out.collectionId).toBe(raw.collectionId);
    expect(out.pkColumn).toBe(raw.pkColumn);
    expect(out.popup).toEqual(raw.popup);
    expect(out.renderAs).toBe(raw.renderAs);
    expect(out.symbology).toEqual(raw.symbology);
  });

  test("raster: optional field (opacity) survives", () => {
    const raw: RawMapLayer = {
      id: "r1",
      title: "R",
      visible: true,
      kind: "raster",
      tilesUrl: "https://t",
      opacity: 0.5,
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.opacity).toBe(0.5);
  });

  test("deck: optional field (props) survives", () => {
    const raw: RawMapLayer = {
      id: "d1",
      title: "D",
      visible: true,
      kind: "deck",
      deckType: "heatmap",
      dataUrl: "https://d",
      props: { radius: 30 },
    };
    const out = toFrontLayer(raw) as Record<string, unknown>;
    expect(out.props).toEqual(raw.props);
  });
});

test("getMapConfig throws when the config has no map payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "app",
        config: { kind: "app", map: null },
      }),
    ),
  );
  await expect(makeClient().getMapConfig("77")).rejects.toThrow();
});

test("saveMapConfig PUTs the map config by item", async () => {
  let method = "";
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/77", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "map", map: body.map });
    }),
  );
  const cfg = {
    basemap: { style: "s" },
    view: { center: [0, 0] as [number, number], zoom: 3 },
    layers: [],
  };
  await makeClient().saveMapConfig("77", cfg);
  expect(method).toBe("PUT");
  expect(body.kind).toBe("map");
  expect(body.map.view.zoom).toBe(3);
});

test("getMapConfig maps a tiles3d layer", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              {
                id: "bldg",
                title: "Bâtiments",
                visible: true,
                kind: "tiles3d",
                url: "https://example.test/tileset.json",
                tilesUrl: null,
                sourceLayer: null,
                opacity: null,
                deckType: null,
                dataUrl: null,
                paint: null,
                props: null,
              },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({
    id: "bldg",
    title: "Bâtiments",
    visible: true,
    kind: "tiles3d",
    url: "https://example.test/tileset.json",
  });
});

test("getMapConfig reads terrain and camera pitch/bearing", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8, pitch: 40, bearing: 200 },
            layers: [],
            terrain: {
              tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
              encoding: "terrarium",
              exaggeration: 1.5,
            },
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.pitch).toBe(40);
  expect(cfg.view.bearing).toBe(200);
  expect(cfg.terrain).toEqual({
    tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
    encoding: "terrarium",
    exaggeration: 1.5,
  });
});

test("getMapConfig defaults terrain to null and omits pitch/bearing when absent", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8, pitch: null, bearing: null },
            layers: [],
            terrain: null,
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.pitch).toBeUndefined();
  expect(cfg.view.bearing).toBeUndefined();
  expect(cfg.terrain).toBeNull();
});

test("saveMapConfig sends terrain nested under map, not at the top level (unlike printLayout)", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/77", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveMapConfig("77", {
    basemap: { style: "s" },
    view: { center: [0, 0], zoom: 1, pitch: 30, bearing: 60 },
    layers: [],
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" },
  });
  expect(body.map.terrain).toEqual({
    tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
    encoding: "terrarium",
  });
  expect(body.map.view).toEqual({ center: [0, 0], zoom: 1, pitch: 30, bearing: 60 });
  expect(body.terrain).toBeUndefined();
});

test("createDatasetItem posts a dataset payload and returns a dataset Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds1", kind: "dataset", itemId: "ds-1" }, { status: 201 });
    }),
  );
  const item = await makeClient().createDatasetItem({
    title: "Parcs",
    owner: "alice",
    source: "collection",
    collectionId: "parcs",
  });
  expect(body.config.kind).toBe("dataset");
  expect(body.config.dataset).toEqual({ source: "collection", collectionId: "parcs", columns: {} });
  expect(item).toMatchObject({
    pk: "ds-1",
    resourceType: "dataset",
    title: "Parcs",
    configId: "cfg-ds1",
  });
});

test("getDatasetConfig reads the dataset payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-2", () =>
      HttpResponse.json({
        id: "cfg-ds2",
        itemId: "ds-2",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: {
            source: "collection",
            collectionId: "parcs",
            columns: { nom: { label: "Nom" } },
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getDatasetConfig("ds-2");
  expect(cfg).toEqual({
    source: "collection",
    collectionId: "parcs",
    columns: { nom: { label: "Nom" } },
    timeField: null,
    reactsToExtent: false,
    crossFilterLinks: [],
    sourcePipelineId: null,
  });
});

test("getDatasetConfig throws when the config has no dataset payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-3", () =>
      HttpResponse.json({ id: "cfg-ds3", itemId: "ds-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getDatasetConfig("ds-3")).rejects.toThrow();
});

test("createBookmarkItem posts a bookmark payload and returns a bookmark Item", async () => {
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      const body = (await request.json()) as { title: string; config: unknown };
      expect(body.config).toEqual({
        version: 1,
        kind: "bookmark",
        bookmark: {
          appId: "app-1",
          pageId: "page-1",
          timeRange: { from: "2026-01-01", to: "2026-02-01" },
          extent: null,
          crossFilter: {},
        },
      });
      return HttpResponse.json(
        { id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" },
        { status: 201 },
      );
    }),
  );
  const item = await makeClient().createBookmarkItem({
    title: "Ma vue",
    owner: "alice",
    appId: "app-1",
    pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: null,
    crossFilter: {},
  });
  expect(item).toEqual({
    pk: "bookmark-1",
    resourceType: "bookmark",
    title: "Ma vue",
    abstract: "",
    owner: "alice",
    thumbnailUrl: null,
    date: "",
    configId: "cfg-bookmark",
    isPublished: false,
    permissions: OWNER_PERMISSIONS,
    license: "",
    language: "fr",
  });
});

test("getBookmarkConfig reads the bookmark payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-1", () =>
      HttpResponse.json({
        id: "cfg-bookmark",
        itemId: "bookmark-1",
        kind: "bookmark",
        config: {
          version: 1,
          kind: "bookmark",
          bookmark: {
            appId: "app-1",
            pageId: "page-1",
            timeRange: { from: "2026-01-01", to: "2026-02-01" },
            extent: null,
            crossFilter: {},
          },
        },
      }),
    ),
  );
  const payload = await makeClient().getBookmarkConfig("bookmark-1");
  expect(payload).toEqual({
    appId: "app-1",
    pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: null,
    crossFilter: {},
  });
});

test("getBookmarkConfig throws when the config has no bookmark payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-2", () =>
      HttpResponse.json({
        id: "cfg-x",
        itemId: "bookmark-2",
        kind: "bookmark",
        config: { version: 1, kind: "bookmark" },
      }),
    ),
  );
  await expect(makeClient().getBookmarkConfig("bookmark-2")).rejects.toThrow();
});

test("saveDatasetConfig PUTs the dataset config by item", async () => {
  let method = "";
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/ds-4", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-ds4",
        itemId: "ds-4",
        kind: "dataset",
        dataset: body.dataset,
      });
    }),
  );
  await makeClient().saveDatasetConfig("ds-4", {
    source: "collection",
    collectionId: "parcs",
    columns: {},
  });
  expect(method).toBe("PUT");
  expect(body.kind).toBe("dataset");
  expect(body.dataset.collectionId).toBe("parcs");
});

test("getDatasetConfig/saveDatasetConfig round-trip timeField/reactsToExtent", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        config: {
          dataset: {
            source: "collection",
            collectionId: "parcs",
            columns: {},
            timeField: "date_releve",
            reactsToExtent: true,
          },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.timeField).toBe("date_releve");
  expect(config.reactsToExtent).toBe(true);

  let putBody: Record<string, unknown> | null = null;
  server.use(
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      putBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveDatasetConfig("ds-1", { ...config, reactsToExtent: false });
  expect((putBody!.dataset as Record<string, unknown>).reactsToExtent).toBe(false);
});

test("getDatasetConfig includes crossFilterLinks from the wire response", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1",
        itemId: "ds-1",
        kind: "dataset",
        config: {
          version: 1,
          kind: "dataset",
          dataset: {
            source: "collection",
            collectionId: "parcs",
            columns: {},
            crossFilterLinks: [
              {
                targetDatasetId: "ds-2",
                mode: "attribute",
                sourceField: "commune",
                targetField: "nom",
              },
            ],
          },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "attribute", sourceField: "commune", targetField: "nom" },
  ]);
});

test("getDatasetConfig defaults crossFilterLinks to an empty array when absent from the wire", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1",
        itemId: "ds-1",
        kind: "dataset",
        config: {
          version: 1,
          kind: "dataset",
          dataset: { source: "collection", collectionId: "parcs", columns: {} },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-1");
  expect(config.crossFilterLinks).toEqual([]);
});

test("saveDatasetConfig sends crossFilterLinks as-is and caches it for later reads", async () => {
  let posted: unknown;
  server.use(
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json(undefined, { status: 204 });
    }),
  );
  await makeClient().saveDatasetConfig("ds-1", {
    source: "collection",
    collectionId: "parcs",
    columns: {},
    crossFilterLinks: [{ targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" }],
  });
  expect((posted as { dataset: { crossFilterLinks: unknown } }).dataset.crossFilterLinks).toEqual([
    { targetDatasetId: "ds-2", mode: "spatial", precision: "bbox" },
  ]);
});

test("featuresUrl resolves datasetId to the dataset's collectionId once cached", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-5", () =>
      HttpResponse.json({
        id: "cfg-ds5",
        itemId: "ds-5",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "parcs", columns: {} },
        },
      }),
    ),
  );
  const client = makeClient();
  // Cache-miss: falls back to source.layer (empty) until something warms the cache.
  expect(
    client.featuresUrl({
      id: "s1",
      type: "features",
      service: "core",
      layer: "",
      datasetId: "ds-5",
      query: {},
    }),
  ).toBe("https://core.test/collections//items");
  await client.getDatasetConfig("ds-5"); // warms the cache
  expect(
    client.featuresUrl({
      id: "s1",
      type: "features",
      service: "core",
      layer: "",
      datasetId: "ds-5",
      query: {},
    }),
  ).toBe("https://core.test/collections/parcs/items");
});

test("queryDataSource resolves datasetId to the dataset's collectionId before fetching features", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-6", () =>
      HttpResponse.json({
        id: "cfg-ds6",
        itemId: "ds-6",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "parcs", columns: {} },
        },
      }),
    ),
    http.get("https://core.test/collections/parcs/items", () =>
      HttpResponse.json({ features: [{ id: 1, properties: { nom: "Le Parc" } }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1",
    type: "features",
    service: "core",
    layer: "",
    datasetId: "ds-6",
    query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Le Parc" }, geometry: undefined }]);
});

test("featuresUrl routes an arcgis-sourced dataset to /datasets/{datasetItemId}/arcgis/items", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-1", () =>
      HttpResponse.json({
        id: "cfg-arc1",
        itemId: "ds-arcgis-1",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "arcgis", arcgisItemId: "layer-9", columns: {} },
        },
      }),
    ),
  );
  const client = makeClient();
  await client.getDatasetConfig("ds-arcgis-1"); // warms the cache
  expect(
    client.featuresUrl({
      id: "s1",
      type: "features",
      service: "core",
      layer: "",
      datasetId: "ds-arcgis-1",
      query: {},
    }),
  ).toBe("https://core.test/datasets/ds-arcgis-1/arcgis/items");
});

test("featuresUrl keys the arcgis proxy URL on the dataset item id, not the arcgis layer id", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-999", () =>
      HttpResponse.json({
        id: "cfg-arc999",
        itemId: "ds-999",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "arcgis", arcgisItemId: "totally-different-layer-id", columns: {} },
        },
      }),
    ),
  );
  const client = makeClient();
  await client.getDatasetConfig("ds-999"); // warms the cache
  expect(
    client.featuresUrl({
      id: "s1",
      type: "features",
      service: "core",
      layer: "",
      datasetId: "ds-999",
      query: {},
    }),
  ).toBe("https://core.test/datasets/ds-999/arcgis/items");
});

test("queryDataSource fetches features from the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-2", () =>
      HttpResponse.json({
        id: "cfg-arc2",
        itemId: "ds-arcgis-2",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "arcgis", arcgisItemId: "layer-10", columns: {} },
        },
      }),
    ),
    http.get("https://core.test/datasets/ds-arcgis-2/arcgis/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [{ id: 1, properties: { nom: "Bât" } }],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1",
    type: "features",
    service: "core",
    layer: "",
    datasetId: "ds-arcgis-2",
    query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Bât" }, geometry: undefined }]);
});

test("queryDataSource posts aggregate queries to the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-3", () =>
      HttpResponse.json({
        id: "cfg-arc3",
        itemId: "ds-arcgis-3",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "arcgis", arcgisItemId: "layer-11", columns: {} },
        },
      }),
    ),
    http.post("https://core.test/datasets/ds-arcgis-3/arcgis/aggregate", () =>
      HttpResponse.json({ categoryKey: "group", rows: [{ group: "Total", value: 4 }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "",
    datasetId: "ds-arcgis-3",
    query: { agg: "count" },
  });
  expect(records).toEqual([{ id: "Total", properties: { group: "Total", value: 4 } }]);
});

test("getDatasetConfig returns an arcgis-shaped DatasetConfig for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-4", () =>
      HttpResponse.json({
        id: "cfg-arc4",
        itemId: "ds-arcgis-4",
        kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "arcgis", arcgisItemId: "layer-12", columns: {} },
        },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-arcgis-4");
  expect(config).toMatchObject({ source: "arcgis", arcgisItemId: "layer-12" });
});

test("createDatasetItem with source=arcgis posts an arcgis dataset payload", async () => {
  let postBody: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      postBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "cfg-9", kind: "dataset", itemId: "ds-9" });
    }),
  );
  const item = await makeClient().createDatasetItem({
    title: "Bâtiments (live)",
    owner: "alice",
    source: "arcgis",
    arcgisItemId: "layer-13",
  });
  expect(item.pk).toBe("ds-9");
  const config = postBody!.config as Record<string, unknown>;
  expect(config.dataset).toEqual({ source: "arcgis", arcgisItemId: "layer-13", columns: {} });
});

test("listFeatureLayers fetches /harvest/feature-layers", async () => {
  server.use(
    http.get("https://core.test/harvest/feature-layers", () =>
      HttpResponse.json({ layers: [{ id: "layer-1", title: "Bâtiments" }] }),
    ),
  );
  const layers = await makeClient().listFeatureLayers();
  expect(layers).toEqual([{ id: "layer-1", title: "Bâtiments" }]);
});

test("getAppConfig reads the app config (kind/theme/layout)", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5",
        itemId: "5",
        kind: "app",
        config: {
          kind: "app",
          theme: { primary: "#123" },
          dataSources: [],
          messages: [],
          layout: {
            type: "grid",
            breakpoints: {},
            items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.kind).toBe("app");
  expect(cfg.layout.items[0]).toMatchObject({ id: "w1", widget: "text" });
});

test("getAppConfig throws when the config has no layout", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5",
        itemId: "5",
        kind: "map",
        config: { kind: "map", layout: null },
      }),
    ),
  );
  await expect(makeClient().getAppConfig("5")).rejects.toThrow();
});

test("getAppConfig appends ?mode=runtime when a mode is passed", async () => {
  let requestedUrl = "";
  server.use(
    http.get("https://core.test/configs/by-item/5", ({ request }) => {
      requestedUrl = request.url;
      return HttpResponse.json({
        id: "cfg-5",
        itemId: "5",
        kind: "app",
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
        },
      });
    }),
  );
  await makeClient().getAppConfig("5", "runtime");
  expect(requestedUrl).toContain("mode=runtime");
});

test("saveAppConfig PUTs the app config by item", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/5", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "app", config: body });
    }),
  );
  await makeClient().saveAppConfig("5", {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  });
  expect(body.kind).toBe("app");
  expect(body.layout.type).toBe("grid");
});

test("getAppConfig/saveAppConfig round-trip interactions", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/9", () =>
      HttpResponse.json({
        config: {
          kind: "app",
          layout: { type: "grid", breakpoints: {}, items: [] },
          interactions: "auto",
        },
      }),
    ),
  );
  const config = await makeClient().getAppConfig("9");
  expect(config.interactions).toBe("auto");

  let putBody: Record<string, unknown> | null = null;
  server.use(
    http.put("https://core.test/configs/by-item/9", async ({ request }) => {
      putBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveAppConfig("9", { ...config, interactions: "manual" });
  expect(putBody!.interactions).toBe("manual");
});

test("featuresUrl builds the core items url", () => {
  const url = makeClient().featuresUrl({
    id: "d",
    type: "features",
    service: "core",
    layer: "public.parcs",
    query: {},
  });
  expect(url).toBe("https://core.test/collections/public.parcs/items");
});

test("queryDataSource maps a feature collection to records", async () => {
  server.use(
    http.get("https://core.test/collections/public.parcs/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: 1,
            properties: { nom: "Parc A" },
            geometry: { type: "Point", coordinates: [1, 2] },
          },
          { type: "Feature", properties: { nom: "Parc B" }, geometry: null },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "d",
    type: "features",
    service: "core",
    layer: "public.parcs",
    query: {},
  });
  expect(records).toHaveLength(2);
  expect(records[0]).toMatchObject({ id: 1, properties: { nom: "Parc A" } });
  // Missing feature id falls back to the index.
  expect(records[1].id).toBe(1);
});

test("queryDataSource returns inline records for a static source", async () => {
  const records = await makeClient().queryDataSource({
    id: "s",
    type: "static",
    service: "",
    layer: "",
    query: { records: [{ id: "a", properties: { v: 1 } }] },
  });
  expect(records).toEqual([{ id: "a", properties: { v: 1 } }]);
});

test("queryDataSource throws when the feature request fails", async () => {
  server.use(
    http.get(
      "https://core.test/collections/x/items",
      () => new HttpResponse(null, { status: 500 }),
    ),
  );
  await expect(
    makeClient().queryDataSource({
      id: "d",
      type: "features",
      service: "core",
      layer: "x",
      query: {},
    }),
  ).rejects.toThrow();
});

test("featuresUrl appends scalar query entries as sorted filter params", () => {
  const url = makeClient().featuresUrl({
    id: "d",
    type: "features",
    service: "core",
    layer: "parcs",
    query: { nom: "Parc A", limit: 10 },
  });
  expect(url).toBe("https://core.test/collections/parcs/items?limit=10&nom=Parc+A");
});

test("featuresUrl omits empty/nullish query entries", () => {
  const url = makeClient().featuresUrl({
    id: "d",
    type: "features",
    service: "core",
    layer: "parcs",
    query: { nom: "", ville: undefined as unknown as string },
  });
  expect(url).toBe("https://core.test/collections/parcs/items");
});

test("queryDataSource aggregates a statistics source by count per group", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: "region",
        rows: [
          { region: "Nord", value: 2 },
          { region: "Sud", value: 1 },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", agg: "count" },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 2 } },
    { id: "Sud", properties: { region: "Sud", value: 1 } },
  ]);
});

test("queryDataSource supports sum/avg/min/max aggregations per group", async () => {
  const run = async (agg: string) => {
    server.use(
      http.post("https://core.test/collections/villes/aggregate", () =>
        HttpResponse.json({
          categoryKey: "region",
          rows: [
            {
              region: "Nord",
              value: agg === "sum" ? 30 : agg === "avg" ? 15 : agg === "min" ? 10 : 20,
            },
            { region: "Sud", value: 6 },
          ],
        }),
      ),
    );
    return makeClient().queryDataSource({
      id: "s",
      type: "statistics",
      service: "core",
      layer: "villes",
      query: { groupBy: "region", agg, field: "pop" },
    });
  };
  expect(await run("sum")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 30 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("avg")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 15 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("min")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 10 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("max")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 20 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
});

test("queryDataSource pivots a statistics source into one column per split value", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: "region",
        rows: [
          { region: "Nord", "2025": 10, "2026": 12 },
          { region: "Sud", "2025": 5, "2026": 0 },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
    { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 0 } },
  ]);
});

test("queryDataSource produces one wide column per measure", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: "region",
        rows: [{ region: "Nord", Population: 30, avg_rev: 6 }],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: {
      groupBy: "region",
      measures: [
        { field: "pop", agg: "sum", label: "Population" },
        { field: "rev", agg: "avg" },
      ],
    },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", Population: 30, avg_rev: 6 } },
  ]);
});

test("queryDataSource sends a bbox query key as body.bbox, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "region", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", agg: "count", bbox: "1,2,3,4" },
  });
  expect(posted!.bbox).toEqual([1, 2, 3, 4]);
  expect(posted!.filters).toBeUndefined();
});

test("queryDataSource sends a geomIntersects query key as body.geomIntersects", async () => {
  const geom = { type: "Point", coordinates: [1, 2] };
  let posted: { geomIntersects?: unknown } | undefined;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as { geomIntersects?: unknown };
      return HttpResponse.json({ categoryKey: "group", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "src-1",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", agg: "count", geomIntersects: geom },
  });
  expect(posted!.geomIntersects).toEqual(geom);
});

test("queryDataSource sends a bucket query key as body.bucket, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "annee", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "annee", bucket: "week", agg: "count" },
  });
  expect(posted!.bucket).toBe("week");
  expect(posted!.filters).toBeUndefined();
});

test("queryDataSource sends an array groupBy as-is in the aggregate request body", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: ["region", "annee"], rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "count" },
  });
  expect(posted!.groupBy).toEqual(["region", "annee"]);
});

test("queryDataSource builds a composite id when categoryKey is a multi-field array", async () => {
  server.use(
    http.post("https://core.test/collections/villes/aggregate", () =>
      HttpResponse.json({
        categoryKey: ["region", "annee"],
        rows: [{ region: "Nord", annee: "2025", value: 10 }],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: ["region", "annee"], agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord|2025", properties: { region: "Nord", annee: "2025", value: 10 } },
  ]);
});

test("queryDataSource sends a bins query key as body.bins, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "bucketIndex", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { field: "pop", bins: 5 },
  });
  expect(posted!.bins).toBe(5);
  expect(posted!.filters).toBeUndefined();
});

test("queryDataSource sends a percentile query's p as body.p, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "region", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", agg: "percentile", field: "pop", p: 90 },
  });
  expect(posted!.p).toBe(90);
  expect(posted!.filters).toBeUndefined();
});

test("queryDataSource carries a per-measure p into body.measures[i].p", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "region", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: {
      groupBy: "region",
      measures: [{ field: "pop", agg: "percentile", p: 90 }],
    },
  });
  expect(posted!.measures).toEqual([{ field: "pop", agg: "percentile", label: undefined, p: 90 }]);
});

test("sampleCollectionField posts sample+field and returns bare numeric values", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/communes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "value", rows: [{ value: 1 }, { value: 2.5 }] });
    }),
  );
  const values = await makeClient().sampleCollectionField("communes", "population", 500);
  expect(values).toEqual([1, 2.5]);
  expect(posted).toEqual({ field: "population", sample: 500 });
});

test("uploadMapIcon POSTs multipart form data with the bearer token", async () => {
  let method: string | null = null;
  let auth: string | null = null;
  let contentType: string | null = null;
  server.use(
    http.post("https://core.test/map-icons", ({ request }) => {
      method = request.method;
      auth = request.headers.get("authorization");
      contentType = request.headers.get("content-type");
      return HttpResponse.json(
        {
          id: "i1",
          title: "Logo",
          category: "generic",
          contentType: "image/png",
          createdAt: "2026-08-27T00:00:00Z",
        },
        { status: 201 },
      );
    }),
  );
  const created = await makeClient("abc").uploadMapIcon(
    new File(["x"], "logo.png", { type: "image/png" }),
    "Logo",
    "generic",
  );
  expect(created.id).toBe("i1");
  expect(method).toBe("POST");
  expect(auth).toBe("Bearer abc");
  // Le vrai runtime (navigateur, ou fetch Node natif hors jsdom — vérifié
  // par une sonde node:http jetable) pose bien
  // "multipart/form-data; boundary=…" quand le Content-Type n'est pas
  // fixé à la main. Dans CET environnement de test (jsdom + interception
  // MSW), le FormData de jsdom n'est pas reconnu par le dérivateur
  // automatique de boundary et l'en-tête observé retombe sur
  // "text/plain;charset=UTF-8" — mesuré, pas un défaut de l'implémentation
  // (confirmé : un Content-Type posé à la main, lui, est bien observé tel
  // quel par MSW). La régression réelle à garder — poser Content-Type à la
  // main et donc écraser le boundary que la plateforme ajoute — reste
  // détectable ici :
  expect(contentType).not.toMatch(/^application\/json/);
});

test("listMapIcons reads the tenant library back", async () => {
  const icon = {
    id: "i1",
    title: "Logo",
    category: "generic",
    contentType: "image/png",
    createdAt: "2026-08-27T00:00:00Z",
  };
  server.use(http.get("https://core.test/map-icons", () => HttpResponse.json([icon])));
  expect(await makeClient("abc").listMapIcons()).toEqual([icon]);
});

test("deleteMapIcon tolerates the 204 the core returns", async () => {
  let method: string | null = null;
  server.use(
    http.delete("https://core.test/map-icons/:iconId", ({ request }) => {
      method = request.method;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  // request() fait `if (res.status === 204) return undefined as T`
  // (itemClient.ts:325-343) : la méthode résout sur undefined, sans lever.
  await expect(makeClient("abc").deleteMapIcon("i1")).resolves.toBeUndefined();
  expect(method).toBe("DELETE");
});

// La route du fichier est gardée par bearer token : une URL nue passée à
// `new Image().src` ne porte aucun en-tête et prendrait un 401 (constat 4.4).
test("fetchMapIconBlob attaches the bearer token and returns the bytes", async () => {
  let auth: string | null = null;
  let url: string | null = null;
  server.use(
    http.get("https://core.test/map-icons/:iconId/file", ({ request }) => {
      auth = request.headers.get("authorization");
      url = request.url;
      return new HttpResponse("PNGBYTES", { headers: { "Content-Type": "image/png" } });
    }),
  );
  const blob = await makeClient("tok").fetchMapIconBlob("i1");
  expect(await blob.text()).toBe("PNGBYTES");
  expect(auth).toBe("Bearer tok");
  expect(url).toBe("https://core.test/map-icons/i1/file");
});

test("fetchMapIconBlob throws on a non-ok response", async () => {
  server.use(
    http.get(
      "https://core.test/map-icons/:iconId/file",
      () => new HttpResponse(null, { status: 404 }),
    ),
  );
  await expect(makeClient("tok").fetchMapIconBlob("i1")).rejects.toThrow(/404/);
});

test("featuresUrl strips reserved statistics keys but keeps filter params", () => {
  const url = makeClient().featuresUrl({
    id: "s",
    type: "statistics",
    service: "core",
    layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop", annee_filtre: 2026 },
  });
  expect(url).toBe("https://core.test/collections/villes/items?annee_filtre=2026");
});

test("getAppConfig passes through the pages array when present", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5",
        itemId: "5",
        kind: "app",
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
          pages: [
            { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } },
          ],
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.pages).toEqual([
    { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } },
  ]);
});

test("saveAppConfig PUTs the pages array when present", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/5", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "app", config: body });
    }),
  );
  await makeClient().saveAppConfig("5", {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [{ id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } }],
  });
  expect(body.pages).toHaveLength(1);
  expect(body.pages[0].name).toBe("Accueil");
});

test("getAppConfig passes through the variables array when present", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5",
        itemId: "5",
        kind: "app",
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
          variables: [{ id: "v1", name: "message", initialValue: "salut" }],
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.variables).toEqual([{ id: "v1", name: "message", initialValue: "salut" }]);
});

test("saveAppConfig PUTs the variables array when present", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/5", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "app", config: body });
    }),
  );
  await makeClient().saveAppConfig("5", {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
    variables: [{ id: "v1", name: "message", initialValue: "salut" }],
  });
  expect(body.variables).toHaveLength(1);
  expect(body.variables[0].name).toBe("message");
});

test("createConfigItem seeds the layout from a template when templateId is given", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient().createConfigItem({
    kind: "app",
    title: "T",
    owner: "o",
    templateId: "two-column",
  });
  expect(body.config.layout.items).toHaveLength(2);
  expect(body.config.layout.items[0].widget).toBe("text");
});

test("createConfigItem falls back to an empty layout when templateId is unknown", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient().createConfigItem({
    kind: "app",
    title: "T",
    owner: "o",
    templateId: "does-not-exist",
  });
  expect(body.config.layout).toEqual({ type: "grid", breakpoints: {}, items: [] });
});

test("getCollectionSchema returns the introspected fields", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/schema", () =>
      HttpResponse.json({
        collection: "incidents",
        pk: "id",
        geometry: { column: "geom", type: "Point", srid: 4326 },
        fields: [
          { name: "titre", type: "string", required: true, maxLength: 120 },
          { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
          { name: "nb_victimes", type: "integer", required: false },
        ],
      }),
    ),
  );
  const schema = await makeClient().getCollectionSchema("incidents");
  expect(schema.geometry).toEqual({ column: "geom", type: "Point", srid: 4326 });
  expect(schema.fields).toHaveLength(3);
  expect(schema.fields[0]).toEqual({
    name: "titre",
    type: "string",
    required: true,
    maxLength: 120,
  });
});

test("createFeature sends a GeoJSON Feature with the bearer token and returns the new id", async () => {
  let auth: string | null = null;
  let body: unknown;
  server.use(
    http.post("https://core.test/collections/incidents/items", async ({ request }) => {
      auth = request.headers.get("authorization");
      body = await request.json();
      return HttpResponse.json({ id: 42 }, { status: 201 });
    }),
  );
  const result = await makeClient("abc").createFeature("incidents", {
    type: "Feature",
    properties: { titre: "Fuite d'eau" },
    geometry: null,
  });
  expect(auth).toBe("Bearer abc");
  expect(body).toEqual({ type: "Feature", properties: { titre: "Fuite d'eau" }, geometry: null });
  expect(result).toEqual({ id: 42 });
});

test("createFeature throws FeatureValidationError with field errors on 400", async () => {
  server.use(
    http.post("https://core.test/collections/incidents/items", () =>
      HttpResponse.json(
        {
          errors: [{ field: "titre", code: "missing_required", message: "'titre' is required" }],
        },
        { status: 400 },
      ),
    ),
  );
  const err = await makeClient()
    .createFeature("incidents", { type: "Feature", properties: {}, geometry: null })
    .catch((e) => e);
  expect(err).toBeInstanceOf(FeatureValidationError);
  expect((err as FeatureValidationError).errors).toEqual([
    { field: "titre", code: "missing_required", message: "'titre' is required" },
  ]);
});

test("createFeature throws a plain Error with the server message on 403", async () => {
  server.use(
    http.post("https://core.test/collections/incidents/items", () =>
      HttpResponse.json({ detail: "collection is not editable" }, { status: 403 }),
    ),
  );
  await expect(
    makeClient().createFeature("incidents", { type: "Feature", properties: {}, geometry: null }),
  ).rejects.toThrow("collection is not editable");
});

test("updateFeature sends a PUT and resolves on 204", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/collections/incidents/items/7", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().updateFeature("incidents", "7", {
    type: "Feature",
    properties: { titre: "Mise à jour" },
    geometry: null,
  });
  expect(body).toEqual({ type: "Feature", properties: { titre: "Mise à jour" }, geometry: null });
});

test("updateFeature throws a plain Error with the server message on 404", async () => {
  server.use(
    http.put("https://core.test/collections/incidents/items/999", () =>
      HttpResponse.json({ detail: "feature not found" }, { status: 404 }),
    ),
  );
  await expect(
    makeClient().updateFeature("incidents", "999", {
      type: "Feature",
      properties: {},
      geometry: null,
    }),
  ).rejects.toThrow("feature not found");
});

test("deleteFeature sends a DELETE and resolves on 204", async () => {
  let method: string | null = null;
  server.use(
    http.delete("https://core.test/collections/incidents/items/7", ({ request }) => {
      method = request.method;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteFeature("incidents", "7");
  expect(method).toBe("DELETE");
});

test("getCollectionPermission returns permissions.write", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({
        id: "incidents",
        title: "Incidents",
        permissions: { read: true, write: true, delete: false, share: true },
      }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(true);
});

test("getCollectionPermission defaults to false when permissions is absent", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({ id: "incidents", title: "Incidents" }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(false);
});

test("getCollection returns the full collection metadata for a single id", async () => {
  server.use(
    http.get("https://core.test/collections/parcs", () =>
      HttpResponse.json({
        id: "parcs",
        title: "Parcs",
        description: "Parcs publics",
        tableName: "parcs",
        isPublic: true,
        editable: false,
        geometryType: null,
        srid: null,
        pkColumn: "id",
        permissions: { read: true, write: false, delete: false, share: true },
        featureCount: 2,
        owner: null,
      }),
    ),
  );
  const col = await makeClient(undefined).getCollection("parcs");
  expect(col).toEqual({
    id: "parcs",
    title: "Parcs",
    description: "Parcs publics",
    tableName: "parcs",
    isPublic: true,
    editable: false,
    geometryType: null,
    srid: null,
    pkColumn: "id",
    permissions: { read: true, write: false, delete: false, share: true },
    featureCount: 2,
    owner: null,
  });
});

test("getCollection propagates a 404 for a non-public or unknown collection", async () => {
  server.use(
    http.get("https://core.test/collections/private-x", () =>
      HttpResponse.json({ detail: "collection not found" }, { status: 404 }),
    ),
  );
  await expect(makeClient(undefined).getCollection("private-x")).rejects.toThrow();
});

test("createConfigItem seeds dataSources and messages from a template that defines them", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient().createConfigItem({
    kind: "app",
    title: "T",
    owner: "o",
    templateId: "application-de-saisie",
  });
  expect(body.config.dataSources).toHaveLength(1);
  expect(body.config.dataSources[0]).toMatchObject({ type: "features", layer: "incidents" });
  expect(body.config.messages).toHaveLength(1);
});

test("createConfigItem seeds pages and navigationMode from a story template", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient().createConfigItem({
    kind: "app",
    title: "T",
    owner: "o",
    templateId: "story-cartographique",
  });
  expect(body.config.navigationMode).toBe("story");
  expect(body.config.pages).toHaveLength(3);
  expect(body.config.pages[0].onEnter[0].action).toBe("flyTo");
  // layout top-level reflète la première page (le cœur l'exige pour app/dashboard)
  expect(body.config.layout.items.length).toBeGreaterThan(0);
});

test("listAllExtensions requests all=true and keeps the enabled flag", async () => {
  let url: string | null = null;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      });
    }),
  );
  const result = await makeClient().listAllExtensions();
  expect(url).toContain("all=true");
  expect(result).toEqual([
    {
      type: "acme.gauge",
      tag: "gauge-extension-widget",
      label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js",
      props: [],
      events: [],
      actions: [],
      defaultSize: { w: 2, h: 2 },
      permissions: { collections: "all" },
      enabled: false,
    },
  ]);
});

test("setExtensionEnabled PATCHes the extension with the new enabled value", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "acme.gauge" });
    }),
  );
  await makeClient().setExtensionEnabled("acme.gauge", false);
  expect(body).toEqual({ enabled: false });
});

test("launchAdminTool POSTs to /admin-tools/launch/{tool} and returns the url", async () => {
  server.use(
    http.post("https://core.test/admin-tools/launch/martin", () =>
      HttpResponse.json({ url: "https://core.test/admin-tools/session/martin?_at=abc" }),
    ),
  );
  const result = await makeClient().launchAdminTool("martin");
  expect(result.url).toBe("https://core.test/admin-tools/session/martin?_at=abc");
});

test("listCollections returns the admin collection shape including owner", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents",
            title: "Incidents",
            description: "",
            tableName: "incidents",
            isPublic: false,
            editable: true,
            geometryType: "Point",
            srid: 4326,
            pkColumn: "id",
            permissions: { read: true, write: true, delete: false, share: true },
            featureCount: 3,
            owner: "admin",
          },
        ],
      }),
    ),
  );
  const result = await makeClient().listCollections();
  expect(result).toEqual([
    {
      id: "incidents",
      title: "Incidents",
      description: "",
      tableName: "incidents",
      isPublic: false,
      editable: true,
      geometryType: "Point",
      srid: 4326,
      pkColumn: "id",
      permissions: { read: true, write: true, delete: false, share: true },
      featureCount: 3,
      owner: "admin",
    },
  ]);
});

test("listCandidateTables returns the candidates array as-is", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
  );
  const result = await makeClient().listCandidateTables();
  expect(result).toEqual([
    { tableName: "widgets", registrable: false, reason: "table has no primary key" },
    {
      tableName: "points_interet",
      registrable: true,
      geometryType: "Point",
      srid: 4326,
      columnCount: 3,
    },
  ]);
});

test("createCollection POSTs the input and returns the created collection", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/collections", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
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
        owner: "admin",
      });
    }),
  );
  const result = await makeClient().createCollection({
    tableName: "points_interet",
    title: "Points d'intérêt",
  });
  expect(body).toEqual({ tableName: "points_interet", title: "Points d'intérêt" });
  expect(result.id).toBe("points_interet");
});

test("updateCollection PATCHes the patch and returns the updated collection", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "incidents",
        title: "Incidents (v2)",
        description: "",
        tableName: "incidents",
        isPublic: true,
        editable: true,
        geometryType: "Point",
        srid: 4326,
        pkColumn: "id",
        permissions: { read: true, write: true, delete: false, share: true },
        featureCount: 3,
        owner: "admin",
      });
    }),
  );
  const result = await makeClient().updateCollection("incidents", {
    title: "Incidents (v2)",
    isPublic: true,
  });
  expect(body).toEqual({ title: "Incidents (v2)", isPublic: true });
  expect(result.title).toBe("Incidents (v2)");
});

test("deleteCollection DELETEs the collection", async () => {
  let called = false;
  server.use(
    http.delete("https://core.test/collections/incidents", () => {
      called = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteCollection("incidents");
  expect(called).toBe(true);
});

test("getCollectionSharing passes through the core's Sharing shape directly", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [{ groupId: "g1", role: "editor" }] }),
    ),
  );
  const result = await makeClient().getCollectionSharing("incidents");
  expect(result).toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
});

test("setCollectionSharing PUTs the sharing object as-is", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ public: false, groups: [] });
    }),
  );
  await makeClient().setCollectionSharing("incidents", {
    public: false,
    groups: [{ groupId: "g1", role: "viewer" }],
  });
  expect(body).toEqual({ public: false, groups: [{ groupId: "g1", role: "viewer" }] });
});

test("getItemBySlug requests /public/sites/{slug} and returns the item", async () => {
  let url: string | null = null;
  server.use(
    http.get("https://core.test/public/sites/mon-portail", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        pk: "s1",
        resourceType: "site",
        slug: "mon-portail",
        title: "Portail",
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "",
        configId: "cfg-1",
        isPublished: true,
      });
    }),
  );
  const item = await makeClient().getItemBySlug("mon-portail");
  expect(url).toBe("https://core.test/public/sites/mon-portail");
  expect(item.slug).toBe("mon-portail");
  expect(item.pk).toBe("s1");
});

test("getItemBySlug propagates a 404 as a rejection", async () => {
  server.use(
    http.get(
      "https://core.test/public/sites/nexiste-pas",
      () => new HttpResponse(null, { status: 404 }),
    ),
  );
  await expect(makeClient().getItemBySlug("nexiste-pas")).rejects.toThrow();
});

test("getPublicAppConfig reads the wrapped ConfigRead shape (config.layout, not top-level)", async () => {
  server.use(
    http.get("https://core.test/public/configs/by-item/s1", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "s1",
        kind: "site",
        version: 1,
        config: {
          kind: "site",
          theme: {},
          dataSources: [],
          messages: [],
          pages: [],
          layout: {
            type: "grid",
            breakpoints: {},
            items: [
              { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bienvenue" } },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getPublicAppConfig("s1");
  expect(cfg.layout).toBeDefined();
  expect(cfg.layout.items[0]).toMatchObject({ id: "w1", widget: "text" });
});

test("getPublicAppConfig throws when the config has no layout", async () => {
  server.use(
    http.get("https://core.test/public/configs/by-item/s1", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "s1",
        kind: "site",
        config: { kind: "site", layout: null },
      }),
    ),
  );
  await expect(makeClient().getPublicAppConfig("s1")).rejects.toThrow();
});

test("createConfigItem transmits the slug in the POST body when given", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        itemId: "s1",
        kind: "site",
        version: 1,
        config: body.config,
      });
    }),
  );
  const item = await makeClient().createConfigItem({
    kind: "site",
    title: "Portail",
    owner: "alice",
    slug: "mon-portail",
  });
  expect(body.slug).toBe("mon-portail");
  expect(body.config.kind).toBe("site");
  expect(item.slug).toBe("mon-portail");
});

test("createConfigItem omits slug from the POST body when not given", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "cfg-1",
        itemId: "1",
        kind: "app",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o" });
  expect(body).not.toHaveProperty("slug");
});

test("listPublicItems calls GET /public/items with type/tag/page/pageSize", async () => {
  let url: string | null = null;
  server.use(
    http.get("https://core.test/public/items", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 6 });
    }),
  );
  await makeClient().listPublicItems({ type: "app", tag: "risques", page: 1, pageSize: 6 });
  expect(url).toContain("type=app");
  expect(url).toContain("tag=risques");
  expect(url).toContain("page=1");
  expect(url).toContain("pageSize=6");
});

test("listPublicItems round-trips keywords from the response", async () => {
  server.use(
    http.get("https://core.test/public/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "8",
            resourceType: "app",
            title: "Carte des risques",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: null,
            isPublished: true,
            keywords: ["risques"],
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  const page = await makeClient().listPublicItems();
  expect(page.items[0].keywords).toEqual(["risques"]);
});

test("runAnalyticsSql posts { sql } and returns columns/rows/truncated", async () => {
  let auth: string | null = null;
  let body: unknown;
  server.use(
    http.post("https://core.test/analytics/sql", async ({ request }) => {
      auth = request.headers.get("authorization");
      body = await request.json();
      return HttpResponse.json({ columns: ["nom"], rows: [["Alice"]], truncated: false });
    }),
  );
  const result = await makeClient("abc").runAnalyticsSql("select nom from personnes");
  expect(auth).toBe("Bearer abc");
  expect(body).toEqual({ sql: "select nom from personnes" });
  expect(result).toEqual({ columns: ["nom"], rows: [["Alice"]], truncated: false });
});

test("runAnalyticsSql throws SqlQueryError with the server message on 400", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json(
        {
          errors: [
            {
              field: "sql",
              code: "sql_error",
              message: "Binder Error: table 'x' does not exist",
            },
          ],
        },
        { status: 400 },
      ),
    ),
  );
  const err = await makeClient()
    .runAnalyticsSql("select * from x")
    .catch((e) => e);
  expect(err).toBeInstanceOf(SqlQueryError);
  expect((err as SqlQueryError).message).toBe("Binder Error: table 'x' does not exist");
});

test("runAnalyticsSql throws a plain Error on 403 (non-analyst)", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ detail: "analyst role required" }, { status: 403 }),
    ),
  );
  await expect(makeClient().runAnalyticsSql("select 1")).rejects.toThrow(/403/);
});

test("createPipelineItem posts a pipeline payload and returns a pipeline Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-p1", kind: "pipeline", itemId: "p-1" }, { status: 201 });
    }),
  );
  const payload = {
    nodes: [
      {
        id: "r1",
        kind: "reader" as const,
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
      },
      {
        id: "w1",
        kind: "writer" as const,
        op: "writer.collection",
        x: 200,
        y: 0,
        params: { collectionId: "villes_propres" },
      },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const item = await makeClient().createPipelineItem({
    title: "Nettoyer villes",
    owner: "alice",
    pipeline: payload,
  });
  expect(body.config).toEqual({ version: 1, kind: "pipeline", pipeline: payload });
  expect(item).toMatchObject({
    pk: "p-1",
    resourceType: "pipeline",
    title: "Nettoyer villes",
    configId: "cfg-p1",
  });
});

test("getPipelineConfig reads the pipeline payload from the by-item config", async () => {
  const payload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "villes" },
      },
    ],
    edges: [],
  };
  server.use(
    http.get("https://core.test/configs/by-item/p-2", () =>
      HttpResponse.json({
        id: "cfg-p2",
        itemId: "p-2",
        kind: "pipeline",
        config: { kind: "pipeline", pipeline: payload },
      }),
    ),
  );
  const cfg = await makeClient().getPipelineConfig("p-2");
  expect(cfg).toEqual(payload);
});

test("getPipelineConfig throws when the config has no pipeline payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/p-3", () =>
      HttpResponse.json({ id: "cfg-p3", itemId: "p-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getPipelineConfig("p-3")).rejects.toThrow();
});

test("savePipelineConfig PUTs the pipeline payload wrapped in a kind=pipeline envelope", async () => {
  let method = "";
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/p-4", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  const payload = { nodes: [], edges: [] };
  await makeClient().savePipelineConfig("p-4", payload);
  expect(method).toBe("PUT");
  expect(body).toEqual({ version: 1, kind: "pipeline", pipeline: payload });
});

test("getPipelineOps returns the op catalogue as-is", async () => {
  const catalog = {
    "reader.collection": { kind: "reader", paramsSchema: { properties: {}, required: [] } },
  };
  server.use(http.get("https://core.test/pipelines/ops", () => HttpResponse.json(catalog)));
  const result = await makeClient().getPipelineOps();
  expect(result).toEqual(catalog);
});

test("runPipeline posts with no body and returns the runId", async () => {
  server.use(
    http.post("https://core.test/pipelines/p-5/run", () =>
      HttpResponse.json({ runId: "run-1" }, { status: 202 }),
    ),
  );
  const result = await makeClient().runPipeline("p-5");
  expect(result).toEqual({ runId: "run-1" });
});

test("getPipelineRuns returns the run history", async () => {
  const runs = [
    {
      id: "run-1",
      status: "succeeded",
      startedAt: "2026-08-06T10:00:00Z",
      finishedAt: "2026-08-06T10:00:05Z",
      error: null,
      nodeStats: {},
    },
  ];
  server.use(http.get("https://core.test/pipelines/p-6/runs", () => HttpResponse.json(runs)));
  const result = await makeClient().getPipelineRuns("p-6");
  expect(result).toEqual(runs);
});

test("previewPipeline posts upTo as a query param and returns the row list", async () => {
  let url = "";
  server.use(
    http.post("https://core.test/pipelines/p-7/preview", ({ request }) => {
      url = request.url;
      return HttpResponse.json([{ id: 1, pop: 1200 }]);
    }),
  );
  const rows = await makeClient().previewPipeline("p-7", "r1");
  expect(url).toContain("upTo=r1");
  expect(rows).toEqual([{ id: 1, pop: 1200 }]);
});

test("createAlertRuleItem posts a kind=alert config and returns the item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-a1", kind: "alert", itemId: "a-1" }, { status: 201 });
    }),
  );
  const alert = {
    datasetItemId: "ds-1",
    query: { agg: "count" },
    condition: { expr: "value > 100" },
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "webhook" as const, url: "https://example.test/hook" }],
    messageTemplate: "Alert {ruleName}: value={value} ({state})",
  };
  const item = await makeClient().createAlertRuleItem({
    title: "High counts",
    owner: "alice",
    alert,
  });
  expect(body.config).toEqual({ version: 1, kind: "alert", alert });
  expect(item).toMatchObject({
    pk: "a-1",
    resourceType: "alert",
    title: "High counts",
    configId: "cfg-a1",
  });
});

test("getAlertRuleConfig reads the alert payload from the by-item config", async () => {
  const alert = {
    datasetItemId: "ds-1",
    query: { agg: "count" },
    condition: { expr: "value > 100" },
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "webhook" as const, url: "https://example.test/hook" }],
    messageTemplate: "Alert {ruleName}: value={value} ({state})",
  };
  server.use(
    http.get("https://core.test/configs/by-item/a-2", () =>
      HttpResponse.json({
        id: "cfg-a2",
        itemId: "a-2",
        kind: "alert",
        config: { kind: "alert", alert },
      }),
    ),
  );
  const cfg = await makeClient().getAlertRuleConfig("a-2");
  expect(cfg).toEqual(alert);
});

test("getAlertRuleConfig throws when the config has no alert payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/a-3", () =>
      HttpResponse.json({ id: "cfg-a3", itemId: "a-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getAlertRuleConfig("a-3")).rejects.toThrow();
});

test("saveAlertRuleConfig PUTs the alert payload wrapped in a kind=alert envelope", async () => {
  let method = "";
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/a-4", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  const alert = {
    datasetItemId: "ds-1",
    query: { agg: "count" },
    condition: { expr: "value > 100" },
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "webhook" as const, url: "https://example.test/hook" }],
    messageTemplate: "Alert {ruleName}: value={value} ({state})",
  };
  await makeClient().saveAlertRuleConfig("a-4", alert);
  expect(method).toBe("PUT");
  expect(body).toEqual({ version: 1, kind: "alert", alert });
});

test("listAlertRulesForDataset calls GET /datasets/{id}/alerts", async () => {
  server.use(
    http.get("https://core.test/datasets/ds-1/alerts", () =>
      HttpResponse.json([{ itemId: "a-1", title: "High counts" }]),
    ),
  );
  const rules = await makeClient().listAlertRulesForDataset("ds-1");
  expect(rules).toEqual([{ itemId: "a-1", title: "High counts" }]);
});

test("getAlertEvaluations calls GET /alerts/{id}/evaluations", async () => {
  server.use(
    http.get("https://core.test/alerts/a-1/evaluations", () =>
      HttpResponse.json([
        {
          id: "e1",
          value: 150,
          state: "firing",
          transitioned: true,
          error: null,
          createdAt: "2026-08-07T00:00:00Z",
        },
      ]),
    ),
  );
  const evaluations = await makeClient().getAlertEvaluations("a-1");
  expect(evaluations[0].state).toBe("firing");
});

test("exportDataSource posts the aggregate body and extracts the filename for a statistics source", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/collections/parcs/export", async ({ request }) => {
      posted = await request.json();
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("csv");
      return new HttpResponse("region,count\nNord,3\n", {
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="parcs-20260807-120000.csv"',
        },
      });
    }),
  );
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "parcs",
    query: { groupBy: "region", agg: "count" },
  };
  const { blob, filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("parcs-20260807-120000.csv");
  expect(await blob.text()).toBe("region,count\nNord,3\n");
  expect(posted).toEqual({ groupBy: "region", agg: "count" });
});

test("exportDataSource GETs the items-export route for a non-statistics source", async () => {
  server.use(
    http.get("https://core.test/collections/parcs/export/items", ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("format")).toBe("geojson");
      return new HttpResponse('{"type":"FeatureCollection","features":[]}', {
        headers: {
          "Content-Type": "application/geo+json",
          "Content-Disposition": 'attachment; filename="parcs.geojson"',
        },
      });
    }),
  );
  const source: DataSource = {
    id: "s1",
    type: "features",
    service: "core",
    layer: "parcs",
    query: {},
  };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("parcs.geojson");
});

test("exportDataSource dispatches to the arcgis export route for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds1", () =>
      HttpResponse.json({
        config: { dataset: { source: "arcgis", arcgisItemId: "ext1", columns: {} } },
      }),
    ),
    http.post(
      "https://core.test/datasets/ds1/arcgis/export",
      () =>
        new HttpResponse("a,b\n1,2\n", {
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition": 'attachment; filename="x.csv"',
          },
        }),
    ),
  );
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "",
    datasetId: "ds1",
    query: {},
  };
  const { filename } = await makeClient("tok").exportDataSource(source, "csv");
  expect(filename).toBe("x.csv");
});

test("exportDataSource falls back to a generic filename when Content-Disposition is missing", async () => {
  server.use(
    http.get(
      "https://core.test/collections/parcs/export/items",
      () => new HttpResponse("[]", { headers: { "Content-Type": "application/geo+json" } }),
    ),
  );
  const source: DataSource = {
    id: "s1",
    type: "features",
    service: "core",
    layer: "parcs",
    query: {},
  };
  const { filename } = await makeClient("tok").exportDataSource(source, "geojson");
  expect(filename).toBe("export");
});

test("downloadAttachment sends the bearer token and returns the blob and filename", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://core.test/collections/col1/items/f1/attachments/att1/file", ({ request }) => {
      auth = request.headers.get("authorization");
      return new HttpResponse("binary-content", {
        headers: {
          "Content-Type": "image/jpeg",
          "Content-Disposition": 'attachment; filename="photo.jpg"',
        },
      });
    }),
  );
  const { blob, filename } = await makeClient("tok").downloadAttachment("col1", "f1", "att1");
  expect(auth).toBe("Bearer tok");
  expect(filename).toBe("photo.jpg");
  expect(await blob.text()).toBe("binary-content");
});

test("getMapConfig reads printLayout from the top level of the config, not nested under map", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        config: {
          kind: "map",
          map: { basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [] },
          printLayout: {
            pageSize: "a3",
            orientation: "landscape",
            showLegend: true,
            showScaleBar: true,
            showNorthArrow: false,
          },
        },
      }),
    ),
  );
  const config = await makeClient().getMapConfig("77");
  expect(config.printLayout).toEqual({
    pageSize: "a3",
    orientation: "landscape",
    showLegend: true,
    showScaleBar: true,
    showNorthArrow: false,
  });
});

test("saveMapConfig sends printLayout back at the top level, sibling of map", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/77", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveMapConfig("77", {
    basemap: { style: "s" },
    view: { center: [0, 0], zoom: 1 },
    layers: [],
    printLayout: {
      pageSize: "a4",
      orientation: "portrait",
      showLegend: false,
      showScaleBar: false,
      showNorthArrow: false,
    },
  });
  expect(body.printLayout).toEqual({
    pageSize: "a4",
    orientation: "portrait",
    showLegend: false,
    showScaleBar: false,
    showNorthArrow: false,
  });
  expect(body.map).toBeDefined();
  expect(body.map.printLayout).toBeUndefined();
});

test("getAppConfig reads printLayout", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
          printLayout: { pageSize: "a4", orientation: "portrait", title: "Rapport" },
        },
      }),
    ),
  );
  const config = await makeClient().getAppConfig("5");
  expect(config.printLayout).toEqual({ pageSize: "a4", orientation: "portrait", title: "Rapport" });
});

test("saveAppConfig round-trips printLayout without dropping it", async () => {
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/5", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  await makeClient().saveAppConfig("5", {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
    printLayout: { pageSize: "a3", orientation: "landscape" },
  });
  expect(body.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
});

test("createExport POSTs itemId and format", async () => {
  let body: any;
  let method = "";
  server.use(
    http.post("https://core.test/export", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({ jobId: "job-1" }, { status: 202 });
    }),
  );
  const result = await makeClient().createExport("pk-1", "pdf");
  expect(result).toEqual({ jobId: "job-1" });
  expect(method).toBe("POST");
  expect(body).toEqual({ itemId: "pk-1", format: "pdf" });
});

test("getExportJob GETs the job status by id", async () => {
  server.use(
    http.get("https://core.test/export/jobs/job-1", () =>
      HttpResponse.json({
        id: "job-1",
        status: "done",
        resultUrl: "https://minio.test/x.pdf",
        error: null,
      }),
    ),
  );
  const job = await makeClient().getExportJob("job-1");
  expect(job).toEqual({
    id: "job-1",
    status: "done",
    resultUrl: "https://minio.test/x.pdf",
    error: null,
  });
});

test("createEmptyCollection posts to /collections/empty and returns the created id", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/collections/empty", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "query_abc123" }, { status: 201 });
    }),
  );
  const result = await makeClient().createEmptyCollection({
    title: "Ma requête",
    columns: [{ name: "commune", sqlType: "text" }],
    geometryType: null,
    srid: null,
  });
  expect(body).toEqual({
    title: "Ma requête",
    columns: [{ name: "commune", sqlType: "text" }],
    geometryType: null,
    srid: null,
  });
  expect(result).toEqual({ id: "query_abc123" });
});

test("createTileset3DUpload posts filename/title and returns jobId", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
  );
  const result = await makeClient("abc").createTileset3DUpload({
    filename: "city.zip",
    title: "Ville",
  });
  expect(result).toEqual({ jobId: "job-1" });
  expect(body).toEqual({ filename: "city.zip", title: "Ville" });
});

test("presignTileset3DUploadPart posts to the job/part route and returns an upload URL", async () => {
  server.use(
    http.post("https://core.test/tileset3d/uploads/job-1/parts/2/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-2" }),
    ),
  );
  const result = await makeClient("abc").presignTileset3DUploadPart("job-1", 2);
  expect(result).toEqual({ uploadUrl: "https://minio.test/part-2" });
});

test("completeTileset3DUpload posts the parts list", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads/job-1/complete", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient("abc").completeTileset3DUpload("job-1", [{ partNumber: 1, etag: '"abc"' }]);
  expect(body).toEqual({ parts: [{ partNumber: 1, etag: '"abc"' }] });
});

test("getTileset3DUploadJob returns the job status", async () => {
  server.use(
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" }),
    ),
  );
  const result = await makeClient("abc").getTileset3DUploadJob("job-1");
  expect(result).toEqual({ status: "done", errorMessage: null, itemId: "item-1" });
});

test("listHostedTerrain3DSources lists terrain3d items via /items", async () => {
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      expect(new URL(request.url).searchParams.get("type")).toBe("terrain3d");
      return HttpResponse.json({ items: [{ pk: "t-1", title: "Relief du massif" }] });
    }),
  );
  const sources = await makeClient("abc").listHostedTerrain3DSources();
  expect(sources).toEqual([{ id: "t-1", title: "Relief du massif" }]);
});

test("presignTerrain3DUpload posts to the terrain3d-specific presign route", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/terrain3d/uploads/presign", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ uploadUrl: "https://minio.test/put", key: "tenant/x/dem.tif" });
    }),
  );
  const result = await makeClient("abc").presignTerrain3DUpload("dem.tif", "image/tiff");
  expect(result).toEqual({ uploadUrl: "https://minio.test/put", key: "tenant/x/dem.tif" });
  expect(body).toEqual({ filename: "dem.tif", contentType: "image/tiff" });
});

test("createTerrain3DUpload posts key/filename/title and returns jobId", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/terrain3d/uploads", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
  );
  const result = await makeClient("abc").createTerrain3DUpload({
    key: "tenant/x/dem.tif",
    filename: "dem.tif",
    title: "Relief",
  });
  expect(result).toEqual({ jobId: "job-1" });
  expect(body).toEqual({ key: "tenant/x/dem.tif", filename: "dem.tif", title: "Relief" });
});

test("getTerrain3DUploadJob returns the job status", async () => {
  server.use(
    http.get("https://core.test/terrain3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "t-1" }),
    ),
  );
  const result = await makeClient("abc").getTerrain3DUploadJob("job-1");
  expect(result).toEqual({ status: "done", errorMessage: null, itemId: "t-1" });
});

test("listLayerSources includes hosted tileset3d items", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => HttpResponse.json({ tiles: {} })),
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
    http.get("https://core.test/items", ({ request }) => {
      expect(new URL(request.url).searchParams.get("type")).toBe("tileset3d");
      return HttpResponse.json({
        items: [
          {
            pk: "t1",
            resourceType: "tileset3d",
            title: "Ville",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 200,
      });
    }),
  );
  const sources = await makeClient("abc").listLayerSources();
  const hosted = sources.find((s) => s.id === "t1");
  expect(hosted).toMatchObject({
    title: "Ville",
    service: "tileset3d",
    kind: "tiles3d",
    url: "https://core.test/tileset3d/t1/tileset.json",
  });
});

test("listConfigRevisions résout la config par item puis lit ses révisions", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/app-1", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "app-1", kind: "app", config: { kind: "app" } }),
    ),
    http.get("https://core.test/configs/cfg-1/revisions", () =>
      HttpResponse.json([
        { version: 1, created_at: "2026-08-01T10:00:00" },
        { version: 2, created_at: "2026-08-02T11:00:00" },
      ]),
    ),
  );
  const client = makeClient();
  expect(await client.listConfigRevisions("app-1")).toEqual([
    { version: 1, createdAt: "2026-08-01T10:00:00" },
    { version: 2, createdAt: "2026-08-02T11:00:00" },
  ]);
});

test("rollbackConfig poste la version demandée sur la config résolue", async () => {
  let posted: { version: number } | null = null;
  server.use(
    http.get("https://core.test/configs/by-item/app-1", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "app-1", kind: "app", config: { kind: "app" } }),
    ),
    http.post("https://core.test/configs/cfg-1/rollback", async ({ request }) => {
      posted = (await request.json()) as { version: number };
      return HttpResponse.json({});
    }),
  );
  const client = makeClient();
  await client.rollbackConfig("app-1", 3);
  expect(posted).toEqual({ version: 3 });
});

test("rollbackConfig propage l'erreur quand le serveur refuse la version", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/app-1", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "app-1", kind: "app", config: { kind: "app" } }),
    ),
    http.post(
      "https://core.test/configs/cfg-1/rollback",
      () => new HttpResponse(null, { status: 422 }),
    ),
  );
  const client = makeClient();
  await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow();
});

test("getAuthToken exposes the client's current token", () => {
  const client = makeClient("secret-token");
  expect(client.getAuthToken?.()).toBe("secret-token");
});

test("getCoreUrl exposes the client's configured core API origin", () => {
  const client = makeClient("secret-token");
  expect(client.getCoreUrl?.()).toBe("https://core.test");
});

test("getPrivilegeCatalog returns the catalog as-is", async () => {
  server.use(
    http.get("https://core.test/roles/catalog", () =>
      HttpResponse.json([
        {
          privilege: "admin.harvest.manage",
          domain: "admin",
          labelKey: "roles.privilege.adminHarvestManage",
        },
      ]),
    ),
  );
  const catalog = await makeClient().getPrivilegeCatalog();
  expect(catalog).toHaveLength(1);
  expect(catalog[0].privilege).toBe("admin.harvest.manage");
});

test("listRoles/createRole/updateRole/deleteRole round-trip", async () => {
  let roles = [
    {
      id: "r1",
      name: "Support",
      slug: "abc",
      isBuiltIn: false,
      privileges: ["admin.harvest.manage"],
    },
  ];
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(roles)),
    http.post("https://core.test/roles", async ({ request }) => {
      const body = (await request.json()) as { name: string; privileges: string[] };
      const created = { id: "r2", slug: "def", isBuiltIn: false, ...body };
      roles = [...roles, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch("https://core.test/roles/r1", async ({ request }) => {
      const patch = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...roles[0], ...patch });
    }),
    http.delete("https://core.test/roles/r1", () => new HttpResponse(null, { status: 204 })),
  );
  const client = makeClient();
  expect(await client.listRoles()).toEqual(roles);
  const created = await client.createRole({ name: "Analyste+", privileges: ["analytics.view"] });
  expect(created.id).toBe("r2");
  const updated = await client.updateRole("r1", { name: "Support+" });
  expect(updated.name).toBe("Support+");
  await expect(client.deleteRole("r1")).resolves.toBeUndefined();
});

test("listUsers/updateUserRole round-trip, avec recherche et pagination dans la query string", async () => {
  let lastUrl = "";
  const users = [
    { id: "u1", username: "alice", roleSlug: "admin" },
    { id: "u2", username: "bob", roleSlug: "reader" },
  ];
  server.use(
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users, total: 2 });
    }),
    http.patch("https://core.test/users/u2", async ({ request }) => {
      const body = (await request.json()) as { roleId: string };
      return HttpResponse.json({ id: "u2", username: "bob", roleSlug: body.roleId });
    }),
  );
  const client = makeClient();
  const page = await client.listUsers({ page: 2, pageSize: 25, q: "ali" });
  expect(page).toEqual({ users, total: 2 });
  const url = new URL(lastUrl);
  expect(url.searchParams.get("page")).toBe("2");
  expect(url.searchParams.get("pageSize")).toBe("25");
  expect(url.searchParams.get("q")).toBe("ali");

  const updated = await client.updateUserRole("u2", "admin");
  expect(updated).toEqual({ id: "u2", username: "bob", roleSlug: "admin" });
});

test("listUsers omet q de la query string quand il n'est pas fourni", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users: [], total: 0 });
    }),
  );
  await makeClient().listUsers({ page: 1, pageSize: 50 });
  const url = new URL(lastUrl);
  expect(url.searchParams.has("q")).toBe(false);
});

test("presignAttachmentUpload appelle la route presign avec le bon corps", async () => {
  server.use(
    http.post(
      "https://core.test/collections/col1/items/f1/attachments/presign",
      async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ fieldKey: "photos", filename: "a.jpg", contentType: "image/jpeg" });
        return HttpResponse.json({ uploadUrl: "https://minio/x", key: "t/col1/f1/x-a.jpg" });
      },
    ),
  );
  const client = makeClient();
  const res = await client.presignAttachmentUpload("col1", "f1", {
    fieldKey: "photos",
    filename: "a.jpg",
    contentType: "image/jpeg",
  });
  expect(res.key).toBe("t/col1/f1/x-a.jpg");
});

test("attachmentFileUrl construit l'URL du proxy-read", () => {
  const client = makeClient();
  expect(client.attachmentFileUrl("col1", "f1", "att1")).toBe(
    "https://core.test/collections/col1/items/f1/attachments/att1/file",
  );
});
