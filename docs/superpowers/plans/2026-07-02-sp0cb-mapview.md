# MapView Core (SP-0c-b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable `MapView` component that renders a `MapConfig` (basemap + view + layers) with MapLibre GL — the core every map screen depends on. Vector/raster/feature layers only (Deck.gl overlay is SP-0c-c).

**Architecture:** A React component instantiates a MapLibre `Map` into a container, applies `basemap.style` + initial `view`, and translates each visible `MapLayer` into a MapLibre source + layer (in order, idempotent on config change). MapLibre needs WebGL (absent in jsdom), so unit tests mock `maplibre-gl` with a stub `Map` that records `addSource`/`addLayer`/… calls; assertions verify the config→API translation. Real rendering is deferred to the SP-0c-e Playwright E2E (once a route mounts `MapView`).

**Tech Stack:** React 19, TypeScript, `maplibre-gl` (new dep), Vitest + Testing Library (with a shared MapLibre mock).

## Global Constraints

- Work under `shell/`; run from `shell/`: `npm test`, `npm run build`.
- Add `maplibre-gl` as the only new dependency.
- MapLibre is mocked in unit tests via a shared `MockMap` (records calls); no real WebGL in unit tests.
- `MapView` never lets a single bad layer throw — unknown/incomplete layers are skipped, not fatal.
- Front `MapConfig` types mirror the SP-0c spec §3 (and the SP-0c-a backend shape).
- Layer→MapLibre type mapping for this phase: `vector` ⇒ `fill` layer on a `vector` source; `raster` ⇒ `raster` layer on a `raster` source; `feature` ⇒ `fill` layer on a `geojson` source; `deck` layers are skipped here (handled in SP-0c-c). Per-geometry typing (line/circle) is a later refinement.
- Stage only the files each task lists (explicit paths); never stage `node_modules`.

---

### Task 1: `maplibre-gl` dep, MapLibre test mock, and `MapView` init

**Files:**
- Modify: `shell/package.json` (add `maplibre-gl`)
- Modify: `shell/src/api/types.ts` (add `MapConfig` front types)
- Create: `shell/src/test/MockMaplibreMap.ts`
- Create: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Produces in `types.ts` (front mirror of the spec §3):
  ```ts
  export type MapViewport = { center: [number, number]; zoom: number };
  export type BaseMap = { style: string };
  export type MapLayer =
    | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
    | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
    | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown> }
    | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> };
  export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[] };
  ```
  (The viewport type is named `MapViewport` to avoid colliding with the `MapView` component; the on-the-wire field stays `view`.)
- `MockMaplibreMap.ts`: exports `mapInstances: MockMap[]` and `class MockMap` recording `on/addSource/addLayer/getLayer/getSource/removeLayer/removeSource/getCenter/getZoom/loaded/remove/fire`; `on("load", cb)` fires `cb` synchronously.
- `MapView` component: `MapView({ config, onViewChange? }: { config: MapConfig; onViewChange?: (v: { center: [number, number]; zoom: number }) => void })` — instantiates `new maplibregl.Map({ container, style: config.basemap.style, center: config.view.center, zoom: config.view.zoom })`, renders a full-size container `div`, and removes the map on unmount.

- [ ] **Step 1: Add the dependency**

Add `"maplibre-gl": "^4.7.0"` to `shell/package.json` `dependencies`. Run `npm install`.

- [ ] **Step 2: Add front `MapConfig` types to `shell/src/api/types.ts`**

Append the block from the Interfaces section above to `shell/src/api/types.ts`.

- [ ] **Step 3: Create the MapLibre mock `shell/src/test/MockMaplibreMap.ts`**

