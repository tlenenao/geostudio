# 3D — `Tile3DLayer` + terrain `raster-dem` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a map author add a 3D Tiles layer (external `tileset.json` URL) and an elevated terrain (external `raster-dem` tile URL), tune camera pitch/bearing from the editor, save that camera, and have a visitor see the exact same 3D view on load.

**Architecture:** Extends the existing `MapConfig`/`MapLayer` declarative schema (core Pydantic + shell TS, kept structurally identical) with a `tiles3d` layer kind and a `terrain` field, and extends the already-integrated deck.gl `MapboxOverlay` in `shell/src/map/MapView.tsx` with a `Tile3DLayer` (from `@deck.gl/geo-layers` + `@loaders.gl/tiles`) — no second map engine. Terrain uses MapLibre's native `raster-dem` source + `map.setTerrain()`. Camera pitch/bearing ride the same `moveend`/`flyTo` round-trip already used for center/zoom. Both 3D Tiles and terrain point at externally-hosted URLs only — no upload/hosting pipeline, no TiTiler wiring (see spec non-goals).

**Tech Stack:** FastAPI, Pydantic (core); React, TypeScript, MapLibre GL JS, deck.gl 9.x, loaders.gl 4.x, Vitest, Testing Library, Playwright (shell).

**Spec:** `docs/superpowers/specs/2026-08-13-3d-tiles-terrain-design.md`

## Global Constraints

- **Rendering only** — no hosting pipeline for uploaded 3D Tiles (zip→S3→item), no terrain served by our own TiTiler. Both `tiles3d.url` and `terrain.tilesUrl` are externally-hosted URLs supplied by the author.
- **`terrarium` encoding only** for terrain — no `mapbox` encoding option in v1.
- `tiles3d` reuses the existing `url` field already carried by `kind: "feature"` — no new field on `MapLayer`.
- `terrain` is nested directly inside `MapConfig` (both core and shell), **not** a top-level `BuilderConfig` sibling like `printLayout` — it only makes sense for a map.
- `pitch`/`bearing` are optional on `MapViewport`/`MapView` (core Pydantic), default `0` when absent — must not change behavior for any existing map without these fields.
- No new cross-field Pydantic validation for `tiles3d`/`terrain` required fields — matches the existing (lax) precedent for vector/raster/feature/deck.
- No new MCP tool — no MCP tool touches `MapConfig` today; not introduced here.
- The manual "add by URL" form in `LayerPicker` is scoped to `tiles3d` only — not a generalization to other `kind`s, and `kind: "deck"` layers remain non-addable from the editor (pre-existing limitation, out of scope).
- French in user-facing shell strings (labels, buttons) and commit messages; English in code identifiers — matches existing repo convention.
- TDD per task: write the failing test(s), confirm RED, implement, confirm GREEN, commit.
- `core/app/configs/schemas.py`'s Pydantic model named `MapView` is **not** the shell's React `MapView` component (`shell/src/map/MapView.tsx`) — same name, unrelated. Do not conflate the two in code comments.
- `> 30 fps` 3D Tiles navigability against a real public tileset is a manual acceptance check, never a CI assertion (WebGL fidelity is not reliably measurable in headless Chromium).

---

### Task 1: Core schema — `tiles3d` layer kind, `terrain`, camera pitch/bearing

**Files:**
- Modify: `core/app/configs/schemas.py:61-88` (`MapView`, `MapLayer`, `MapConfig` classes)
- Test: `core/tests/test_routes.py`

**Interfaces:**
- Produces: `MapLayer.kind` Literal including `"tiles3d"` (reuses existing `url: str | None` field, no new field); `MapTerrain(tilesUrl: str, encoding: Literal["terrarium"] = "terrarium", exaggeration: float | None = None)`; `MapConfig.terrain: MapTerrain | None = None`; `MapView.pitch: float | None = None`, `MapView.bearing: float | None = None`. These exact JSON field names are consumed by shell Task 2/3 (`MapLayer`/`MapConfig`/`MapViewport` TS types and `itemClient.ts` wire mapping).

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_routes.py` (near the existing `_map_config`/`test_map_config_*` tests, e.g. after `test_put_config_by_item_404_when_missing`):

```python
def test_map_config_round_trips_tiles3d_layer_terrain_and_camera(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte 3D",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [2.35, 48.85], "zoom": 5, "pitch": 45, "bearing": 90},
                    "layers": [
                        {"id": "bldg", "title": "Bâtiments", "visible": True,
                         "kind": "tiles3d", "url": "https://example.test/tileset.json"},
                    ],
                    "terrain": {
                        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
                        "encoding": "terrarium",
                        "exaggeration": 1.5,
                    },
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]["map"]
    assert body["view"]["pitch"] == 45
    assert body["view"]["bearing"] == 90
    assert body["layers"][0] == {
        "id": "bldg", "title": "Bâtiments", "visible": True, "kind": "tiles3d",
        "tilesUrl": None, "sourceLayer": None, "url": "https://example.test/tileset.json",
        "opacity": None, "deckType": None, "dataUrl": None, "paint": None, "props": None,
    }
    assert body["terrain"] == {
        "tilesUrl": "https://example.test/dem/{z}/{x}/{y}.png",
        "encoding": "terrarium",
        "exaggeration": 1.5,
    }


