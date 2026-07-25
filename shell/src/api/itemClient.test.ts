// SPDX-License-Identifier: Apache-2.0
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient, FeatureValidationError } from "./itemClient";

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    coreUrl: "https://core.test",
    martinUrl: "https://martin.test",
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
        isAdmin: false,
        isAnalyst: false,
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false, isAnalyst: false });
});

test("getMe surfaces isAdmin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        isAdmin: true,
        isAnalyst: false,
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me.isAdmin).toBe(true);
});

test("createConfigItem does not send owner in the request body", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "99", kind: "app", version: 1, config: {} }, { status: 201 });
    }),
  );
  const item = await makeClient().createConfigItem({ kind: "app", title: "My App", owner: "alice" });
  expect(body).not.toHaveProperty("owner");
  expect(item.owner).toBe("alice");
  expect(item.pk).toBe("99");
});

test("updateItem sends the patch camelCase, unchanged", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/items/:pk", async ({ params, request }) => {
      body = await request.json();
      return HttpResponse.json({
        pk: String(params.pk), resourceType: "app", title: "Renamed", abstract: "", owner: "alice",
        thumbnailUrl: null, date: "", configId: null, isPublished: true,
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
  server.use(http.delete("https://core.test/configs/by-item/:pk", () => new HttpResponse(null, { status: 404 })));
  await expect(makeClient().deleteItem("nope")).resolves.toBeUndefined();
});

test("listGroups maps name to title", async () => {
  const groups = await makeClient().listGroups();
  expect(groups).toEqual([{ id: "10", title: "Équipe A" }, { id: "11", title: "Équipe B" }]);
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
  await makeClient().setSharing("7", { public: false, groups: [{ groupId: "10", role: "viewer" }] });
  expect(body).toEqual({ public: false, groups: [{ groupId: "10", role: "viewer" }] });
});

test("listLayerSources aggregates Martin vector sources and core collections", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { content_type: "application/x-protobuf", description: "Communes" },
          routes: { content_type: "application/x-protobuf" },
        },
      }),
    ),
    http.get("https://core.test/collections", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        collections: [{ id: "public.parcs", title: "Parcs", featureCount: 42 }],
      });
    }),
  );
  const sources = await makeClient("abc").listLayerSources();
  expect(auth).toBe("Bearer abc");
  const martin = sources.find((s) => s.id === "communes");
  expect(martin).toMatchObject({
    title: "Communes",
    service: "martin",
    kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  expect(martin?.featureCount).toBeUndefined();
  // Martin source without a description falls back to its id for the title.
  expect(sources.find((s) => s.id === "routes")?.title).toBe("routes");
  const feature = sources.find((s) => s.id === "public.parcs");
  expect(feature).toMatchObject({
    title: "Parcs",
    service: "core",
    kind: "feature",
    url: "https://core.test/collections/public.parcs/items",
    featureCount: 42,
  });
});

test("listActiveExtensions maps the core's /extensions response to ExtensionManifest[]", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
            events: ["changed"], actions: ["reset"],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
          },
        ],
      });
    }),
  );
  const result = await makeClient("abc").listActiveExtensions();
  expect(auth).toBe("Bearer abc");
  expect(result).toEqual([
    {
      type: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js",
      props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
      events: ["changed"], actions: ["reset"],
      defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" },
    },
  ]);
});

test("listLayerSources still returns one service when the other fails", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [{ id: "public.parcs", title: "Parcs" }] }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources).toHaveLength(1);
  expect(sources[0].service).toBe("core");
});

test("listLayerSources passes q to /collections and filters Martin sources client-side", async () => {
  let collectionsUrl: string | null = null;
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { description: "Communes" },
          routes: { description: "Routes" },
        },
      }),
    ),
    http.get("https://core.test/collections", ({ request }) => {
      collectionsUrl = request.url;
      return HttpResponse.json({ collections: [{ id: "c1", title: "Communes" }] });
    }),
  );
  const sources = await makeClient().listLayerSources({ q: "commun" });
  expect(collectionsUrl).toContain("q=commun");
  expect(sources.find((s) => s.id === "communes")).toBeDefined();
  expect(sources.find((s) => s.id === "routes")).toBeUndefined();
  expect(sources.find((s) => s.id === "c1")).toBeDefined();
});

