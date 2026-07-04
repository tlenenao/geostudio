import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    martinUrl: "https://martin.test",
    featureservUrl: "https://featureserv.test",
    getToken: () => token,
  });
}

test("listItems maps GeoNode resources to Items", async () => {
  const page = await makeClient().listItems();
  expect(page.total).toBe(2);
  expect(page.items[0]).toMatchObject({
    pk: "1",
    resourceType: "app",
    title: "Alpha",
    owner: "alice",
  });
});

test("listItems forwards the search term", async () => {
  const page = await makeClient().listItems({ q: "beta" });
  expect(page.items).toHaveLength(1);
  expect(page.items[0].title).toBe("Beta");
});

test("listItems sends the bearer token", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient("abc").listItems();
  expect(auth).toBe("Bearer abc");
});

test("listItems forwards the type filter param", async () => {
  let captured: URL | null = null;
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      captured = new URL(request.url);
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ type: "app" });
  expect(captured!.searchParams.get("filter{resource_type.in}")).toBe("app");
});

test("getItem maps a single resource", async () => {
  const item = await makeClient().getItem("7");
  expect(item.pk).toBe("7");
  expect(item.thumbnailUrl).toContain("/thumbs/7.png");
});

test("getItem throws on 404", async () => {
  await expect(makeClient().getItem("404")).rejects.toThrow(/404/);
});

test("getMe maps the current user", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
});

test("createConfigItem posts a skeleton config and maps to Item", async () => {
  const item = await makeClient().createConfigItem({
    kind: "dashboard",
    title: "My Dash",
    owner: "alice",
  });
  expect(item).toMatchObject({
    pk: "99",
    resourceType: "dashboard",
    title: "My Dash",
    owner: "alice",
    configId: "cfg-1",
    thumbnailUrl: null,
  });
});

test("createConfigItem sends title, owner and an empty grid layout", async () => {
  let body: any = null;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "c",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient("abc").createConfigItem({ kind: "app", title: "T", owner: "o" });
  expect(body.title).toBe("T");
  expect(body.owner).toBe("o");
  expect(body.config.kind).toBe("app");
  expect(body.config.layout).toEqual({ type: "grid", breakpoints: {}, items: [] });
});

test("updateItem PATCHes GeoNode and maps the result", async () => {
  const item = await makeClient().updateItem("7", { title: "Renamed", abstract: "New" });
  expect(item.pk).toBe("7");
  expect(item.title).toBe("Renamed");
  expect(item.abstract).toBe("New");
});

test("uploadThumbnail PUTs multipart without throwing", async () => {
  const file = new File(["x"], "t.png", { type: "image/png" });
  await expect(makeClient().uploadThumbnail("7", file)).resolves.toBeUndefined();
});

test("deleteItem DELETEs the by-item endpoint", async () => {
  let url: string | null = null;
  server.use(
    http.delete("https://builder.test/configs/by-item/:pk", ({ request }) => {
      url = new URL(request.url).pathname;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteItem("42");
  expect(url).toBe("/configs/by-item/42");
});

test("deleteItem treats 404 as success", async () => {
  server.use(
    http.delete("https://builder.test/configs/by-item/:pk", () =>
      new HttpResponse(null, { status: 404 }),
    ),
  );
  await expect(makeClient().deleteItem("gone")).resolves.toBeUndefined();
});

test("createConfigItem throws when builder returns no itemId", async () => {
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      const body = (await request.json()) as { config: { kind: string } };
      return HttpResponse.json({ id: "c", kind: body.config.kind, itemId: null, version: 1, config: body.config });
    }),
  );
  await expect(
    makeClient().createConfigItem({ kind: "app", title: "T", owner: "o" }),
  ).rejects.toThrow(/itemId/);
});

test("listGroups maps GeoNode group_profiles", async () => {
  const groups = await makeClient().listGroups();
  expect(groups).toEqual([
    { id: "10", title: "Équipe A" },
    { id: "11", title: "Équipe B" },
  ]);
});