```ts
export type Recorded = { id: string; spec: unknown };

export const mapInstances: MockMap[] = [];

export class MockMap {
  opts: { style: string; center: [number, number]; zoom: number };
  handlers: Record<string, () => void> = {};
  sources: Recorded[] = [];
  layers: { id: string; [k: string]: unknown }[] = [];
  removed = false;

  constructor(opts: MockMap["opts"]) {
    this.opts = opts;
    mapInstances.push(this);
  }

  on(event: string, cb: () => void) {
    this.handlers[event] = cb;
    if (event === "load") cb();
    return this;
  }
  fire(event: string) {
    this.handlers[event]?.();
  }
  addSource(id: string, spec: unknown) {
    this.sources.push({ id, spec });
  }
  addLayer(layer: { id: string; [k: string]: unknown }) {
    this.layers.push(layer);
  }
  getLayer(id: string) {
    return this.layers.find((l) => l.id === id);
  }
  getSource(id: string) {
    return this.sources.find((s) => s.id === id);
  }
  removeLayer(id: string) {
    this.layers = this.layers.filter((l) => l.id !== id);
  }
  removeSource(id: string) {
    this.sources = this.sources.filter((s) => s.id !== id);
  }
  getCenter() {
    return { lng: this.opts.center[0], lat: this.opts.center[1] };
  }
  getZoom() {
    return this.opts.zoom;
  }
  loaded() {
    return true;
  }
  remove() {
    this.removed = true;
  }
}
```

- [ ] **Step 4: Write the failing test**

Create `shell/src/map/MapView.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapConfig } from "../api/types";
import { mapInstances } from "../test/MockMaplibreMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

const { MapView } = await import("./MapView");

beforeEach(() => {
  mapInstances.length = 0;
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.35, 48.85], zoom: 5 },
  layers: [],
};

test("initializes a MapLibre map with the basemap and view", () => {
  render(<MapView config={config} />);
  expect(mapInstances).toHaveLength(1);
  expect(mapInstances[0].opts.style).toBe("https://demotiles.maplibre.org/style.json");
  expect(mapInstances[0].opts.center).toEqual([2.35, 48.85]);
  expect(mapInstances[0].opts.zoom).toBe(5);
});

test("removes the map on unmount", () => {
  const { unmount } = render(<MapView config={config} />);
  const map = mapInstances[0];
  unmount();
  expect(map.removed).toBe(true);
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `npm test -- src/map/MapView.test.tsx`
Expected: FAIL — cannot resolve `./MapView`.

- [ ] **Step 6: Create `shell/src/map/MapView.tsx`**

```tsx
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { MapConfig } from "../api/types";

export function MapView({
  config,
  onViewChange,
}: {
  config: MapConfig;
  onViewChange?: (v: { center: [number, number]; zoom: number }) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} className="h-full w-full" data-testid="map-container" />;
}
```

- [ ] **Step 7: Run to verify it passes**

Run: `npm test -- src/map/MapView.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 8: Run the build**

Run: `npm run build`
Expected: success (types resolve; `maplibre-gl` bundles).

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/api/types.ts shell/src/test/MockMaplibreMap.ts shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "feat(shell): add MapView with MapLibre init and a test mock"
```

---

### Task 2: Layer translation (vector / raster / feature)

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx` (add cases)

**Interfaces:**
- Consumes: `MockMap` recorded `sources`/`layers`.
- Produces: on map load and whenever `config.layers` changes, `MapView` applies the visible layers idempotently: `vector` ⇒ `addSource(id, { type: "vector", tiles: [tilesUrl] })` + `addLayer({ id, type: "fill", source: id, "source-layer": sourceLayer, paint })`; `raster` ⇒ `addSource(id, { type: "raster", tiles: [tilesUrl], tileSize: 256 })` + `addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity ?? 1 } })`; `feature` ⇒ `addSource(id, { type: "geojson", data: url })` + `addLayer({ id, type: "fill", source: id, paint })`; `deck` and non-visible layers are skipped. Re-applying removes previously added ids first.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/MapView.test.tsx`:

```tsx
test("adds a vector source and fill layer for a vector layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "communes", title: "Communes", visible: true, kind: "vector",
        tilesUrl: "https://martin/communes/{z}/{x}/{y}", sourceLayer: "communes" },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getSource("communes")).toMatchObject({
    spec: { type: "vector", tiles: ["https://martin/communes/{z}/{x}/{y}"] },
  });
  expect(map.getLayer("communes")).toMatchObject({
    type: "fill",
    source: "communes",
    "source-layer": "communes",
  });
});

