### Task 3: `itemClient.ts` — wire mapping for `tiles3d`/`terrain`/camera

**Files:**
- Modify: `shell/src/api/itemClient.ts:6-29` (`RawMapLayer`, `toFrontLayer`), `shell/src/api/itemClient.ts:601-618` (`getMapConfig`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `MapLayer`, `MapConfig`, `MapTerrainConfig` (Task 2).
- Produces: `getMapConfig(pk): Promise<MapConfig>` now also returns `terrain` and `view.pitch`/`view.bearing` when present; `toFrontLayer` handles `kind: "tiles3d"`. `saveMapConfig` needs **no code change** — `terrain` and `view.pitch/bearing` are structural parts of the `MapConfig`/`MapViewport` objects already spread into the PUT body via `const { printLayout, ...map } = config`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts`, near the existing `getMapConfig`/`saveMapConfig` tests (after the `saveMapConfig PUTs the map config by item` test, around line 340):

```ts
test("getMapConfig maps a tiles3d layer", async () => {
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
              { id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json",
                tilesUrl: null, sourceLayer: null, opacity: null, deckType: null, dataUrl: null, paint: null, props: null },
            ],
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.layers[0]).toEqual({ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" });
});

test("getMapConfig reads terrain and camera pitch/bearing", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1", itemId: "77", kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demo/s.json" },
            view: { center: [1, 47], zoom: 8, pitch: 40, bearing: 200 },
            layers: [],
            terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1.5 },
          },
        },
      }),
    ),
  );
  const cfg = await makeClient().getMapConfig("77");
  expect(cfg.view.pitch).toBe(40);
  expect(cfg.view.bearing).toBe(200);
  expect(cfg.terrain).toEqual({ tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1.5 });
});

test("getMapConfig defaults terrain to null and omits pitch/bearing when absent", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1", itemId: "77", kind: "map",
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
  expect(body.map.terrain).toEqual({ tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" });
  expect(body.map.view).toEqual({ center: [0, 0], zoom: 1, pitch: 30, bearing: 60 });
  expect(body.terrain).toBeUndefined();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- src/api/itemClient.test.ts`
Expected: FAIL — `toFrontLayer` falls through the `default: case "feature"` branch for `kind: "tiles3d"` (returns a `feature`-shaped object instead), and `getMapConfig`'s inline raw type doesn't read `terrain`/`pitch`/`bearing` (the returned `cfg.terrain`/`cfg.view.pitch` are `undefined` in the first three tests; the 4th test passes accidentally since it saves `terrain` through the existing generic spread — verify by running the full set and reading actual failures, not assuming which ones fail).

- [ ] **Step 3: Implement**

In `shell/src/api/itemClient.ts`, replace the `RawMapLayer`/`toFrontLayer` block (lines 6-29):

```ts
type RawMapLayer = {
  id: string; title: string; visible: boolean; kind: string;
  tilesUrl?: string | null; sourceLayer?: string | null; url?: string | null;
  opacity?: number | null; deckType?: string | null; dataUrl?: string | null;
  paint?: Record<string, unknown> | null; props?: Record<string, unknown> | null;
};

function toFrontLayer(l: RawMapLayer): MapLayer {
  const base = { id: l.id, title: l.title, visible: l.visible };
  switch (l.kind) {
    case "vector":
      return { ...base, kind: "vector", tilesUrl: l.tilesUrl ?? "", sourceLayer: l.sourceLayer ?? "",
        ...(l.paint ? { paint: l.paint } : {}) };
    case "raster":
      return { ...base, kind: "raster", tilesUrl: l.tilesUrl ?? "",
        ...(l.opacity != null ? { opacity: l.opacity } : {}) };
    case "deck":
      return { ...base, kind: "deck", deckType: (l.deckType ?? "heatmap") as "heatmap" | "hexbin" | "column",
        dataUrl: l.dataUrl ?? "", ...(l.props ? { props: l.props } : {}) };
    case "tiles3d":
      return { ...base, kind: "tiles3d", url: l.url ?? "" };
    case "feature":
    default:
      return { ...base, kind: "feature", url: l.url ?? "", ...(l.paint ? { paint: l.paint } : {}) };
  }
}
```

Then replace `getMapConfig` (lines 601-618):

```ts
    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map,
      // printLayout is a sibling top-level field (core/app/configs/schemas.py::BuilderConfig).
      const data = await request<{
        config?: {
          map?: {
            basemap: { style: string };
            view: { center: [number, number]; zoom: number; pitch?: number | null; bearing?: number | null };
            layers: RawMapLayer[];
            terrain?: { tilesUrl: string; encoding: "terrarium"; exaggeration?: number | null } | null;
          } | null;
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: {
          center: map.view.center,
          zoom: map.view.zoom,
          ...(map.view.pitch != null ? { pitch: map.view.pitch } : {}),
          ...(map.view.bearing != null ? { bearing: map.view.bearing } : {}),
        },
        layers: (map.layers ?? []).map(toFrontLayer),
        printLayout: data.config?.printLayout ?? null,
        terrain: map.terrain
          ? {
              tilesUrl: map.terrain.tilesUrl,
              encoding: map.terrain.encoding,
              ...(map.terrain.exaggeration != null ? { exaggeration: map.terrain.exaggeration } : {}),
            }
          : null,
      };
    },
```

`saveMapConfig` (lines 620-623) is unchanged — `terrain` and `view.pitch/bearing` are already part of `MapConfig`/`MapViewport` and flow through `const { printLayout, ...map } = config` automatically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- src/api/itemClient.test.ts`
Expected: PASS, all tests in the file green (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient mappe tiles3d, terrain et pitch/bearing"
```

---