test("listLayerSources throws when both services fail", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/collections", () => new HttpResponse(null, { status: 500 })),
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
        id: "cfg-1", itemId: "77", kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8 },
            layers: [
              { id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a",
                tilesUrl: null, sourceLayer: null, opacity: null, deckType: null, dataUrl: null, paint: null, props: null },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.zoom).toBe(8);
  expect(cfg.layers[0]).toEqual({ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" });
});

test("getMapConfig throws when the config has no map payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "app", config: { kind: "app", map: null } }),
    ),
  );
  await expect(makeClient().getMapConfig("77")).rejects.toThrow();
});

test("saveMapConfig PUTs the map config by item", async () => {
  let method = ""; let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/77", async ({ request }) => {
      method = request.method; body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "map", map: body.map });
    }),
  );
  const cfg = { basemap: { style: "s" }, view: { center: [0, 0] as [number, number], zoom: 3 }, layers: [] };
  await makeClient().saveMapConfig("77", cfg);
  expect(method).toBe("PUT");
  expect(body.kind).toBe("map");
  expect(body.map.view.zoom).toBe(3);
});

test("createDatasetItem posts a dataset payload and returns a dataset Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds1", kind: "dataset", itemId: "ds-1" }, { status: 201 });
    }),
  );
  const item = await makeClient().createDatasetItem({ title: "Parcs", owner: "alice", collectionId: "parcs" });
  expect(body.config.kind).toBe("dataset");
  expect(body.config.dataset).toEqual({ source: "collection", collectionId: "parcs", columns: {} });
  expect(item).toMatchObject({ pk: "ds-1", resourceType: "dataset", title: "Parcs", configId: "cfg-ds1" });
});

test("getDatasetConfig reads the dataset payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-2", () =>
      HttpResponse.json({
        id: "cfg-ds2", itemId: "ds-2", kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "parcs", columns: { nom: { label: "Nom" } } },
        },
      }),
    ),
  );
  const cfg = await makeClient().getDatasetConfig("ds-2");
  expect(cfg).toEqual({ source: "collection", collectionId: "parcs", columns: { nom: { label: "Nom" } } });
});

test("getDatasetConfig throws when the config has no dataset payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-3", () =>
      HttpResponse.json({ id: "cfg-ds3", itemId: "ds-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getDatasetConfig("ds-3")).rejects.toThrow();
});

test("saveDatasetConfig PUTs the dataset config by item", async () => {
  let method = ""; let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/ds-4", async ({ request }) => {
      method = request.method; body = await request.json();
      return HttpResponse.json({ id: "cfg-ds4", itemId: "ds-4", kind: "dataset", dataset: body.dataset });
    }),
  );
  await makeClient().saveDatasetConfig("ds-4", { source: "collection", collectionId: "parcs", columns: {} });
  expect(method).toBe("PUT");
  expect(body.kind).toBe("dataset");
  expect(body.dataset.collectionId).toBe("parcs");
});

test("featuresUrl resolves datasetId to the dataset's collectionId once cached", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-5", () =>
      HttpResponse.json({
        id: "cfg-ds5", itemId: "ds-5", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
  );
  const client = makeClient();
  // Cache-miss: falls back to source.layer (empty) until something warms the cache.
  expect(client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-5", query: {} }))
    .toBe("https://core.test/collections//items");
  await client.getDatasetConfig("ds-5"); // warms the cache
  expect(client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-5", query: {} }))
    .toBe("https://core.test/collections/parcs/items");
});

test("queryDataSource resolves datasetId to the dataset's collectionId before fetching features", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-6", () =>
      HttpResponse.json({
        id: "cfg-ds6", itemId: "ds-6", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
    http.get("https://core.test/collections/parcs/items", () =>
      HttpResponse.json({ features: [{ id: 1, properties: { nom: "Le Parc" } }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-6", query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Le Parc" }, geometry: undefined }]);
});

test("getAppConfig reads the app config (kind/theme/layout)", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: { primary: "#123" }, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [
            { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
          ] },
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
      HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "map", config: { kind: "map", layout: null } }),
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
        id: "cfg-5", itemId: "5", kind: "app",
        config: { kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] } },
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
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  });
  expect(body.kind).toBe("app");
  expect(body.layout.type).toBe("grid");
});