def test_map_config_defaults_pitch_bearing_terrain_when_absent(client):
    created = client.post(
        "/configs",
        json={
            "title": "Carte plate",
            "config": {
                "kind": "map",
                "map": {
                    "basemap": {"style": "https://demo/style.json"},
                    "view": {"center": [0, 0], "zoom": 1},
                    "layers": [],
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]
    body = client.get(f"/configs/by-item/{item_id}").json()["config"]["map"]
    assert body["view"]["pitch"] is None
    assert body["view"]["bearing"] is None
    assert body["terrain"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_routes.py -k "tiles3d_layer_terrain_and_camera or defaults_pitch_bearing_terrain" -v`
Expected: FAIL — `tiles3d` rejected as an invalid `kind` (Pydantic validation error, response not 201), and `terrain`/`pitch`/`bearing` unrecognized/absent from the response body.

- [ ] **Step 3: Implement the schema changes**

In `core/app/configs/schemas.py`, replace the `MapView`, `MapLayer`, `MapConfig` classes (currently lines 61-88):

```python
class MapView(BaseModel):
    center: tuple[float, float]
    zoom: float
    pitch: float | None = None
    bearing: float | None = None


class BaseMap(BaseModel):
    style: str


class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck", "tiles3d"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None


class MapTerrain(BaseModel):
    tilesUrl: str
    encoding: Literal["terrarium"] = "terrarium"
    exaggeration: float | None = None


class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)
    terrain: MapTerrain | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_routes.py -k "tiles3d_layer_terrain_and_camera or defaults_pitch_bearing_terrain" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full core suite for regressions**

Run: `cd core && uv run pytest -q`
Expected: all passing, same count as before plus the 2 new tests (no existing map-config test broken — `pitch`/`bearing`/`terrain` are all optional/defaulted).

- [ ] **Step 6: Regenerate `openapi.json`**

Run:
```bash
cd core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json
```
Expected: `core/openapi.json` is rewritten; `git diff --stat core/openapi.json` shows changes reflecting the new `tiles3d` enum value, `MapTerrain` schema, and `pitch`/`bearing` fields.

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_routes.py core/openapi.json
git commit -m "feat(core): ajoute le kind tiles3d, le terrain et pitch/bearing à MapConfig"
```

---

### Task 2: Shell types — `tiles3d`, `terrain`, camera in `MapConfig`

**Files:**
- Modify: `shell/src/api/types.ts:57-74` (`MapViewport`, `MapLayer`, `MapConfig`)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)

**Interfaces:**
- Consumes: Task 1's `core/openapi.json`.
- Produces: `MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number }`; `MapLayer` union gains `{ kind: "tiles3d"; id; title; visible; url: string }`; `MapViewport` gains `pitch?: number; bearing?: number`; `MapConfig` gains `terrain?: MapTerrainConfig | null`. Consumed by Task 3 (`itemClient.ts`), Task 4 (`MapView.tsx`), Task 5 (`LayerPicker.tsx`), Task 6 (`TerrainPanel.tsx`), Task 7 (`CameraControls.tsx`, `MapEditorPage.tsx`).

- [ ] **Step 1: Edit the types**

In `shell/src/api/types.ts`, replace lines 57-74:

```ts
export type MapViewport = { center: [number, number]; zoom: number; pitch?: number; bearing?: number };
export type BaseMap = { style: string };
export type MapLayer =
  | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
  | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "tiles3d"; url: string };
export type MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number };
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  showScaleBar?: boolean;
  showNorthArrow?: boolean;
  cartouche?: string | null;
};

export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
};
```

- [ ] **Step 2: Type-check (expect errors in files not yet updated)**

Run: `cd shell && npx tsc --noEmit`
Expected: FAIL — errors in `itemClient.ts` (the `toFrontLayer` switch doesn't handle `"tiles3d"` in a way that satisfies the new union yet — actually this alone won't error since `toFrontLayer`'s `default` branch still returns a valid `feature`-shaped object; expect this step to otherwise PASS with no new errors). If it passes cleanly, that's fine — proceed; the real coverage gap is closed by Task 3's tests, not the type checker.

- [ ] **Step 3: Regenerate `core-schema.d.ts`**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` is rewritten to reflect Task 1's `core/openapi.json` (new `tiles3d` enum value, `MapTerrain` schema, `pitch`/`bearing` fields visible in the diff).

