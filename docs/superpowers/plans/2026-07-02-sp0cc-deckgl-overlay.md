# GeoStudio SP-0c-c — Deck.gl overlay in MapView — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render `kind: "deck"` layers of a `MapConfig` as a Deck.gl overlay on top of the existing MapLibre `MapView` (heatmap / hexbin / 3D column).

**Architecture:** `MapView` already instantiates a MapLibre map and translates vector/raster/feature layers to MapLibre sources/layers (SP-0c-b). This phase mounts a single `@deck.gl/mapbox` `MapboxOverlay` on the map as a control, and on load / on `config.layers` change rebuilds the overlay's deck-layer list from the visible `kind:"deck"` layers, mapping `deckType` → deck class (heatmap→`HeatmapLayer`, hexbin→`HexagonLayer`, column→`ColumnLayer`). Deck.gl requires WebGL absent from jsdom, so unit tests mock `@deck.gl/mapbox`, `@deck.gl/aggregation-layers`, and `@deck.gl/layers` with doubles that record constructor props and `setProps` calls; real rendering is validated by the Playwright E2E deferred to 0c-e.

**Tech Stack:** React 19, TypeScript, Vite 6, Vitest 3 + Testing Library, MapLibre GL (mocked), Deck.gl v9 (`@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/aggregation-layers`, `@deck.gl/mapbox`; mocked in unit).

## Global Constraints

- Front: all network access via `item-client`; no service URL hard-coded (env config). (No new network in this phase.)
- `Item`/`ItemClient`/`MapConfig` contracts extended without breaking; only additions.
- MapLibre and Deck.gl are mocked in unit tests; real render validated only in E2E (0c-e).
- A single layer in error must never break the whole map render.
- No token in localStorage (unchanged).
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `design/sp0c-map` (do not branch or merge; PR is handled by finishing flow).
- `MapConfig`/`MapLayer` deck variant already exists in `shell/src/api/types.ts`:
  `{ id; title; visible; kind:"deck"; deckType:"heatmap"|"hexbin"|"column"; dataUrl; props? }`.

---

### Task 1: Deck.gl dependencies, test doubles, and overlay mount (heatmap)

**Files:**
- Modify: `shell/package.json` (add deck.gl deps)
- Create: `shell/src/test/MockDeckgl.ts`
- Modify: `shell/src/test/MockMaplibreMap.ts` (add `addControl`)
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx` (add deck mocks + heatmap test)

**Interfaces:**
- Consumes: `MapView({ config, onViewChange? })`, `MapConfig` from `../api/types`, `MockMap`/`mapInstances` from `../test/MockMaplibreMap`.
- Produces:
  - `MockDeckgl.ts` exports: `overlayInstances: MockMapboxOverlay[]`; class `MockMapboxOverlay` with `props: { layers: MockDeckLayer[] }`, `setProps(p)`; mocked layer classes `HeatmapLayer`, `HexagonLayer`, `ColumnLayer` each producing an instance with `deckType: string` (the class name) and `props: Record<string, unknown>`.
  - `MockMap.addControl(control)` recording into `controls: unknown[]`.
  - `MapView` builds one `MapboxOverlay`, adds it via `map.addControl`, and calls `overlay.setProps({ layers })` with a `HeatmapLayer` for each visible `deckType:"heatmap"` layer.

- [ ] **Step 1: Add deck.gl dependencies**

Edit `shell/package.json` `dependencies` (keep alphabetic-ish grouping near `maplibre-gl`), adding:

```json
    "@deck.gl/core": "^9.0.0",
    "@deck.gl/layers": "^9.0.0",
    "@deck.gl/aggregation-layers": "^9.0.0",
    "@deck.gl/mapbox": "^9.0.0",
```

Then install:

Run: `cd shell && npm install`
Expected: installs deck.gl packages, lockfile updated, no peer-dependency errors that block install.

- [ ] **Step 2: Create the Deck.gl test doubles**

Create `shell/src/test/MockDeckgl.ts`:

```ts
export const overlayInstances: MockMapboxOverlay[] = [];

export class MockDeckLayer {
  deckType: string;
  props: Record<string, unknown>;
  constructor(props: Record<string, unknown>) {
    this.props = props;
    this.deckType = (this.constructor as typeof MockDeckLayer).typeName;
  }
  static typeName = "MockDeckLayer";
}

export class HeatmapLayer extends MockDeckLayer {
  static typeName = "HeatmapLayer";
}
export class HexagonLayer extends MockDeckLayer {
  static typeName = "HexagonLayer";
}
export class ColumnLayer extends MockDeckLayer {
  static typeName = "ColumnLayer";
}