test("featuresUrl builds the core items url", () => {
  const url = makeClient().featuresUrl({ id: "d", type: "features", service: "core", layer: "public.parcs", query: {} });
  expect(url).toBe("https://core.test/collections/public.parcs/items");
});

test("queryDataSource maps a feature collection to records", async () => {
  server.use(
    http.get("https://core.test/collections/public.parcs/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { type: "Feature", id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
          { type: "Feature", properties: { nom: "Parc B" }, geometry: null },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({ id: "d", type: "features", service: "core", layer: "public.parcs", query: {} });
  expect(records).toHaveLength(2);
  expect(records[0]).toMatchObject({ id: 1, properties: { nom: "Parc A" } });
  // Missing feature id falls back to the index.
  expect(records[1].id).toBe(1);
});

test("queryDataSource returns inline records for a static source", async () => {
  const records = await makeClient().queryDataSource({
    id: "s", type: "static", service: "", layer: "",
    query: { records: [{ id: "a", properties: { v: 1 } }] },
  });
  expect(records).toEqual([{ id: "a", properties: { v: 1 } }]);
});

test("queryDataSource throws when the feature request fails", async () => {
  server.use(
    http.get("https://core.test/collections/x/items", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(
    makeClient().queryDataSource({ id: "d", type: "features", service: "core", layer: "x", query: {} }),
  ).rejects.toThrow();
});

test("featuresUrl appends scalar query entries as sorted filter params", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "core", layer: "parcs",
    query: { nom: "Parc A", limit: 10 },
  });
  expect(url).toBe("https://core.test/collections/parcs/items?limit=10&nom=Parc+A");
});

test("featuresUrl omits empty/nullish query entries", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "core", layer: "parcs",
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
    id: "s", type: "statistics", service: "core", layer: "villes",
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
            { region: "Nord", value: agg === "sum" ? 30 : agg === "avg" ? 15 : agg === "min" ? 10 : 20 },
            { region: "Sud", value: 6 },
          ],
        }),
      ),
    );
    return makeClient().queryDataSource({
      id: "s", type: "statistics", service: "core", layer: "villes",
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
    id: "s", type: "statistics", service: "core", layer: "villes",
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
        rows: [
          { region: "Nord", Population: 30, avg_rev: 6 },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
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

test("featuresUrl strips reserved statistics keys but keeps filter params", () => {
  const url = makeClient().featuresUrl({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop", annee_filtre: 2026 },
  });
  expect(url).toBe("https://core.test/collections/villes/items?annee_filtre=2026");
});

test("getAppConfig passes through the pages array when present", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
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
    kind: "app", theme: {}, dataSources: [], messages: [],
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
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
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
    kind: "app", theme: {}, dataSources: [], messages: [],
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
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "two-column" });
  expect(body.config.layout.items).toHaveLength(2);
  expect(body.config.layout.items[0].widget).toBe("text");
});

test("createConfigItem falls back to an empty layout when templateId is unknown", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "does-not-exist" });
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
  expect(schema.fields[0]).toEqual({ name: "titre", type: "string", required: true, maxLength: 120 });
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
        { detail: { errors: [{ field: "titre", code: "missing_required", message: "'titre' is required" }] } },
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
    makeClient().updateFeature("incidents", "999", { type: "Feature", properties: {}, geometry: null }),
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

test("getCollectionPermission returns the canWrite flag", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({ id: "incidents", title: "Incidents", canWrite: true }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(true);
});

test("getCollectionPermission defaults to false when the field is absent", async () => {
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
        id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
        isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
        canWrite: false, featureCount: 2, owner: null,
      }),
    ),
  );
  const col = await makeClient(undefined).getCollection("parcs");
  expect(col).toEqual({
    id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
    isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
    canWrite: false, featureCount: 2, owner: null,
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
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "application-de-saisie" });
  expect(body.config.dataSources).toHaveLength(1);
  expect(body.config.dataSources[0]).toMatchObject({ type: "features", layer: "incidents" });
  expect(body.config.messages).toHaveLength(1);
});