- [ ] **Step 4: Type-check again**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS, no errors.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/generated/core-schema.d.ts
git commit -m "feat(shell): ajoute tiles3d, terrain et pitch/bearing aux types MapConfig"
```

---

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

### Task 4: `MapView.tsx` — render `Tile3DLayer`, terrain, and persist camera

**Files:**
- Modify: `shell/package.json` (add `@deck.gl/geo-layers`, `@loaders.gl/tiles`, `@loaders.gl/core`)
- Modify: `shell/src/map/MapView.tsx` (full file)
- Modify: `shell/src/test/MockDeckgl.ts` (add `Tile3DLayer` mock)
- Create: `shell/src/test/MockLoadersGl.ts`
- Modify: `shell/src/test/MockMaplibreMap.ts` (pitch/bearing/terrain tracking)
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `MapLayer`, `MapConfig`, `MapTerrainConfig` (Task 2).
- Produces: `MapView` renders `tiles3d` layers via the existing deck.gl overlay and applies/clears `map.setTerrain(...)`; `MapViewHandle.flyTo` accepts optional `pitch`/`bearing`; `onViewChange` payload gains `pitch: number; bearing: number`. Consumed by Task 7 (`MapEditorPage.tsx`'s `setView`/`setCamera`/`mapViewRef`).

- [ ] **Step 1: Add dependencies**

In `shell/package.json`, in the `dependencies` block, add (alphabetically, alongside the existing `@deck.gl/*` and near the top):

```json
    "@deck.gl/geo-layers": "^9.0.0",
    "@loaders.gl/core": "^4.3.0",
    "@loaders.gl/tiles": "^4.3.0",
```

Run: `cd shell && npm install`
Expected: installs successfully; `package-lock.json` updated. If `@loaders.gl/tiles@^4.3.0` conflicts with the installed `@deck.gl/core@9.0.x` peer range, npm will report it — adjust the loaders.gl version to whatever npm resolves cleanly against the existing deck.gl 9.0.x install (check `npm ls @deck.gl/core` for the exact installed version first).

- [ ] **Step 2: Add test doubles**

Add to `shell/src/test/MockDeckgl.ts` (after the `ColumnLayer` class):

```ts
export class Tile3DLayer extends MockDeckLayer {
  static typeName = "Tile3DLayer";
}
```

Create `shell/src/test/MockLoadersGl.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
export const Tiles3DLoader = { name: "Tiles3DLoader", id: "3d-tiles" };
```

In `shell/src/test/MockMaplibreMap.ts`, update the `opts` type and add terrain/camera support:

```ts
export type Recorded = { id: string; spec: unknown };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: { style: string; center: [number, number]; zoom: number; pitch?: number; bearing?: number };
  handlers: Record<string, Array<() => void>> = {};
  layerHandlers: Record<string, Array<(e: unknown) => void>> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  controls: unknown[] = [];
  removed = false;
  throwOnAddLayer = new Set<string>();
  flyToArgs: unknown[] = [];
  fitBoundsArgs: unknown[] = [];
  bounds: [[number, number], [number, number]] = [[0, 0], [0, 0]];
  terrain: unknown = null;
```

(Only the `opts` type and the new `terrain` field are new; the constructor and every other existing field stay as-is.) Then add these methods anywhere in the class body (e.g. right after `getBounds()`):

```ts
  getPitch() {
    return this.opts.pitch ?? 0;
  }
  getBearing() {
    return this.opts.bearing ?? 0;
  }
  setTerrain(spec: unknown) {
    this.terrain = spec;
  }
```

- [ ] **Step 3: Write the failing tests**

Add to `shell/src/map/MapView.test.tsx`. First, two more `vi.mock` blocks after the existing `@deck.gl/layers` mock:

```ts
vi.mock("@deck.gl/geo-layers", async () => {
  const { Tile3DLayer } = await import("../test/MockDeckgl");
  return { Tile3DLayer };
});
vi.mock("@loaders.gl/tiles", async () => {
  const { Tiles3DLoader } = await import("../test/MockLoadersGl");
  return { Tiles3DLoader };
});
```

Then replace the two existing `moveend` tests (`"reports view changes on moveend"` and `"onViewChange includes the current bbox from the map bounds"`) with:

```ts
test("reports view changes on moveend", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5, bbox: [0, 0, 0, 0], pitch: 0, bearing: 0 });
});

test("onViewChange includes the current bbox from the map bounds", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].bounds = [[1, 2], [3, 4]];
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5, bbox: [1, 2, 3, 4], pitch: 0, bearing: 0 });
});

test("onViewChange reports the map's current pitch and bearing", () => {
  const onViewChange = vi.fn();
  const cfg: MapConfig = { ...config, view: { center: [2.35, 48.85], zoom: 5, pitch: 40, bearing: 200 } };
  render(<MapView config={cfg} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith(expect.objectContaining({ pitch: 40, bearing: 200 }));
});
```

Finally, append these new tests at the end of the file:

```ts
test("initializes the map with pitch and bearing from the view", () => {
  const cfg: MapConfig = { ...config, view: { center: [2.35, 48.85], zoom: 5, pitch: 30, bearing: 120 } };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].opts.pitch).toBe(30);
  expect(mapInstances[0].opts.bearing).toBe(120);
});

test("defaults pitch and bearing to 0 when absent from the view", () => {
  render(<MapView config={config} />);
  expect(mapInstances[0].opts.pitch).toBe(0);
  expect(mapInstances[0].opts.bearing).toBe(0);
});

test("mounts a Tile3DLayer for a visible tiles3d layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers).toHaveLength(1);
  expect(layers[0].deckType).toBe("Tile3DLayer");
  expect(layers[0].props).toMatchObject({ id: "bldg", data: "https://example.test/tileset.json" });
});

test("excludes a hidden tiles3d layer from the overlay", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: false, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(overlayInstances[0].props.layers).toHaveLength(0);
});

test("skips tiles3d layers in the MapLibre-native layer path", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("bldg")).toBeUndefined();
});

test("shows a tiles3d layer's title in the legend", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  expect(document.body.textContent).toContain("Bâtiments");
});

test("enables terrain on load when config.terrain is present", () => {
  const cfg: MapConfig = {
    ...config,
    terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1.5 },
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("__terrain__")).toMatchObject({
    spec: { type: "raster-dem", tiles: ["https://example.test/dem/{z}/{x}/{y}.png"], encoding: "terrarium" },
  });
  expect(map.terrain).toEqual({ source: "__terrain__", exaggeration: 1.5 });
});

test("defaults terrain exaggeration to 1 when not specified", () => {
  const cfg: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" } };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].terrain).toEqual({ source: "__terrain__", exaggeration: 1 });
});

test("removes terrain when config.terrain is cleared", () => {
  const withTerrain: MapConfig = { ...config, terrain: { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium" } };
  const { rerender } = render(<MapView config={withTerrain} />);
  expect(mapInstances[0].terrain).not.toBeNull();
  rerender(<MapView config={{ ...config, terrain: null }} />);
  expect(mapInstances[0].terrain).toBeNull();
  expect(mapInstances[0].getSource("__terrain__")).toBeUndefined();
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd shell && npm run test -- src/map/MapView.test.tsx`
Expected: FAIL — `@deck.gl/geo-layers`/`@loaders.gl/tiles` imports don't exist in `MapView.tsx` yet, `tiles3d` isn't handled, `config.terrain`/pitch/bearing aren't applied, and the two rewritten moveend tests fail (payload currently lacks `pitch`/`bearing`).

- [ ] **Step 5: Implement**

Replace the full contents of `shell/src/map/MapView.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { Tiles3DLoader } from "@loaders.gl/tiles";
import type { DataRecord, MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

const HIGHLIGHT_ID = "__highlight__";
const TERRAIN_SOURCE_ID = "__terrain__";

export type MapViewHandle = {
  flyTo: (opts: { center: [number, number]; zoom?: number; pitch?: number; bearing?: number }) => void;
  highlight: (geometry: unknown | null) => void;
};

function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  onFeatureClick: (record: DataRecord) => void,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    const prevHandler = clickHandlers.get(id);
    if (prevHandler) {
      map.off("click", id, prevHandler);
      clickHandlers.delete(id);
    }
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck" || layer.kind === "tiles3d") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({
          id: layer.id,
          type: "fill",
          source: layer.id,
          "source-layer": layer.sourceLayer,
          paint: layer.paint ?? {},
        });
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({ id: layer.id, type: "circle", source: layer.id, paint: layer.paint ?? {} });
            break;
          case "line":
            map.addLayer({ id: layer.id, type: "line", source: layer.id, paint: layer.paint ?? {} });
            break;
          default:
            map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
            break;
        }
        const handler = (e: maplibregl.MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f || f.id == null) return;
          onFeatureClick({ id: f.id as string | number, properties: f.properties ?? {}, geometry: f.geometry });
        };
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map. Roll back any
      // half-added source/layer so it can't orphan or clash on the next apply.
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
}

type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;
type Tiles3DMapLayer = Extract<MapConfig["layers"][number], { kind: "tiles3d" }>;

function buildDeckLayer(layer: DeckLayer) {
  // Canonical fields last so user props can't shadow the id Deck.gl uses for
  // layer reconciliation, nor the data source.
  const props = { ...(layer.props ?? {}), id: layer.id, data: layer.dataUrl };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
    default:
      // Exhaustiveness guard: a new deckType turns into a compile error here.
      return layer.deckType satisfies never;
  }
}

function buildTiles3DLayer(layer: Tiles3DMapLayer) {
  return new Tile3DLayer({ id: layer.id, data: layer.url, loader: Tiles3DLoader });
}

function applyDeckLayers(overlay: MapboxOverlay, layers: MapConfig["layers"]) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  const tiles3dLayers = layers
    .filter((l): l is Tiles3DMapLayer => l.visible && l.kind === "tiles3d")
    .map(buildTiles3DLayer);
  overlay.setProps({ layers: [...deckLayers, ...tiles3dLayers] });
}

// Full teardown-then-rebuild on every apply, mirroring applyLayers' pattern
// for the MapLibre-native layer array — simpler than diffing, and the only
// way to pick up a changed tilesUrl (MapLibre raster-dem sources are
// immutable once created).
function applyTerrain(map: maplibregl.Map, terrain: MapConfig["terrain"] | null | undefined) {
  map.setTerrain(null);
  if (map.getSource(TERRAIN_SOURCE_ID)) map.removeSource(TERRAIN_SOURCE_ID);
  if (!terrain) return;
  map.addSource(TERRAIN_SOURCE_ID, {
    type: "raster-dem",
    tiles: [terrain.tilesUrl],
    tileSize: 256,
    encoding: terrain.encoding,
  });
  map.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: terrain.exaggeration ?? 1 });
}

export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number]; pitch: number; bearing: number }) => void;
    onFeatureClick?: (record: DataRecord) => void;
    // Fired once the map has settled after its first load (MapLibre "idle":
    // no pending tiles/style/sprite loads) — the real "ready to capture"
    // signal for exportRender mode (SP-17a Task 10), as opposed to a fixed
    // delay.
    onReady?: () => void;
    // Suppresses the built-in interactive legend. Used by exportRender mode
    // (MapEditorPage), which renders its own legend overlay driven by
    // `printLayout.showLegend` — without this, that toggle couldn't ever
    // hide the legend from a capture (this MapLegend would still render
    // underneath it, and both would duplicate when showLegend is true).
    hideLegend?: boolean;
  }
>(function MapView({ config, onViewChange, onFeatureClick, onReady, hideLegend }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(new Map());
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const onReadyRef = useRef(onReady);
  const layersRef = useRef(config.layers);
  const terrainRef = useRef(config.terrain);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
  useEffect(() => {
    terrainRef.current = config.terrain;
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
    });
    mapRef.current = map;
    const overlay = new MapboxOverlay({ layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      map.addSource(HIGHLIGHT_ID, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: HIGHLIGHT_ID, type: "line", source: HIGHLIGHT_ID, paint: { "line-color": "#ef4444", "line-width": 3 } });
      applyLayers(map, layersRef.current, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
      applyDeckLayers(overlay, layersRef.current);
      applyTerrain(map, terrainRef.current);
      map.once("idle", () => onReadyRef.current?.());
    });
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      cb({ center: [c.lng, c.lat], zoom: map.getZoom(), bbox: bounds, pitch: map.getPitch(), bearing: map.getBearing() });
    });
    return () => {
      map.removeControl(overlay);
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !map.isStyleLoaded() || !overlay) return;
    applyLayers(map, config.layers, appliedRef.current, clickHandlersRef.current, (r) => onFeatureClickRef.current?.(r));
    applyDeckLayers(overlay, config.layers);
  }, [config.layers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    applyTerrain(map, config.terrain);
  }, [config.terrain]);

  useImperativeHandle(ref, () => ({
    flyTo: (opts) => {
      mapRef.current?.flyTo(opts);
    },
    highlight: (geometry) => {
      const src = mapRef.current?.getSource(HIGHLIGHT_ID) as { setData?: (d: unknown) => void } | undefined;
      src?.setData?.(
        geometry
          ? { type: "Feature", geometry, properties: {} }
          : { type: "FeatureCollection", features: [] },
      );
    },
  }), []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      {!hideLegend && <MapLegend layers={config.layers} />}
    </div>
  );
});
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd shell && npm run test -- src/map/MapView.test.tsx`
Expected: PASS, all tests in the file green (existing + new).

- [ ] **Step 7: Type-check**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS, no errors.

- [ ] **Step 8: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/test/MockDeckgl.ts shell/src/test/MockLoadersGl.ts shell/src/test/MockMaplibreMap.ts
git commit -m "feat(shell): MapView rend les couches tiles3d et le terrain, persiste pitch/bearing"
```

---

### Task 5: `LayerPicker.tsx` — add a 3D Tiles layer by URL

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx` (full file)
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `MapLayer` (Task 2, `kind: "tiles3d"` variant), `Button` from `shell/src/ui/button.tsx`.
- Produces: no new exports — `LayerPicker`'s existing `onAdd` prop is now also called with a `tiles3d` layer from the new inline form.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/LayerPicker.test.tsx` (after the last existing test, `"has a search field that calls listLayerSources with q"`):

```ts
test("adds a tiles3d layer from the manual URL form", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  await userEvent.type(screen.getByLabelText("URL du tileset.json"), "https://example.test/tileset.json");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "tiles3d",
    title: "Bâtiments",
    visible: true,
    url: "https://example.test/tileset.json",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("disables the tiles3d add button until both title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter le tileset 3D" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("URL du tileset.json"), "https://example.test/tileset.json");
  expect(button).toBeEnabled();
});

test("clears the tiles3d form after adding", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const titleInput = screen.getByLabelText("Titre du tileset 3D") as HTMLInputElement;
  const urlInput = screen.getByLabelText("URL du tileset.json") as HTMLInputElement;
  await userEvent.type(titleInput, "Bâtiments");
  await userEvent.type(urlInput, "https://example.test/tileset.json");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(titleInput.value).toBe("");
  expect(urlInput.value).toBe("");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- src/map/LayerPicker.test.tsx`
Expected: FAIL — no element with label "Titre du tileset 3D"/"URL du tileset.json" or button "Ajouter le tileset 3D" exists yet.

- [ ] **Step 3: Implement**

Replace the full contents of `shell/src/map/LayerPicker.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { Button } from "../ui/button";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
    };
  }
  if (source.kind === "raster") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "raster",
      tilesUrl: source.tilesUrl ?? "",
      opacity: 1,
    };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const [q, setQ] = useState("");
  const [tiles3dTitle, setTiles3dTitle] = useState("");
  const [tiles3dUrl, setTiles3dUrl] = useState("");
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  function addTiles3D() {
    if (!tiles3dTitle.trim() || !tiles3dUrl.trim()) return;
    onAdd({ id: crypto.randomUUID(), title: tiles3dTitle, visible: true, kind: "tiles3d", url: tiles3dUrl });
    setTiles3dTitle("");
    setTiles3dUrl("");
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        role="searchbox"
        aria-label="Rechercher une source de couche"
        placeholder="Rechercher…"
        className="h-8 rounded-md border border-slate-300 px-2 text-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-slate-500">Chargement des sources…</p>}
      {isError && (
        <div className="text-sm text-red-600">
          <p role="alert">Impossible de charger les sources de couches.</p>
          <button type="button" className="underline" onClick={() => refetch()}>
            Réessayer
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-slate-500">Aucune source disponible.</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-slate-400">
                    {source.featureCount} entités
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter un tileset 3D par URL</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre du tileset 3D"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={tiles3dTitle}
            onChange={(e) => setTiles3dTitle(e.target.value)}
          />
          <input
            aria-label="URL du tileset.json"
            type="text"
            placeholder="https://…/tileset.json"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={tiles3dUrl}
            onChange={(e) => setTiles3dUrl(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!tiles3dTitle.trim() || !tiles3dUrl.trim()}
            onClick={addTiles3D}
          >
            Ajouter le tileset 3D
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- src/map/LayerPicker.test.tsx`
Expected: PASS, all tests in the file green (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "feat(shell): LayerPicker permet d'ajouter un tileset 3D par URL"
```

---

### Task 6: `TerrainPanel.tsx` — terrain editor panel

**Files:**
- Create: `shell/src/map/TerrainPanel.tsx`
- Create: `shell/src/map/TerrainPanel.test.tsx`

**Interfaces:**
- Consumes: `MapTerrainConfig` (Task 2).
- Produces: `TerrainPanel({ value: MapTerrainConfig | null; onChange: (next: MapTerrainConfig | null) => void })` — consumed by Task 7 (`MapEditorPage.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/TerrainPanel.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { MapTerrainConfig } from "../api/types";
import { TerrainPanel } from "./TerrainPanel";

test("renders unchecked and hides fields when value is null", () => {
  render(<TerrainPanel value={null} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Activer le terrain 3D")).not.toBeChecked();
  expect(screen.queryByLabelText("URL de tuiles terrain")).not.toBeInTheDocument();
});

test("checking the box emits a default terrain config", async () => {
  const onChange = vi.fn();
  render(<TerrainPanel value={null} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "", encoding: "terrarium", exaggeration: 1 });
});

test("shows URL and exaggeration fields when a terrain config is provided", () => {
  const value: MapTerrainConfig = { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 2 };
  render(<TerrainPanel value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Activer le terrain 3D")).toBeChecked();
  expect(screen.getByLabelText("URL de tuiles terrain")).toHaveValue("https://example.test/dem/{z}/{x}/{y}.png");
  expect(screen.getByLabelText("Exaggeration du terrain")).toHaveValue(2);
});

test("editing the URL field patches tilesUrl and preserves other fields", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "", encoding: "terrarium", exaggeration: 1 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("URL de tuiles terrain"), "u");
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 1 });
});

test("unchecking the box emits null", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 1 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith(null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- src/map/TerrainPanel.test.tsx`
Expected: FAIL — `shell/src/map/TerrainPanel.tsx` doesn't exist (module not found).

- [ ] **Step 3: Implement**

Create `shell/src/map/TerrainPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { MapTerrainConfig } from "../api/types";

export function TerrainPanel({
  value, onChange,
}: {
  value: MapTerrainConfig | null;
  onChange: (next: MapTerrainConfig | null) => void;
}) {
  const enabled = value != null;

  function toggle(checked: boolean) {
    onChange(checked ? { tilesUrl: "", encoding: "terrarium", exaggeration: 1 } : null);
  }

  function patch(partial: Partial<MapTerrainConfig>) {
    if (!value) return;
    onChange({ ...value, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Terrain 3D</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Activer le terrain 3D"
          type="checkbox"
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        Activer le terrain 3D
      </label>
      {enabled && value && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            URL de tuiles (terrain-RGB, encodage terrarium)
            <input
              aria-label="URL de tuiles terrain"
              type="text"
              placeholder="https://…/{z}/{x}/{y}.png"
              value={value.tilesUrl}
              onChange={(e) => patch({ tilesUrl: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Exaggeration
            <input
              aria-label="Exaggeration du terrain"
              type="number"
              step={0.1}
              min={0}
              value={value.exaggeration ?? 1}
              onChange={(e) => patch({ exaggeration: Number(e.target.value) })}
            />
          </label>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- src/map/TerrainPanel.test.tsx`
Expected: PASS, all 5 tests green.

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/TerrainPanel.tsx shell/src/map/TerrainPanel.test.tsx
git commit -m "feat(shell): TerrainPanel, panneau d'édition du terrain 3D"
```

---

### Task 7: `CameraControls.tsx` + wire terrain/camera into `MapEditorPage.tsx`

**Files:**
- Create: `shell/src/map/CameraControls.tsx`
- Create: `shell/src/map/CameraControls.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx` (full file)
- Modify: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `MapViewHandle`, `MapConfig`, `MapLayer`, `MapTerrainConfig`, `PrintLayoutConfig` (Tasks 2, 4), `TerrainPanel` (Task 6), `Button` from `shell/src/ui/button.tsx`.
- Produces: `CameraControls({ pitch: number; bearing: number; onChange: (next: { pitch: number; bearing: number }) => void })`. `MapEditorPage` gains a wired terrain panel and camera controls; saved `MapConfig.terrain`/`view.pitch`/`view.bearing` reflect editor state.

- [ ] **Step 1: Write the failing `CameraControls` tests**

Create `shell/src/map/CameraControls.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { CameraControls } from "./CameraControls";

test("renders the current pitch and bearing", () => {
  render(<CameraControls pitch={30} bearing={120} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Inclinaison de la caméra")).toHaveValue(30);
  expect(screen.getByLabelText("Orientation de la caméra")).toHaveValue(120);
});

test("moving the pitch slider reports the new pitch and keeps bearing", () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Inclinaison de la caméra"), { target: { value: "45" } });
  expect(onChange).toHaveBeenCalledWith({ pitch: 45, bearing: 120 });
});

test("moving the bearing slider reports the new bearing and keeps pitch", () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Orientation de la caméra"), { target: { value: "200" } });
  expect(onChange).toHaveBeenCalledWith({ pitch: 30, bearing: 200 });
});

test("the reset button reports pitch 0 and bearing 0", async () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Réinitialiser en 2D" }));
  expect(onChange).toHaveBeenCalledWith({ pitch: 0, bearing: 0 });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npm run test -- src/map/CameraControls.test.tsx`
Expected: FAIL — `shell/src/map/CameraControls.tsx` doesn't exist.

- [ ] **Step 3: Implement `CameraControls`**

Create `shell/src/map/CameraControls.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Button } from "../ui/button";

export function CameraControls({
  pitch, bearing, onChange,
}: {
  pitch: number;
  bearing: number;
  onChange: (next: { pitch: number; bearing: number }) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Caméra</p>
      <label className="flex flex-col gap-1 text-sm">
        Inclinaison (pitch) — {pitch}°
        <input
          aria-label="Inclinaison de la caméra"
          type="range"
          min={0}
          max={60}
          step={1}
          value={pitch}
          onChange={(e) => onChange({ pitch: Number(e.target.value), bearing })}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Orientation (bearing) — {bearing}°
        <input
          aria-label="Orientation de la caméra"
          type="range"
          min={0}
          max={360}
          step={1}
          value={bearing}
          onChange={(e) => onChange({ pitch, bearing: Number(e.target.value) })}
        />
      </label>
      <Button type="button" size="sm" variant="outline" className="w-fit" onClick={() => onChange({ pitch: 0, bearing: 0 })}>
        Réinitialiser en 2D
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npm run test -- src/map/CameraControls.test.tsx`
Expected: PASS, all 4 tests green.

- [ ] **Step 5: Commit `CameraControls`**

```bash
git add shell/src/map/CameraControls.tsx shell/src/map/CameraControls.test.tsx
git commit -m "feat(shell): CameraControls, sliders pitch/bearing avec réinitialisation 2D"
```

- [ ] **Step 6: Write the failing `MapEditorPage` tests**

In `shell/src/pages/MapEditorPage.test.tsx`, add two more `vi.mock` blocks after the existing `@deck.gl/layers` mock:

```ts
vi.mock("@deck.gl/geo-layers", async () => {
  const { Tile3DLayer } = await import("../test/MockDeckgl");
  return { Tile3DLayer };
});
vi.mock("@loaders.gl/tiles", async () => {
  const { Tiles3DLoader } = await import("../test/MockLoadersGl");
  return { Tiles3DLoader };
});
```

Add `fireEvent` to the existing `@testing-library/react` import (`import { fireEvent, render, screen, waitFor } from "@testing-library/react";`). Then add these two tests after the existing `"saving after only changing a layer keeps the previously loaded printLayout"` test:

```ts
test("edits terrain and camera, then saves both", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");

  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  await userEvent.type(screen.getByLabelText("URL de tuiles terrain"), "https://example.test/dem/{z}/{x}/{y}.png");
  fireEvent.change(screen.getByLabelText("Inclinaison de la caméra"), { target: { value: "40" } });
  fireEvent.change(screen.getByLabelText("Orientation de la caméra"), { target: { value: "200" } });

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.terrain).toEqual({ tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 1 });
  expect(saved.view.pitch).toBe(40);
  expect(saved.view.bearing).toBe(200);
});

test("the camera reset button zeroes pitch and bearing in the saved view", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue({ ...config, view: { ...config.view, pitch: 40, bearing: 200 } }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Réinitialiser en 2D" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.view.pitch).toBe(0);
  expect(saved.view.bearing).toBe(0);
});
```

- [ ] **Step 7: Run to verify they fail**

Run: `cd shell && npm run test -- src/pages/MapEditorPage.test.tsx`
Expected: FAIL — no "Activer le terrain 3D"/"Inclinaison de la caméra"/"Réinitialiser en 2D" elements exist in the rendered page yet.

- [ ] **Step 8: Wire `TerrainPanel`/`CameraControls` into `MapEditorPage`**

Replace the full contents of `shell/src/pages/MapEditorPage.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useInstanceInfo, useMapConfig, useSaveMap } from "../api/hooks";
import type { MapConfig, MapLayer, MapTerrainConfig, PrintLayoutConfig } from "../api/types";
import { MapView, type MapViewHandle } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { TerrainPanel } from "../map/TerrainPanel";
import { CameraControls } from "../map/CameraControls";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { ExportPanel } from "../builder/print/ExportPanel";
import { Button } from "../ui/button";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";

export function MapEditorPage({ pk }: { pk: string }) {
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);
  const mapViewRef = useRef<MapViewHandle>(null);
  const isExportRender = useIsExportRender();
  const instanceQuery = useInstanceInfo();
  const exportEnabled = instanceQuery.data?.exportEnabled === true;

  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);

  // `draft` lags one render behind a successful load (it is synced in the
  // effect above), so keep showing the loader during that gap instead of
  // flashing the error.
  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return (
      <p role="alert" className="text-sm text-red-600">
        Carte introuvable.
      </p>
    );

  const setLayers = (layers: MapLayer[]) => setDraft({ ...draft, layers });
  const setStyle = (style: string) => setDraft({ ...draft, basemap: { style } });
  const setView = (view: { center: [number, number]; zoom: number; pitch: number; bearing: number }) =>
    setDraft((d) => (d ? { ...d, view } : d));
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }
  function setTerrain(terrain: MapTerrainConfig | null) {
    setDraft((d) => (d ? { ...d, terrain } : d));
  }
  function setCamera(next: { pitch: number; bearing: number }) {
    setDraft((d) => (d ? { ...d, view: { ...d.view, ...next } } : d));
    mapViewRef.current?.flyTo({ center: draft.view.center, zoom: draft.view.zoom, ...next });
  }

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1 to capture a clean shot of the map
  // plus the PrintLayoutConfig overlays — no builder aside, no editor UI.
  // Ready signal = MapLibre "idle" (map.once), relayed via MapView's onReady.
  // showScaleBar/showNorthArrow are intentionally not rendered yet (known
  // limitation, tracked in the Task 10 report — not a silent no-op).
  if (isExportRender) {
    return (
      <div className="relative h-full w-full">
        <MapView config={draft} onReady={markExportReady} hideLegend />
        {draft.printLayout?.title && (
          <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
            {draft.printLayout.title}
          </div>
        )}
        {draft.printLayout?.showLegend && (
          <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.layers.filter((l) => l.visible).map((l) => <li key={l.id}>{l.title}</li>)}
          </ul>
        )}
        {draft.printLayout?.cartouche && (
          <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.printLayout.cartouche}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4">
      <aside className="flex w-72 flex-col gap-4 overflow-auto">
        <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
        <LayersPanel layers={draft.layers} onChange={setLayers} />
        <TerrainPanel value={draft.terrain ?? null} onChange={setTerrain} />
        <CameraControls pitch={draft.view.pitch ?? 0} bearing={draft.view.bearing ?? 0} onChange={setCamera} />
        <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
        {exportEnabled && <ExportPanel itemId={pk} />}
        <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
          Enregistrer
        </Button>
        {save.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de l'enregistrement.
          </p>
        )}
      </aside>
      <div className="relative flex-1">
        <MapView ref={mapViewRef} config={draft} onViewChange={setView} />
      </div>
    </div>
  );
}
```

- [ ] **Step 9: Run to verify they pass**

Run: `cd shell && npm run test -- src/pages/MapEditorPage.test.tsx`
Expected: PASS, all tests in the file green (existing + 2 new).

- [ ] **Step 10: Type-check**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS, no errors.

- [ ] **Step 11: Commit**

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): MapEditorPage câble le terrain et la caméra 3D"
```

---

### Task 8: E2E — add a 3D tileset, terrain, and camera; save; reload

**Files:**
- Modify: `shell/e2e/map-editor.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-7, `mockCore` from `shell/e2e/mocks.ts` (unchanged — `terrain` round-trips automatically through the existing generic `map` passthrough in the `/configs/by-item/**` PUT/GET handlers, since it's nested inside `map` rather than a `printLayout`-style sibling).

- [ ] **Step 1: Write the new E2E test**

Append to `shell/e2e/map-editor.spec.ts` (after the existing test):

```ts
test("add a 3D tileset + terrain, set the camera, save, and reload — everything round-trips", async ({ page }) => {
  await mockCore(page);
  await page.route("https://example.test/tileset.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: { version: "1.0" },
        geometricError: 500,
        root: { boundingVolume: { region: [0, 0, 0, 0, 0, 0] }, geometricError: 500, refine: "ADD", children: [] },
      }),
    }),
  );
  await page.route("https://example.test/dem/**", (route) => route.fulfill({ status: 404, body: "" }));

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte 3D");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Add a 3D Tiles layer by URL.
  await page.getByLabel("Titre du tileset 3D").fill("Bâtiments");
  await page.getByLabel("URL du tileset.json").fill("https://example.test/tileset.json");
  await page.getByRole("button", { name: "Ajouter le tileset 3D" }).click();

  // Enable terrain.
  await page.getByLabel("Activer le terrain 3D").check();
  await page.getByLabel("URL de tuiles terrain").fill("https://example.test/dem/{z}/{x}/{y}.png");

  // Set the camera.
  await page.getByLabel("Inclinaison de la caméra").fill("45");
  await page.getByLabel("Orientation de la caméra").fill("90");

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Bâtiments").first()).toBeVisible();
  await expect(page.getByLabel("Activer le terrain 3D")).toBeChecked();
  await expect(page.getByLabel("URL de tuiles terrain")).toHaveValue("https://example.test/dem/{z}/{x}/{y}.png");
  await expect(page.getByLabel("Inclinaison de la caméra")).toHaveValue("45");
  await expect(page.getByLabel("Orientation de la caméra")).toHaveValue("90");
});
```

- [ ] **Step 2: Run the new spec to verify it fails**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/map-editor.spec.ts`
Expected: FAIL, before Tasks 4-7 land in this branch (it won't fail if run after them — run this spec now to confirm the assertions are exercising real behavior, not passing vacuously; if all tasks above are already committed, this step instead just confirms PASS directly, matching Step 4 below).

- [ ] **Step 3: Fix up against the real DOM until it passes**

If any locator/label mismatch surfaces (e.g. an aria-label typo), fix it directly in the relevant Task 5/6/7 component file, re-run.

- [ ] **Step 4: Run full E2E suite for regressions**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: all existing specs still pass (no existing config field removed or reshaped — `tiles3d`/`terrain`/`pitch`/`bearing` are purely additive), plus both `map-editor.spec.ts` tests passing.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/map-editor.spec.ts
git commit -m "test(e2e): ajoute un tileset 3D, un terrain et la caméra dans l'éditeur de carte"
```

---

### Task 9: Final verification + `CLAUDE.md` roadmap update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: all passing (606+2 executed, 87 skipped as before — postgis-marked tests still require docker, unaffected by this change).

- [ ] **Step 2: Run the full shell suite, build, and E2E**

Run: `cd shell && npm run test && npm run build && VITE_AUTH_MODE=mock npm run e2e`
Expected: all passing, clean build.

- [ ] **Step 3: Run import-linter for regressions**

Run: `cd core && uv run lint-imports`
Expected: PASS — no new cross-module imports were introduced (schema-only change in `app.configs`).

- [ ] **Step 4: Update `CLAUDE.md`**

In the `### Fait` list, add a new bullet after the `SP-17b` bullet (before `### À venir`), matching the existing unnumbered-increment style already used for `Storytelling`:

```markdown
- **3D (rendu)** — reste non planifié de la vision post-v0.1 (feuille de
  route §SP-17, A24) exécuté hors tout numéro de SP : nouveau `kind:
  "tiles3d"` sur `MapLayer` (deck.gl `Tile3DLayer` + loaders.gl, rendu par
  le même `MapboxOverlay` déjà utilisé par les couches `deck` — pas de
  deuxième moteur cartographique) et `MapConfig.terrain` (MapLibre
  `raster-dem` natif, encodage `terrarium` uniquement) ; caméra pitch/
  bearing sur `MapViewport`, persistée via le même round-trip `moveend`/
  `flyTo` que center/zoom. Périmètre resserré par rapport à l'A24
  d'origine (décidé en brainstorm 2026-08-13) : rendu seul — tileset 3D
  Tiles et terrain pointent vers des URL externes déjà hébergées, aucun
  pipeline d'upload/hébergement (zip→S3→item), aucun terrain servi par
  notre propre TiTiler, aucun outil MCP dédié.
```

Then update the `### À venir` bullet that currently reads `- Reste de la vision post-v0.1 : 3D (deck.gl \`Tile3DLayer\` + terrain raster-dem).` to:

```markdown
- Reste de la vision post-v0.1, 3D — rendu livré (cf. `### Fait`) ;
  restent non planifiés : hébergement de tilesets 3D Tiles uploadés
  (zip→S3→item), terrain servi par notre propre TiTiler depuis un DEM COG
  hébergé chez nous, encodage terrain `mapbox` en plus de `terrarium`,
  conversion 3D (py3dtiles, nuages de points).
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: rendu 3D (tiles3d + terrain) livré hors numéro de SP"
```