test("skips non-visible and deck layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "hidden", title: "H", visible: false, kind: "raster", tilesUrl: "u" },
      { id: "deck1", title: "D", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "d" },
      { id: "ras", title: "R", visible: true, kind: "raster", tilesUrl: "https://titiler/{z}/{x}/{y}.png", opacity: 0.5 },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("hidden")).toBeUndefined();
  expect(map.getLayer("deck1")).toBeUndefined();
  expect(map.getLayer("ras")).toMatchObject({ type: "raster", paint: { "raster-opacity": 0.5 } });
});

test("re-applies layers when config.layers changes", () => {
  const first: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "A", visible: true, kind: "feature", url: "https://fs/a" }],
  };
  const { rerender } = render(<MapView config={first} />);
  const map = mapInstances[0];
  expect(map.getLayer("a")).toBeDefined();

  const second: MapConfig = {
    ...config,
    layers: [{ id: "b", title: "B", visible: true, kind: "feature", url: "https://fs/b" }],
  };
  rerender(<MapView config={second} />);
  expect(map.getLayer("a")).toBeUndefined();
  expect(map.getLayer("b")).toMatchObject({ type: "fill", source: "b" });
  expect(map.getSource("b")).toMatchObject({ spec: { type: "geojson", data: "https://fs/b" } });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/map/MapView.test.tsx`
Expected: FAIL — no sources/layers applied yet.

- [ ] **Step 3: Add layer translation to `shell/src/map/MapView.tsx`**

Add an `applyLayers` helper above the component:

```tsx
function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck") continue;
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
      map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
    }
    applied.add(layer.id);
  }
}
```

In the component, add an `applied` ref, apply on load, and re-apply when `config.layers` changes:

```tsx
  const appliedRef = useRef<Set<string>>(new Set());
```

In the init effect, after `mapRef.current = map;`, register the load handler:

```tsx
    map.on("load", () => applyLayers(map, config.layers, appliedRef.current));
```

Add a second effect for layer updates:

```tsx
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.loaded()) return;
    applyLayers(map, config.layers, appliedRef.current);
  }, [config.layers]);
```

(The `applyLayers` type parameter uses `MapConfig["layers"]`; the calls pass `map` typed as `maplibregl.Map`. In the mock, `getLayer`/`getSource`/`addSource`/`addLayer`/`removeLayer`/`removeSource`/`loaded` are all present.)

- [ ] **Step 4: Run to verify they pass**

Run: `npm test -- src/map/MapView.test.tsx`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "feat(shell): translate MapConfig layers to MapLibre sources/layers"
```

---

### Task 3: View change callback + legend

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Create: `shell/src/map/MapLegend.tsx`
- Test: `shell/src/map/MapView.test.tsx` (add cases)
- Test: `shell/src/map/MapLegend.test.tsx`