test("getSharing maps public flag and group roles", async () => {
  const sharing = await makeClient().getSharing("7");
  expect(sharing.public).toBe(true);
  expect(sharing.groups).toEqual([{ groupId: "10", role: "editor" }]);
});

test("setSharing sends the mapped GeoNode payload", async () => {
  let body: any = null;
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  await makeClient().setSharing("7", {
    public: true,
    groups: [{ groupId: "5", role: "viewer" }],
  });
  expect(body.groups).toEqual([
    { id: "anonymous", permissions: "view" },
    { id: "5", permissions: "view" },
  ]);
});

test("setSharing omits the anonymous group when private", async () => {
  let body: any = null;
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  await makeClient().setSharing("7", {
    public: false,
    groups: [{ groupId: "5", role: "editor" }],
  });
  expect(body.groups).toEqual([{ id: "5", permissions: "edit" }]);
});

test("listItems scope=mine sends the owner filter", async () => {
  let url = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ scope: "mine", me: "alice" });
  expect(new URL(url).searchParams.get("filter{owner.username.in}")).toBe("alice");
});

test("listItems scope=public sends the published filter", async () => {
  let url = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ scope: "public" });
  expect(new URL(url).searchParams.get("filter{is_published}")).toBe("true");
});

test("listItems scope=shared drops items owned by me", async () => {
  server.use(
    http.get("https://geonode.test/api/v2/resources", () =>
      HttpResponse.json({
        total: 2,
        page: 1,
        page_size: 12,
        resources: [
          { pk: "1", resource_type: "app", title: "Mine", owner: { username: "alice" }, date: "" },
          { pk: "2", resource_type: "app", title: "Theirs", owner: { username: "bob" }, date: "" },
        ],
      }),
    ),
  );
  const page = await makeClient().listItems({ scope: "shared", me: "alice" });
  expect(page.items.map((i) => i.pk)).toEqual(["2"]);
  expect(page.total).toBe(1);
});

test("listItems scope=mine without me does not send the owner filter", async () => {
  let url = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ scope: "mine" });
  expect(new URL(url).searchParams.has("filter{owner.username.in}")).toBe(false);
});

test("listLayerSources aggregates Martin vector sources and featureserv collections", async () => {
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { content_type: "application/x-protobuf", description: "Communes" },
          routes: { content_type: "application/x-protobuf" },
        },
      }),
    ),
    http.get("https://featureserv.test/collections.json", () =>
      HttpResponse.json({
        collections: [{ id: "public.parcs", title: "Parcs" }],
      }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  const martin = sources.find((s) => s.id === "communes");
  expect(martin).toMatchObject({
    title: "Communes",
    service: "martin",
    kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  // Martin source without a description falls back to its id for the title.
  expect(sources.find((s) => s.id === "routes")?.title).toBe("routes");
  const feature = sources.find((s) => s.id === "public.parcs");
  expect(feature).toMatchObject({
    title: "Parcs",
    service: "featureserv",
    kind: "feature",
    url: "https://featureserv.test/collections/public.parcs/items.json",
  });
});

test("listLayerSources still returns one service when the other fails", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://featureserv.test/collections.json", () =>
      HttpResponse.json({ collections: [{ id: "public.parcs", title: "Parcs" }] }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources).toHaveLength(1);
  expect(sources[0].service).toBe("featureserv");
});

test("listLayerSources throws when both services fail", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://featureserv.test/collections.json", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(makeClient().listLayerSources()).rejects.toThrow();
});

test("createMapItem posts a map skeleton and returns a map Item", async () => {
  let body: any;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
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
    http.get("https://builder.test/configs/by-item/77", () =>
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
    http.get("https://builder.test/configs/by-item/77", () =>
      HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "app", config: { kind: "app", map: null } }),
    ),
  );
  await expect(makeClient().getMapConfig("77")).rejects.toThrow();
});