export class MockMapboxOverlay {
  props: { layers: MockDeckLayer[] };
  constructor(props: { layers?: MockDeckLayer[] } = {}) {
    this.props = { layers: props.layers ?? [] };
    overlayInstances.push(this);
  }
  setProps(props: { layers: MockDeckLayer[] }) {
    this.props = { ...this.props, ...props };
  }
  // MapboxOverlay implements the maplibre IControl interface.
  onAdd() {
    return document.createElement("div");
  }
  onRemove() {}
}
```

- [ ] **Step 3: Add `addControl` to the MapLibre mock**

Edit `shell/src/test/MockMaplibreMap.ts`: add a `controls` field and `addControl`/`removeControl` methods to `MockMap` (place near `remove()`):

```ts
  controls: unknown[] = [];
```

```ts
  addControl(control: unknown) {
    this.controls.push(control);
    return this;
  }
  removeControl(control: unknown) {
    this.controls = this.controls.filter((c) => c !== control);
    return this;
  }
```

- [ ] **Step 4: Write the failing test (heatmap overlay)**

Edit `shell/src/map/MapView.test.tsx`. Add the deck.gl mocks alongside the existing `maplibre-gl` mock (after it, before `const { MapView } = ...`):

```ts
import { overlayInstances } from "../test/MockDeckgl";

vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});
vi.mock("@deck.gl/aggregation-layers", async () => {
  const { HeatmapLayer, HexagonLayer } = await import("../test/MockDeckgl");
  return { HeatmapLayer, HexagonLayer };
});
vi.mock("@deck.gl/layers", async () => {
  const { ColumnLayer } = await import("../test/MockDeckgl");
  return { ColumnLayer };
});
```

Add `overlayInstances.length = 0;` inside the existing `beforeEach`. Then add the test:

```ts
test("mounts a Deck.gl overlay and adds a HeatmapLayer for a heatmap deck layer", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      {
        id: "heat",
        title: "Heat",
        visible: true,
        kind: "deck",
        deckType: "heatmap",
        dataUrl: "https://fs/points",
        props: { radiusPixels: 30 },
      },
    ],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.controls).toContain(overlayInstances[0]);
  expect(overlayInstances).toHaveLength(1);
  const layers = overlayInstances[0].props.layers;
  expect(layers).toHaveLength(1);
  expect(layers[0].deckType).toBe("HeatmapLayer");
  expect(layers[0].props).toMatchObject({
    id: "heat",
    data: "https://fs/points",
    radiusPixels: 30,
  });
});
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL — new test errors (e.g. `overlayInstances` empty / `map.controls` undefined) because `MapView` does not yet create an overlay.

- [ ] **Step 6: Implement the overlay in MapView**

Edit `shell/src/map/MapView.tsx`. Add imports at top:

```ts
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
```

Add a builder + apply function near `applyLayers`:

```ts
type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;

function buildDeckLayer(layer: DeckLayer) {
  const props = { id: layer.id, data: layer.dataUrl, ...(layer.props ?? {}) };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
  }
}

function applyDeckLayers(overlay: MapboxOverlay, layers: MapConfig["layers"]) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  overlay.setProps({ layers: deckLayers });
}
```

In the `MapView` component, add an overlay ref beside `mapRef`:

```ts
  const overlayRef = useRef<MapboxOverlay | null>(null);
```

In the init effect (the one with `new maplibregl.Map(...)`), after `mapRef.current = map;`, create and add the overlay, and apply deck layers on load:

```ts
    const overlay = new MapboxOverlay({ layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);
```

Change the existing `map.on("load", ...)` to also apply deck layers:

```ts
    map.on("load", () => {
      applyLayers(map, layersRef.current, appliedRef.current);
      applyDeckLayers(overlay, layersRef.current);
    });
```

In the cleanup, null the overlay ref alongside the map:

```ts
    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS — all existing tests plus the new heatmap test.

- [ ] **Step 8: Run the full unit suite + typecheck/build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all test files pass; `tsc --noEmit && vite build` succeeds.

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/test/MockDeckgl.ts shell/src/test/MockMaplibreMap.ts shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "feat(shell): mount Deck.gl overlay in MapView with heatmap layers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: hexbin + column deck types, visibility, and reactive updates

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `buildDeckLayer` / `applyDeckLayers` from Task 1; `overlayInstances` mock.
- Produces: `applyDeckLayers` also re-runs when `config.layers` changes; `buildDeckLayer` covers all three `deckType` values; hidden deck layers excluded.

- [ ] **Step 1: Write the failing tests**

Edit `shell/src/map/MapView.test.tsx`, add:

```ts
test("maps hexbin to HexagonLayer and column to ColumnLayer, excluding hidden deck layers", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [
      { id: "hex", title: "Hex", visible: true, kind: "deck", deckType: "hexbin", dataUrl: "https://fs/a" },
      { id: "col", title: "Col", visible: true, kind: "deck", deckType: "column", dataUrl: "https://fs/b" },
      { id: "off", title: "Off", visible: false, kind: "deck", deckType: "heatmap", dataUrl: "https://fs/c" },
    ],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers.map((l) => l.deckType)).toEqual(["HexagonLayer", "ColumnLayer"]);
  expect(layers.map((l) => l.props.id)).toEqual(["hex", "col"]);
});

