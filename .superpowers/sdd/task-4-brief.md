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