test("createConfigItem seeds pages and navigationMode from a story template", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "story-cartographique" });
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
            id: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
            defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
          },
        ],
      });
    }),
  );
  const result = await makeClient().listAllExtensions();
  expect(url).toContain("all=true");
  expect(result).toEqual([
    {
      type: "acme.gauge", tag: "gauge-extension-widget", label: "Jauge (extension)",
      moduleUrl: "https://example.com/gauge.js", props: [], events: [], actions: [],
      defaultSize: { w: 2, h: 2 }, permissions: { collections: "all" }, enabled: false,
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

test("listCollections returns the admin collection shape including owner", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
  );
  const result = await makeClient().listCollections();
  expect(result).toEqual([
    {
      id: "incidents", title: "Incidents", description: "", tableName: "incidents",
      isPublic: false, editable: true, geometryType: "Point", srid: 4326,
      pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
    },
  ]);
});

test("listCandidateTables returns the candidates array as-is", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
        ],
      }),
    ),
  );
  const result = await makeClient().listCandidateTables();
  expect(result).toEqual([
    { tableName: "widgets", registrable: false, reason: "table has no primary key" },
    { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
  ]);
});

test("createCollection POSTs the input and returns the created collection", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/collections", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "Points d'intérêt", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  const result = await makeClient().createCollection({ tableName: "points_interet", title: "Points d'intérêt" });
  expect(body).toEqual({ tableName: "points_interet", title: "Points d'intérêt" });
  expect(result.id).toBe("points_interet");
});

test("updateCollection PATCHes the patch and returns the updated collection", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "incidents", title: "Incidents (v2)", description: "", tableName: "incidents",
        isPublic: true, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
      });
    }),
  );
  const result = await makeClient().updateCollection("incidents", { title: "Incidents (v2)", isPublic: true });
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
  await makeClient().setCollectionSharing("incidents", { public: false, groups: [{ groupId: "g1", role: "viewer" }] });
  expect(body).toEqual({ public: false, groups: [{ groupId: "g1", role: "viewer" }] });
});

test("getItemBySlug requests /public/sites/{slug} and returns the item", async () => {
  let url: string | null = null;
  server.use(
    http.get("https://core.test/public/sites/mon-portail", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        pk: "s1", resourceType: "site", slug: "mon-portail", title: "Portail",
        abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-1", isPublished: true,
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
    http.get("https://core.test/public/sites/nexiste-pas", () => new HttpResponse(null, { status: 404 })),
  );
  await expect(makeClient().getItemBySlug("nexiste-pas")).rejects.toThrow();
});

test("getPublicAppConfig reads the wrapped ConfigRead shape (config.layout, not top-level)", async () => {
  server.use(
    http.get("https://core.test/public/configs/by-item/s1", () =>
      HttpResponse.json({
        id: "cfg-1", itemId: "s1", kind: "site", version: 1,
        config: {
          kind: "site", theme: {}, dataSources: [], messages: [], pages: [],
          layout: { type: "grid", breakpoints: {}, items: [
            { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Bienvenue" } },
          ] },
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
      HttpResponse.json({ id: "cfg-1", itemId: "s1", kind: "site", config: { kind: "site", layout: null } }),
    ),
  );
  await expect(makeClient().getPublicAppConfig("s1")).rejects.toThrow();
});

test("createConfigItem transmits the slug in the POST body when given", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "s1", kind: "site", version: 1, config: body.config });
    }),
  );
  const item = await makeClient().createConfigItem({ kind: "site", title: "Portail", owner: "alice", slug: "mon-portail" });
  expect(body.slug).toBe("mon-portail");
  expect(body.config.kind).toBe("site");
  expect(item.slug).toBe("mon-portail");
});

test("createConfigItem omits slug from the POST body when not given", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "1", kind: "app", version: 1, config: body.config });
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
        items: [{
          pk: "8", resourceType: "app", title: "Carte des risques", abstract: "", owner: "alice",
          thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: true, keywords: ["risques"],
        }],
        total: 1, page: 1, pageSize: 12,
      }),
    ),
  );
  const page = await makeClient().listPublicItems();
  expect(page.items[0].keywords).toEqual(["risques"]);
});