test("re-applies deck layers when config.layers changes", () => {
  const first: MapConfig = {
    ...config,
    layers: [{ id: "d1", title: "D1", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "https://fs/1" }],
  };
  const { rerender } = render(<MapView config={first} />);
  const overlay = overlayInstances[0];
  expect(overlay.props.layers.map((l) => l.props.id)).toEqual(["d1"]);

  const second: MapConfig = {
    ...config,
    layers: [{ id: "d2", title: "D2", visible: true, kind: "deck", deckType: "column", dataUrl: "https://fs/2" }],
  };
  rerender(<MapView config={second} />);
  expect(overlay.props.layers.map((l) => l.props.id)).toEqual(["d2"]);
  expect(overlay.props.layers[0].deckType).toBe("ColumnLayer");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL — the "re-applies deck layers" test fails because the `[config.layers]` effect does not yet update the overlay. (The hexbin/column test may already pass from Task 1's `buildDeckLayer`; the reactive test is the real gate.)

- [ ] **Step 3: Update the config-change effect to re-apply deck layers**

Edit `shell/src/map/MapView.tsx`. In the effect keyed on `[config.layers]`, apply deck layers after the MapLibre layers:

```ts
  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !map.loaded() || !overlay) return;
    applyLayers(map, config.layers, appliedRef.current);
    applyDeckLayers(overlay, config.layers);
  }, [config.layers]);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS — all MapView tests including the two new ones.

- [ ] **Step 5: Run the full unit suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "feat(shell): support hexbin/column deck layers and reactive overlay updates

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Include deck layers in the map legend

**Files:**
- Modify: `shell/src/map/MapLegend.tsx`
- Test: `shell/src/map/MapLegend.test.tsx`

**Interfaces:**
- Consumes: `MapLegend({ layers })`, `MapConfig` from `../api/types`.
- Produces: `MapLegend` lists every visible layer including `kind:"deck"`.

- [ ] **Step 1: Write the failing test**

Edit `shell/src/map/MapLegend.test.tsx` (add a test; keep existing ones). If the file does not exist, create it with this content plus a minimal import block matching the existing test style:

```ts
test("lists visible deck layers in the legend", () => {
  const layers: MapConfig["layers"] = [
    { id: "heat", title: "Chaleur", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "d" },
    { id: "off", title: "Cachée", visible: false, kind: "deck", deckType: "heatmap", dataUrl: "d" },
  ];
  render(<MapLegend layers={layers} />);
  expect(screen.getByText("Chaleur")).toBeInTheDocument();
  expect(screen.queryByText("Cachée")).toBeNull();
});
```

(Use the same `render`/`screen` imports already present in the file; if creating it, `import { render, screen } from "@testing-library/react";`, `import { test, expect } from "vitest";`, `import type { MapConfig } from "../api/types";`, `import { MapLegend } from "./MapLegend";`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/map/MapLegend.test.tsx`
Expected: FAIL — "Chaleur" is not found because `MapLegend` filters out `kind:"deck"`.

- [ ] **Step 3: Include deck layers in the legend**

Edit `shell/src/map/MapLegend.tsx`, change the filter to keep visible layers of any kind:

```tsx
  const visible = layers.filter((l) => l.visible);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/map/MapLegend.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full unit suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/MapLegend.tsx shell/src/map/MapLegend.test.tsx
git commit -m "feat(shell): show deck layers in the map legend

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (§10 0c-c):** "Overlay Deck.gl dans MapView (heatmap/hexbin/column)" → Task 1 (mount + heatmap), Task 2 (hexbin/column + visibility + updates). Spec §5 `MapView` "monte un overlay Deck.gl (`@deck.gl/mapbox` `MapboxOverlay`) pour les couches `kind:"deck"`" → Tasks 1–2. Spec §9 "mock `@deck.gl/mapbox`" → Task 1 doubles. Legend of visible layers (§5) extended to deck → Task 3. E2E real render is explicitly deferred to 0c-e (spec §10 0c-e). Deferred-note "per-layer isolation" is scheduled for 0c-e, not here.
- **Placeholder scan:** none — all steps carry concrete code and commands.
- **Type consistency:** `DeckLayer` derived via `Extract<...,{kind:"deck"}>`; `buildDeckLayer`/`applyDeckLayers` names stable across Tasks 1–2; mock class names (`HeatmapLayer`/`HexagonLayer`/`ColumnLayer`/`MockMapboxOverlay`) match the `vi.mock` factories and `MapView` imports; `overlayInstances`/`props.layers`/`deckType` used identically in tests and doubles.
