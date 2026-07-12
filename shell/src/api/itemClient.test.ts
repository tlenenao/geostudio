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
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
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
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", pop: 10 } },
          { id: 2, properties: { region: "Nord", pop: 20 } },
          { id: 3, properties: { region: "Sud", pop: 5 } },
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
  const feats = {
    type: "FeatureCollection",
    features: [
      { id: 1, properties: { region: "Nord", pop: 10 } },
      { id: 2, properties: { region: "Nord", pop: 20 } },
      { id: 3, properties: { region: "Sud", pop: 6 } },
    ],
  };
  const run = async (agg: string) => {
    server.use(
      http.get("https://core.test/collections/villes/items", () => HttpResponse.json(feats)),
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
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", annee: "2025", pop: 10 } },
          { id: 2, properties: { region: "Nord", annee: "2026", pop: 12 } },
          { id: 3, properties: { region: "Sud", annee: "2025", pop: 5 } },
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
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", pop: 10, rev: 4 } },
          { id: 2, properties: { region: "Nord", pop: 20, rev: 8 } },
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