test("saveMapConfig PUTs the map config by item", async () => {
  let method = ""; let body: any;
  server.use(
    http.put("https://builder.test/configs/by-item/77", async ({ request }) => {
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
    http.get("https://builder.test/configs/by-item/5", () =>
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
    http.get("https://builder.test/configs/by-item/5", () =>
      HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "map", config: { kind: "map", layout: null } }),
    ),
  );
  await expect(makeClient().getAppConfig("5")).rejects.toThrow();
});

test("saveAppConfig PUTs the app config by item", async () => {
  let body: any;
  server.use(
    http.put("https://builder.test/configs/by-item/5", async ({ request }) => {
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

test("featuresUrl builds the featureserv items url", () => {
  const url = makeClient().featuresUrl({ id: "d", type: "features", service: "featureserv", layer: "public.parcs", query: {} });
  expect(url).toBe("https://featureserv.test/collections/public.parcs/items.json");
});

test("queryDataSource maps a feature collection to records", async () => {
  server.use(
    http.get("https://featureserv.test/collections/public.parcs/items.json", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { type: "Feature", id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
          { type: "Feature", properties: { nom: "Parc B" }, geometry: null },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({ id: "d", type: "features", service: "featureserv", layer: "public.parcs", query: {} });
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
    http.get("https://featureserv.test/collections/x/items.json", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(
    makeClient().queryDataSource({ id: "d", type: "features", service: "featureserv", layer: "x", query: {} }),
  ).rejects.toThrow();
});

test("featuresUrl appends scalar query entries as sorted filter params", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "featureserv", layer: "parcs",
    query: { nom: "Parc A", limit: 10 },
  });
  expect(url).toBe("https://featureserv.test/collections/parcs/items.json?limit=10&nom=Parc+A");
});

test("featuresUrl omits empty/nullish query entries", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "featureserv", layer: "parcs",
    query: { nom: "", ville: undefined as unknown as string },
  });
  expect(url).toBe("https://featureserv.test/collections/parcs/items.json");
});

test("queryDataSource aggregates a statistics source by count per group", async () => {
  server.use(
    http.get("https://featureserv.test/collections/villes/items.json", () =>
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
    id: "s", type: "statistics", service: "featureserv", layer: "villes",
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
      http.get("https://featureserv.test/collections/villes/items.json", () => HttpResponse.json(feats)),
    );
    return makeClient().queryDataSource({
      id: "s", type: "statistics", service: "featureserv", layer: "villes",
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
    http.get("https://featureserv.test/collections/villes/items.json", () =>
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
    id: "s", type: "statistics", service: "featureserv", layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
    { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 0 } },
  ]);
});

test("queryDataSource produces one wide column per measure", async () => {
  server.use(
    http.get("https://featureserv.test/collections/villes/items.json", () =>
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
    id: "s", type: "statistics", service: "featureserv", layer: "villes",
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
    id: "s", type: "statistics", service: "featureserv", layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop", annee_filtre: 2026 },
  });
  expect(url).toBe("https://featureserv.test/collections/villes/items.json?annee_filtre=2026");
});

test("getAppConfig passes through the pages array when present", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/5", () =>
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
    http.put("https://builder.test/configs/by-item/5", async ({ request }) => {
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
    http.get("https://builder.test/configs/by-item/5", () =>
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
    http.put("https://builder.test/configs/by-item/5", async ({ request }) => {
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
    http.post("https://builder.test/configs", async ({ request }) => {
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
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "does-not-exist" });
  expect(body.config.layout).toEqual({ type: "grid", breakpoints: {}, items: [] });
});

test("getItem maps is_published into isPublished", async () => {
  const item = await makeClient().getItem("7");
  expect(item.isPublished).toBe(false);
});

test("updateItem sends isPublished as is_published and maps the result back", async () => {
  let body: any = null;
  server.use(
    http.patch("https://geonode.test/api/v2/resources/:pk", async ({ request, params }) => {
      body = await request.json();
      return HttpResponse.json({
        resource: {
          pk: String(params.pk), resource_type: "app", title: "Item", abstract: "",
          owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01T00:00:00Z",
          is_published: body.is_published,
        },
      });
    }),
  );
  const item = await makeClient().updateItem("7", { isPublished: true });
  expect(body.is_published).toBe(true);
  expect(item.isPublished).toBe(true);
});