**Interfaces:**
- Produces:
  - `MapLegend({ layers }: { layers: MapConfig["layers"] })` — renders a `<ul>` listing the titles of visible, non-deck layers (empty when none).
  - `MapView` registers `map.on("moveend", …)` that calls `onViewChange({ center: [lng, lat], zoom })` from `getCenter()`/`getZoom()`, and renders `<MapLegend layers={config.layers} />` overlaid on the container.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/MapLegend.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import type { MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

test("lists visible non-deck layer titles", () => {
  const layers: MapConfig["layers"] = [
    { id: "a", title: "Communes", visible: true, kind: "vector", tilesUrl: "u", sourceLayer: "c" },
    { id: "b", title: "Cachée", visible: false, kind: "raster", tilesUrl: "u" },
  ];
  render(<MapLegend layers={layers} />);
  expect(screen.getByText("Communes")).toBeInTheDocument();
  expect(screen.queryByText("Cachée")).not.toBeInTheDocument();
});
```

Add to `shell/src/map/MapView.test.tsx`:

```tsx
test("reports view changes on moveend", () => {
  const onViewChange = vi.fn();
  render(<MapView config={config} onViewChange={onViewChange} />);
  mapInstances[0].fire("moveend");
  expect(onViewChange).toHaveBeenCalledWith({ center: [2.35, 48.85], zoom: 5 });
});

test("renders a legend of visible layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "a", title: "Communes", visible: true, kind: "vector", tilesUrl: "u", sourceLayer: "c" }],
  };
  render(<MapView config={cfg} />);
  // MapLegend renders the title
  expect(document.body.textContent).toContain("Communes");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/map/MapLegend.test.tsx src/map/MapView.test.tsx`
Expected: FAIL — `./MapLegend` missing; `onViewChange` not wired; legend absent.

- [ ] **Step 3: Create `shell/src/map/MapLegend.tsx`**

```tsx
import type { MapConfig } from "../api/types";

export function MapLegend({ layers }: { layers: MapConfig["layers"] }) {
  const visible = layers.filter((l) => l.visible && l.kind !== "deck");
  if (visible.length === 0) return null;
  return (
    <ul className="absolute bottom-2 left-2 z-10 rounded-md bg-white/90 p-2 text-xs shadow">
      {visible.map((l) => (
        <li key={l.id}>{l.title}</li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Wire `onViewChange` + legend into `shell/src/map/MapView.tsx`**

Add the import:

```tsx
import { MapLegend } from "./MapLegend";
```

In the init effect, after registering the load handler, add (guarded by `onViewChange`):

```tsx
    if (onViewChange) {
      map.on("moveend", () => {
        const c = map.getCenter();
        onViewChange({ center: [c.lng, c.lat], zoom: map.getZoom() });
      });
    }
```

Wrap the return in a relative container with the legend:

```tsx
  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      <MapLegend layers={config.layers} />
    </div>
  );
```

- [ ] **Step 5: Run to verify they pass**

Run: `npm test -- src/map/MapLegend.test.tsx src/map/MapView.test.tsx`
Expected: PASS (all).

- [ ] **Step 6: Run the full suite + build**

Run: `npm test` then `npm run build`.
Expected: all PASS; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapLegend.tsx shell/src/map/MapView.test.tsx shell/src/map/MapLegend.test.tsx
git commit -m "feat(shell): add MapView view-change callback and layer legend"
```

---

## Self-Review

**Spec coverage (against SP-0c §5 MapView + §9 test strategy + phase 0c-b):**
- `MapView` instantiates MapLibre with basemap + view → Task 1. ✅
- Translates vector/raster/feature layers (order, visibility, idempotent) → Task 2. ✅
- `onViewChange` on move + legend of visible layers → Task 3. ✅
- MapLibre mocked in unit tests; real render deferred to 0c-e E2E → Tasks 1-3 use `MockMap`. ✅
- Front `MapConfig` types added → Task 1. ✅
- `deck` layers skipped (0c-c) → Task 2. ✅

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `MapConfig`/`MapLayer` (Task 1, `api/types`) consumed by `MapView` (Tasks 1-3) and `MapLegend` (Task 3). The `MockMap` API (`on/addSource/addLayer/getLayer/getSource/removeLayer/removeSource/getCenter/getZoom/loaded/remove/fire`) matches what `MapView.applyLayers` and the view-change handler call. The component `MapView` (module `map/MapView.tsx`) is distinct from the `MapView` *type* (`api/types`) — no runtime collision. ✅

## Notes for SP-0c-c..e

- 0c-c mounts a Deck.gl `MapboxOverlay` on the MapLibre map for `kind: "deck"` layers (mock `@deck.gl/mapbox`).
- 0c-e mounts `MapView` in `MapEditorPage` at `/maps/:pk`; the Playwright E2E then asserts the real MapLibre canvas mounts.
- Per-geometry layer typing (line/circle vs fill) is a refinement once the layer picker (0c-d) knows geometry.
