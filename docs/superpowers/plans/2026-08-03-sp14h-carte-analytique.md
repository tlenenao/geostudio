# SP-14h — Carte analytique : symbologie pilotée par dataset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the GeoStudio shell's existing `map` widget a dataset-driven symbology: `encodings.color` (categorical or numeric field) and `encodings.size` (numeric field, point geometry only), with a legend, editable in its `PropsPanel`.

**Architecture:** Zero backend changes. Two new pure-function modules (`mapSymbology.ts`, consumed by the widget) turn an `{encodings, domain, geometryKind}` triple into a MapLibre `paint` expression and a legend description — exactly the same "pure function reshapes data, component renders it" split already used by `chartOption.ts`/`pivotTable.ts`. The domain (min/max bounds, or distinct values) is fetched with a `statistics` `DataSource` query, reusing the exact pattern already shipped in `sliderFilter.tsx`/`selectFilter.tsx`. One shared file gets a small, strictly additive change: `MapLayer` (kind `"feature"`) gains an optional `renderAs` field that `MapView.tsx` honors instead of hard-coding `"fill"` — absent ⇒ identical behavior to today, so the map editor and any already-saved `MapConfig` are unaffected.

**Tech Stack:** React 18 + TypeScript (shell), Vitest + Testing Library (unit), Playwright (E2E), MapLibre GL JS, `@tanstack/react-query`. No core/Python changes in this plan.

## Global Constraints

- Zero changes to `core/`, `itemClient.ts`, `DataSourcePanel.tsx`, `LayersPanel.tsx`, `MapEditorPage.tsx`, `MapLegend.tsx` — the spec (`docs/superpowers/specs/2026-08-03-sp14h-carte-analytique-design.md`) requires this plan to touch only `shell/src/api/types.ts` and `shell/src/map/MapView.tsx` as shared files; everything else is new files or `mapWidget.tsx`/`mapWidget.test.tsx`.
- `MapLayer`'s new `renderAs?: "fill" | "circle" | "line"` field is optional and additive — absent ⇒ `"fill"` (today's hard-coded behavior), unchanged for every config that doesn't set it (the map editor never will).
- `encodings.size` only ever produces `circle-radius` when the detected geometry kind is `"point"` — never for `"line"`/`"polygon"`, even if `encodings.size` is configured (spec §1 non-buts).
- No user-configurable palette or class breaks in v1 — a fixed 8-color qualitative palette (cycling past 8 distinct values) for categorical color, a fixed 2-stop sequential ramp (`#dbeafe` → `#1e3a8a`) for numeric color, linear `interpolate` only. Circle radius always interpolates 4px → 24px.
- A numeric domain with `min === max` renders a **constant** color/radius, never an `interpolate` expression with two identical stops (MapLibre throws `stops must be strictly ascending` otherwise).
- Domain queries (`groupBy`/`measures` against a `statistics` `DataSource`) only fire when `ctx.data.datasetId` is present — same convention as `selectFilter.tsx`/`sliderFilter.tsx` (`enabled: Boolean(datasetId && field)`).
- All UI strings are in French, matching the rest of the builder (`labelCls`/`inputCls` conventions already used by `pivot.tsx`/`sliderFilter.tsx`).
- Every new file starts with `// SPDX-License-Identifier: Apache-2.0`.
- Commits are conventional (`feat(shell): ... (SP-14h)`), small, one subject per commit.

---

## Task 1: `mapSymbology.ts` — geometry detection, paint expressions, legend spec

**Files:**
- Create: `shell/src/builder/widgets/mapSymbology.ts`
- Test: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: nothing from other tasks (pure module, no imports beyond its own types).
- Produces (consumed by Task 3):
  ```ts
  export type GeometryKind = "point" | "line" | "polygon";
  export type ColorDomain = { kind: "categorical"; values: string[] } | { kind: "numeric"; min: number; max: number };
  export type SizeDomain = { min: number; max: number };
  export type MapEncodings = {
    color?: { field: string; mode: "categorical" | "numeric" };
    size?: { field: string };
  };
  export type MapPaintResult = { renderAs: "fill" | "circle" | "line"; paint: Record<string, unknown> };
  export type LegendSpec = {
    color?:
      | { kind: "categorical"; field: string; entries: { value: string; color: string }[] }
      | { kind: "numeric"; field: string; min: number; max: number; colorLow: string; colorHigh: string };
    size?: { field: string; min: number; max: number; radiusMin: number; radiusMax: number };
  };
  export function detectGeometryKind(geometry: unknown): GeometryKind;
  export function buildMapPaint(
    encodings: MapEncodings | undefined,
    colorDomain: ColorDomain | null,
    sizeDomain: SizeDomain | null,
    geometryKind: GeometryKind,
  ): MapPaintResult;
  export function buildLegend(
    encodings: MapEncodings | undefined,
    colorDomain: ColorDomain | null,
    sizeDomain: SizeDomain | null,
    geometryKind: GeometryKind,
  ): LegendSpec | null;
  ```

- [ ] **Step 1: Write the failing test file**

Create `shell/src/builder/widgets/mapSymbology.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { buildLegend, buildMapPaint, detectGeometryKind } from "./mapSymbology";

test("detectGeometryKind maps GeoJSON types to a rendering kind", () => {
  expect(detectGeometryKind({ type: "Point" })).toBe("point");
  expect(detectGeometryKind({ type: "MultiPoint" })).toBe("point");
  expect(detectGeometryKind({ type: "LineString" })).toBe("line");
  expect(detectGeometryKind({ type: "MultiLineString" })).toBe("line");
  expect(detectGeometryKind({ type: "Polygon" })).toBe("polygon");
  expect(detectGeometryKind({ type: "MultiPolygon" })).toBe("polygon");
  expect(detectGeometryKind(undefined)).toBe("polygon");
  expect(detectGeometryKind(null)).toBe("polygon");
});

test("buildMapPaint returns a match expression with a trailing default color for a categorical domain", () => {
  const { renderAs, paint } = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "polygon",
  );
  expect(renderAs).toBe("fill");
  expect(paint["fill-color"]).toEqual([
    "match", ["get", "region"],
    "Nord", "#2563eb",
    "Sud", "#dc2626",
    "#2563eb",
  ]);
});

test("cycles the categorical palette past 8 distinct values", () => {
  const values = Array.from({ length: 9 }, (_, i) => `v${i}`);
  const { paint } = buildMapPaint({ color: { field: "cat", mode: "categorical" } }, { kind: "categorical", values }, null, "polygon");
  const match = paint["fill-color"] as unknown[];
  // ["match", ["get","cat"], v0,c0, v1,c1, ..., v8,c8, default] — v8 is the
  // 9th distinct value (index 8) and must reuse c0 (palette wraps at 8).
  expect(match[2]).toBe("v0");
  expect(match[3]).toBe("#2563eb");
  expect(match[18]).toBe("v8");
  expect(match[19]).toBe("#2563eb");
});

test("buildMapPaint returns an interpolate expression for a numeric color domain", () => {
  const { paint } = buildMapPaint({ color: { field: "valeur", mode: "numeric" } }, { kind: "numeric", min: 0, max: 100 }, null, "point");
  expect(paint["circle-color"]).toEqual(["interpolate", ["linear"], ["get", "valeur"], 0, "#dbeafe", 100, "#1e3a8a"]);
});

test("a numeric color domain with min === max renders a constant color, not an interpolate expression", () => {
  const { paint } = buildMapPaint({ color: { field: "valeur", mode: "numeric" } }, { kind: "numeric", min: 5, max: 5 }, null, "polygon");
  expect(paint["fill-color"]).toBe("#dbeafe");
});

test("renderAs follows the geometry kind, independent of encodings", () => {
  expect(buildMapPaint(undefined, null, null, "point").renderAs).toBe("circle");
  expect(buildMapPaint(undefined, null, null, "line").renderAs).toBe("line");
  expect(buildMapPaint(undefined, null, null, "polygon").renderAs).toBe("fill");
});

test("size encoding produces a circle-radius interpolate expression only for point geometry", () => {
  const point = buildMapPaint({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "point");
  expect(point.paint["circle-radius"]).toEqual(["interpolate", ["linear"], ["get", "montant"], 0, 4, 50, 24]);

  const polygon = buildMapPaint({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "polygon");
  expect(polygon.paint["circle-radius"]).toBeUndefined();
});

test("a size domain with min === max renders a constant radius", () => {
  const { paint } = buildMapPaint({ size: { field: "montant" } }, null, { min: 10, max: 10 }, "point");
  expect(paint["circle-radius"]).toBe(4);
});

test("no active encodings produce an empty paint object", () => {
  const { paint } = buildMapPaint(undefined, null, null, "polygon");
  expect(paint).toEqual({});
});

test("buildLegend returns null when no encoding is active", () => {
  expect(buildLegend(undefined, null, null, "polygon")).toBeNull();
});

test("buildLegend builds a categorical color section", () => {
  const legend = buildLegend({ color: { field: "region", mode: "categorical" } }, { kind: "categorical", values: ["Nord", "Sud"] }, null, "polygon");
  expect(legend).toEqual({
    color: {
      kind: "categorical", field: "region",
      entries: [{ value: "Nord", color: "#2563eb" }, { value: "Sud", color: "#dc2626" }],
    },
  });
});

test("buildLegend builds a numeric color section", () => {
  const legend = buildLegend({ color: { field: "valeur", mode: "numeric" } }, { kind: "numeric", min: 0, max: 100 }, null, "point");
  expect(legend).toEqual({
    color: { kind: "numeric", field: "valeur", min: 0, max: 100, colorLow: "#dbeafe", colorHigh: "#1e3a8a" },
  });
});

test("buildLegend builds a size section only for point geometry", () => {
  const onPoint = buildLegend({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "point");
  expect(onPoint).toEqual({ size: { field: "montant", min: 0, max: 50, radiusMin: 4, radiusMax: 24 } });

  const onPolygon = buildLegend({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "polygon");
  expect(onPolygon).toBeNull();
});

test("buildLegend combines color and size sections when both encodings are active", () => {
  const legend = buildLegend(
    { color: { field: "region", mode: "categorical" }, size: { field: "montant" } },
    { kind: "categorical", values: ["Nord"] },
    { min: 0, max: 10 },
    "point",
  );
  expect(legend).toEqual({
    color: { kind: "categorical", field: "region", entries: [{ value: "Nord", color: "#2563eb" }] },
    size: { field: "montant", min: 0, max: 10, radiusMin: 4, radiusMax: 24 },
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npm run test -- mapSymbology.test.ts`
Expected: FAIL — `Cannot find module './mapSymbology'` (file does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `shell/src/builder/widgets/mapSymbology.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
export type GeometryKind = "point" | "line" | "polygon";

export type ColorDomain =
  | { kind: "categorical"; values: string[] }
  | { kind: "numeric"; min: number; max: number };

export type SizeDomain = { min: number; max: number };

export type MapEncodings = {
  color?: { field: string; mode: "categorical" | "numeric" };
  size?: { field: string };
};

export type MapPaintResult = { renderAs: "fill" | "circle" | "line"; paint: Record<string, unknown> };

export type LegendSpec = {
  color?:
    | { kind: "categorical"; field: string; entries: { value: string; color: string }[] }
    | { kind: "numeric"; field: string; min: number; max: number; colorLow: string; colorHigh: string };
  size?: { field: string; min: number; max: number; radiusMin: number; radiusMax: number };
};

const CATEGORICAL_PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];
const NUMERIC_COLOR_LOW = "#dbeafe";
const NUMERIC_COLOR_HIGH = "#1e3a8a";
const SIZE_RADIUS_MIN = 4;
const SIZE_RADIUS_MAX = 24;

function paletteColor(index: number): string {
  return CATEGORICAL_PALETTE[index % CATEGORICAL_PALETTE.length];
}

// GeoJSON geometry.type → the MapLibre layer type that can render it and
// carry a data-driven symbology (spec §3): points get circles (the only
// geometry a size encoding can apply to), lines/polygons keep the existing
// line/fill rendering. Absent/unrecognized geometry defaults to "polygon"
// (identical to today's hard-coded "fill" behavior — see Task 2).
export function detectGeometryKind(geometry: unknown): GeometryKind {
  const type = (geometry as { type?: string } | null | undefined)?.type;
  if (type === "Point" || type === "MultiPoint") return "point";
  if (type === "LineString" || type === "MultiLineString") return "line";
  return "polygon";
}

function colorPaintProperty(renderAs: "fill" | "circle" | "line"): string {
  if (renderAs === "circle") return "circle-color";
  if (renderAs === "line") return "line-color";
  return "fill-color";
}

export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
): MapPaintResult {
  const renderAs: "fill" | "circle" | "line" =
    geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
  const paint: Record<string, unknown> = {};

  if (encodings?.color && colorDomain) {
    const prop = colorPaintProperty(renderAs);
    if (colorDomain.kind === "categorical") {
      const match: unknown[] = ["match", ["get", encodings.color.field]];
      colorDomain.values.forEach((value, i) => match.push(value, paletteColor(i)));
      match.push(paletteColor(0)); // default color for a value outside the observed domain
      paint[prop] = match;
    } else if (colorDomain.min === colorDomain.max) {
      paint[prop] = NUMERIC_COLOR_LOW;
    } else {
      paint[prop] = ["interpolate", ["linear"], ["get", encodings.color.field],
        colorDomain.min, NUMERIC_COLOR_LOW, colorDomain.max, NUMERIC_COLOR_HIGH];
    }
  }

  if (encodings?.size && sizeDomain && renderAs === "circle") {
    paint["circle-radius"] = sizeDomain.min === sizeDomain.max
      ? SIZE_RADIUS_MIN
      : ["interpolate", ["linear"], ["get", encodings.size.field],
        sizeDomain.min, SIZE_RADIUS_MIN, sizeDomain.max, SIZE_RADIUS_MAX];
  }

  return { renderAs, paint };
}

export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
): LegendSpec | null {
  const legend: LegendSpec = {};

  if (encodings?.color && colorDomain) {
    legend.color = colorDomain.kind === "categorical"
      ? {
          kind: "categorical", field: encodings.color.field,
          entries: colorDomain.values.map((value, i) => ({ value, color: paletteColor(i) })),
        }
      : {
          kind: "numeric", field: encodings.color.field,
          min: colorDomain.min, max: colorDomain.max,
          colorLow: NUMERIC_COLOR_LOW, colorHigh: NUMERIC_COLOR_HIGH,
        };
  }

  // Size legend only makes sense where size is actually rendered (points).
  if (encodings?.size && sizeDomain && geometryKind === "point") {
    legend.size = {
      field: encodings.size.field, min: sizeDomain.min, max: sizeDomain.max,
      radiusMin: SIZE_RADIUS_MIN, radiusMax: SIZE_RADIUS_MAX,
    };
  }

  return legend.color || legend.size ? legend : null;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npm run test -- mapSymbology.test.ts`
Expected: PASS — 14 tests green.

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/widgets/mapSymbology.ts src/builder/widgets/mapSymbology.test.ts
git commit -m "feat(shell): mapSymbology builds MapLibre paint expressions and a legend spec from dataset encodings (SP-14h)"
```

---

## Task 2: `MapLayer.renderAs` — additive field honored by `MapView`

**Files:**
- Modify: `shell/src/api/types.ts:62`
- Modify: `shell/src/map/MapView.tsx:56-58`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: nothing from Task 1 (independent, purely additive change to shared map rendering).
- Produces (consumed by Task 3): `MapLayer` (kind `"feature"`) now accepts an optional `renderAs?: "fill" | "circle" | "line"`; `MapView` renders that MapLibre layer `type` instead of the hard-coded `"fill"`, defaulting to `"fill"` when absent.

- [ ] **Step 1: Write the failing tests**

In `shell/src/map/MapView.test.tsx`, add these three tests right after the existing `"re-applies layers when config.layers changes"` test (after its closing `});`, before `"reports view changes on moveend"`):

```ts
test("renders a circle layer for a feature layer with renderAs \"circle\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "pts", title: "Points", visible: true, kind: "feature", url: "https://fs/pts", renderAs: "circle", paint: { "circle-color": "#111" } }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("pts")).toMatchObject({ type: "circle", source: "pts", paint: { "circle-color": "#111" } });
});

test("renders a line layer for a feature layer with renderAs \"line\"", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "lns", title: "Lignes", visible: true, kind: "feature", url: "https://fs/lns", renderAs: "line" }],
  };
  render(<MapView config={cfg} />);
  const map = mapInstances[0];
  expect(map.getLayer("lns")).toMatchObject({ type: "line", source: "lns" });
});

test("defaults a feature layer to fill when renderAs is not set", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "poly", title: "Polygones", visible: true, kind: "feature", url: "https://fs/poly" }],
  };
  render(<MapView config={cfg} />);
  expect(mapInstances[0].getLayer("poly")).toMatchObject({ type: "fill", source: "poly" });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npm run test -- MapView.test.tsx`
Expected: FAIL — the first two new tests fail (`type` is `"fill"` for both, since MapView doesn't know about `renderAs` yet, and TypeScript itself would already reject `renderAs` as an unknown property on `MapLayer` until Step 3's type change lands). The third test passes already (it doesn't exercise anything new).

- [ ] **Step 3: Add `renderAs` to `MapLayer` and honor it in `MapView`**

In `shell/src/api/types.ts`, change line 62 from:

```ts
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown> }
```

to:

```ts
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown>; renderAs?: "fill" | "circle" | "line" }
```

In `shell/src/map/MapView.tsx`, change (lines 56-58):

```ts
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: layer.paint ?? {} });
```

to:

```ts
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        map.addLayer({ id: layer.id, type: layer.renderAs ?? "fill", source: layer.id, paint: layer.paint ?? {} });
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npm run test -- MapView.test.tsx`
Expected: PASS — all tests green, including the 3 new ones.

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS — no other suite references `MapLayer`'s `feature` variant in a way that would break from an additive optional field.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/api/types.ts src/map/MapView.tsx src/map/MapView.test.tsx
git commit -m "feat(shell): MapLayer gains an optional renderAs, honored by MapView for feature layers (SP-14h)"
```

---

## Task 3: `map` widget — color/size encodings, domain queries, legend overlay

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `detectGeometryKind`, `buildMapPaint`, `buildLegend`, `MapEncodings`, `ColorDomain`, `SizeDomain`, `LegendSpec` from Task 1 (`./mapSymbology`); `MapLayer.renderAs` from Task 2 (`../../api/types`); `useItemClient` from `../../api/ItemClientProvider` (pre-existing, used the same way by `sliderFilter.tsx`/`selectFilter.tsx`).
- Produces: nothing consumed by later tasks — Task 4's E2E tests exercise this widget only through the real builder UI (palette button `"Carte"`, PropsPanel fields `"Champ couleur"`/`"Type de couleur"`/`"Champ taille"`), not by importing anything from this file.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `shell/src/builder/widgets/mapWidget.test.tsx` with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { ExplorerProvider } from "../ExplorerContext";

const flyToSpy = vi.fn();
const highlightSpy = vi.fn();

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange, onFeatureClick }: {
        config: { layers: { url?: string; renderAs?: string; paint?: Record<string, unknown> }[] };
        onViewChange?: (v: { center: [number, number]; zoom: number; bbox: [number, number, number, number] }) => void;
        onFeatureClick?: (record: { id: string | number; properties: Record<string, unknown>; geometry?: unknown }) => void;
      },
      ref: React.Ref<{ flyTo: unknown; highlight: unknown }>,
    ) => {
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight: highlightSpy }));
      const layer = config.layers[0];
      return (
        <div data-testid="mapview" onClick={() => onViewChange?.({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] })}>
          layers:{config.layers.length} url:{layer?.url ?? ""} renderAs:{layer?.renderAs ?? ""} paint:{JSON.stringify(layer?.paint ?? {})}
          <button
            type="button"
            data-testid="feature"
            onClick={() => onFeatureClick?.({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } })}
          >
            feature
          </button>
        </div>
      );
    },
  ),
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); flyToSpy.mockClear(); highlightSpy.mockClear(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

// Every Component test now needs QueryClientProvider + ItemClientProvider —
// the widget calls useItemClient()/useQuery() unconditionally to fetch a
// color/size domain, same as sliderFilter.tsx/selectFilter.tsx already do.
// Pre-existing tests never configure `encodings`, so those two domain
// queries stay `enabled: false` and `queryDataSource` is never actually
// invoked for them — a bare vi.fn() default is safe.
function withClient(children: React.ReactNode, queryDataSource: ReturnType<typeof vi.fn> = vi.fn()) {
  const client = { queryDataSource } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("registers with a 6x6 default size", () => {
  expect(getWidget("map")!.defaultSize).toEqual({ w: 6, h: 6 });
});

test("PropsPanel edits the color and size encodings", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("map")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{}} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  // Single characters only: props never gets fed back between keystrokes in
  // this test (same convention as pivot.test.tsx's PropsPanel test), so each
  // assertion reflects setEncodings() merging against the still-empty base
  // `props={{}}`, not an accumulated string.
  await userEvent.type(screen.getByLabelText("Champ couleur"), "r");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "r", mode: "categorical" } } }));
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { color: { field: "", mode: "numeric" } } }));
  await userEvent.type(screen.getByLabelText("Champ taille"), "m");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ encodings: { size: { field: "m" } } }));
});

test("map widget builds a feature layer from the bound source url", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: state({ url: "https://fs/parcs/items.json", records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:1");
  expect(view).toHaveTextContent("url:https://fs/parcs/items.json");
});

test("map widget renders an empty map when no source is bound", async () => {
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />));
  const view = await screen.findByTestId("mapview");
  expect(view).toHaveTextContent("layers:0");
});

test("map declares extentChanged/itemSelected events and flyTo/highlight actions", () => {
  expect(getWidget("map")!.events).toEqual(["extentChanged", "itemSelected"]);
  expect(getWidget("map")!.actions).toEqual(expect.arrayContaining(["flyTo", "highlight"]));
});

test("map emits extentChanged when the view moves", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "extentChanged", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("mapview"));
  expect(handler).toHaveBeenCalledWith({ center: [1, 2], zoom: 9, bbox: [10, 20, 30, 40] });
});

test("map flyTo action flies to a selected record's point", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "list1", event: "itemSelected", to: "map1", action: "flyTo" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await screen.findByTestId("mapview");
  bus.emit("list1", "itemSelected", { id: 1, properties: {}, geometry: { type: "Point", coordinates: [5, 6] } });
  expect(flyToSpy).toHaveBeenCalledWith({ center: [5, 6], zoom: 12 });
});

test("map emits itemSelected when a feature is clicked", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "map1", event: "itemSelected", to: "sink", action: "log" }]);
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{}} ctx={{ mode: "runtime", bus, widgetId: "map1" } as WidgetContext} />));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(handler).toHaveBeenCalledWith({ id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [5, 6] } });
});

test("map sets the extent (debounced by the provider) when the view moves and interactions is auto", async () => {
  function ExtentProbe() {
    const ctx = useAnalyticsContext();
    return <p>extent:{ctx.extent ? ctx.extent.join(",") : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{}} ctx={{ mode: "runtime" } as WidgetContext} />
      <ExtentProbe />
    </AnalyticsContextProvider>,
  ));
  const view = await screen.findByTestId("mapview");
  vi.useFakeTimers();
  try {
    fireEvent.click(view);
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.getByText("extent:10,20,30,40")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("map sets a cross-filter by pkColumn on feature click when dataset-bound", async () => {
  function CrossFilterProbe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const Map = getWidget("map")!.Component;
  const data = { loading: false, error: false, records: [], datasetId: "dataset-1", pkColumn: "id" };
  render(withClient(
    <AnalyticsContextProvider interactions="auto">
      <Map props={{ dataSourceId: "src-1" }} ctx={{ mode: "runtime", data } as WidgetContext} />
      <CrossFilterProbe />
    </AnalyticsContextProvider>,
  ));
  await userEvent.click(await screen.findByTestId("feature"));
  expect(await screen.findByText("cf:id=1")).toBeInTheDocument();
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const Map = getWidget("map")!.Component;
  const ctx = { mode: "runtime", data: { loading: false, error: false, records: [], datasetId: "ds1", url: "https://core/collections/geo/items" } } as unknown as WidgetContext;
  render(withClient(<ExplorerProvider enabled><Map props={{ dataSourceId: "src1" }} ctx={ctx} /></ExplorerProvider>));
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("colors features by a categorical field once the domain query resolves", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { groupBy?: string } }) => {
    if (source.query?.groupBy === "region") {
      return [{ id: "Nord", properties: { value: 2 } }, { id: "Sud", properties: { value: 1 } }];
    }
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  await waitFor(() => expect(view.textContent).toContain('"fill-color"'));
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("#2563eb");
  expect(view.textContent).toContain("#dc2626");
});

test("colors and sizes point features by numeric fields once both domain queries resolve", async () => {
  const queryDataSource = vi.fn(async (source: { query?: { measures?: { field: string }[] } }) => {
    const field = source.query?.measures?.[0]?.field;
    if (field === "valeur") return [{ id: "s", properties: { min: 0, max: 100 } }];
    if (field === "montant") return [{ id: "s", properties: { min: 5, max: 25 } }];
    return [];
  });
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/points/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "valeur", mode: "numeric" }, size: { field: "montant" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  const view = await screen.findByTestId("mapview");
  // Both domain queries (color, size) resolve independently — wait for both
  // paint keys inside the same waitFor so a flush of just one doesn't pass
  // the assertion prematurely.
  await waitFor(() => {
    expect(view.textContent).toContain('"circle-radius"');
    expect(view.textContent).toContain('"circle-color"');
  });
  expect(view.textContent).toContain("renderAs:circle");
});

test("shows no symbology legend when no encoding is configured", () => {
  const ctx = { mode: "runtime", data: state({ url: "https://fs/communes/items.json" }) } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(<Map props={{ dataSourceId: "d" }} ctx={ctx} />));
  expect(screen.queryByText("Nord")).not.toBeInTheDocument();
});

test("shows a categorical symbology legend once the color domain resolves", async () => {
  const queryDataSource = vi.fn(async () => [{ id: "Nord", properties: { value: 1 } }, { id: "Sud", properties: { value: 1 } }]);
  const ctx = {
    mode: "runtime",
    data: state({
      url: "https://fs/communes/items.json", datasetId: "ds-1",
      records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
    }),
  } as WidgetContext;
  const Map = getWidget("map")!.Component;
  render(withClient(
    <Map props={{ dataSourceId: "d", encodings: { color: { field: "region", mode: "categorical" } } }} ctx={ctx} />,
    queryDataSource,
  ));
  expect(await screen.findByText("Nord")).toBeInTheDocument();
  expect(screen.getByText("Sud")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npm run test -- mapWidget.test.tsx`
Expected: FAIL — every test that renders `<Map .../>` throws `useItemClient must be used within an ItemClientProvider` (the widget doesn't call `useItemClient`/`useQuery` yet, so `withClient`'s providers are inert, but more importantly `PropsPanel` has no color/size fields yet and `encodings`-related tests find nothing to assert on).

- [ ] **Step 3: Write the widget implementation**

Replace the full contents of `shell/src/builder/widgets/mapWidget.tsx` with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { buildLegend, buildMapPaint, detectGeometryKind } from "./mapSymbology";
import type { ColorDomain, LegendSpec, MapEncodings, SizeDomain } from "./mapSymbology";
import type { ItemClient, MapConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function centerFromPayload(p: unknown): [number, number] | null {
  const rec = p as { center?: [number, number]; geometry?: { type?: string; coordinates?: number[] } } | undefined;
  if (rec?.center) return rec.center;
  const g = rec?.geometry;
  if (g?.type === "Point" && Array.isArray(g.coordinates)) return [g.coordinates[0], g.coordinates[1]];
  return null;
}

function geometryFromPayload(p: unknown): unknown | null {
  return (p as { geometry?: unknown } | undefined)?.geometry ?? null;
}

// Bornes min/max d'un champ numérique, interrogées séparément de la
// DataSource "features" qui alimente le rendu — même patron que
// sliderFilter.tsx (measures min/max sur une source "statistics").
function useNumericDomain(client: ItemClient, datasetId: string | undefined, field: string, active: boolean) {
  return useQuery({
    queryKey: ["map-numeric-domain", datasetId, field],
    queryFn: async (): Promise<SizeDomain> => {
      const rows = await client.queryDataSource({
        id: `map-domain-${datasetId}-${field}`, type: "statistics", service: "core",
        layer: "", datasetId, query: { measures: [{ field, agg: "min" }, { field, agg: "max" }] },
      });
      const properties = rows[0]?.properties ?? {};
      return { min: Number(properties.min ?? 0), max: Number(properties.max ?? 0) };
    },
    enabled: active && Boolean(datasetId && field),
  });
}

function MapSymbologyLegend({ legend }: { legend: LegendSpec }) {
  return (
    <div className="absolute bottom-2 right-2 z-10 flex flex-col gap-2 rounded-md bg-white/90 p-2 text-xs shadow">
      {legend.color?.kind === "categorical" && (
        <ul>
          {legend.color.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: e.color }} />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "numeric" && (
        <div>
          <div className="h-2 w-24 rounded"
            style={{ background: `linear-gradient(to right, ${legend.color.colorLow}, ${legend.color.colorHigh})` }} />
          <span>{legend.color.min} – {legend.color.max}</span>
        </div>
      )}
      {legend.size && (
        <div className="flex items-end gap-2">
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMin, height: legend.size.radiusMin }} />
          <span className="rounded-full bg-slate-500" style={{ width: legend.size.radiusMax, height: legend.size.radiusMax }} />
          <span>{legend.size.min} – {legend.size.max}</span>
        </div>
      )}
    </div>
  );
}

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const setEncodings = (patch: MapEncodings) => onChange({ ...props, encodings: { ...encodings, ...patch } });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className={labelCls}>Champ couleur
            <input aria-label="Champ couleur" className={inputCls}
              value={String(encodings.color?.field ?? "")}
              onChange={(e) => setEncodings({ color: { field: e.target.value, mode: encodings.color?.mode ?? "categorical" } })} />
          </label>
          <label className={labelCls}>Type de couleur
            <select aria-label="Type de couleur" className={inputCls}
              value={encodings.color?.mode ?? "categorical"}
              onChange={(e) => setEncodings({ color: { field: encodings.color?.field ?? "", mode: e.target.value as "categorical" | "numeric" } })}>
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          <label className={labelCls}>Champ taille
            <input aria-label="Champ taille" className={inputCls}
              value={String(encodings.size?.field ?? "")}
              onChange={(e) => setEncodings({ size: { field: e.target.value } })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });

      const encodings = (props.encodings as MapEncodings | undefined) ?? {};
      const datasetId = ctx.data?.datasetId;
      const colorField = encodings.color?.field ?? "";
      const colorMode = encodings.color?.mode ?? "categorical";
      const sizeField = encodings.size?.field ?? "";

      const categoricalQuery = useQuery({
        queryKey: ["map-categorical-domain", datasetId, colorField],
        queryFn: async (): Promise<string[]> => {
          const rows = await client.queryDataSource({
            id: `map-domain-${datasetId}-${colorField}`, type: "statistics", service: "core",
            layer: "", datasetId, query: { groupBy: colorField },
          });
          return rows.map((r) => String(r.id));
        },
        enabled: Boolean(datasetId && colorField && colorMode === "categorical"),
      });
      const numericColorQuery = useNumericDomain(client, datasetId, colorField, colorMode === "numeric");
      const sizeQuery = useNumericDomain(client, datasetId, sizeField, true);

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

      const colorDomain: ColorDomain | null = !colorField
        ? null
        : colorMode === "categorical"
          ? (categoricalQuery.data ? { kind: "categorical", values: categoricalQuery.data } : null)
          : (numericColorQuery.data ? { kind: "numeric", ...numericColorQuery.data } : null);
      const sizeDomain: SizeDomain | null = sizeField && sizeQuery.data ? sizeQuery.data : null;
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      const { renderAs, paint } = buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind);
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind);

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [{ id: `ds-${String(props.dataSourceId)}`, title: "Données", visible: true, kind: "feature", url, renderAs, paint }]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={ctx.data?.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn) setCrossFilter(datasetId, pkColumn, String(record.id), String(props.dataSourceId ?? ""));
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npm run test -- mapWidget.test.tsx`
Expected: PASS — 15 tests green.

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS — all existing suites remain green, plus `mapSymbology.test.ts` (Task 1), the extended `MapView.test.tsx` (Task 2) and the rewritten `mapWidget.test.tsx`.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/builder/widgets/mapWidget.tsx src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): map widget colors and sizes features from dataset encodings, with a legend (SP-14h)"
```

---

## Task 4: E2E — categorical legend, numeric color+size legend, cross-filter regression, unconfigured no-op

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` (already defined at the top of this file, unmodified); the `map` widget's new PropsPanel fields, addressable via labels `"Champ couleur"` / `"Type de couleur"` / `"Champ taille"`.
- Produces: nothing consumed by later tasks — this is the last task in the plan.

- [ ] **Step 1: Write the four E2E tests**

Append to the end of `shell/e2e/analytics-context.spec.ts` (after the last existing test, the SP-14g unconfigured-pivot scenario):

```ts
// -------------------------------------------------------------------------
// Scénario 22 (SP-14h) — couleur catégorielle : le widget Carte colore une
// couche polygonale par un champ catégoriel ; la légende affiche les valeurs
// distinctes obtenues via une requête statistics (groupBy) séparée de la
// DataSource "features" qui alimente la géométrie.
// -------------------------------------------------------------------------
test("a map with a categorical color encoding shows a legend built from a groupBy domain query (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/communes/schema", async (route) => {
    await route.fulfill({
      json: { collection: "communes", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/communes/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, geometry: { type: "Polygon", coordinates: [[[2, 46], [3, 46], [3, 47], [2, 47], [2, 46]]] }, properties: { region: "Nord" } },
          { id: 2, geometry: { type: "Polygon", coordinates: [[[2, 44], [3, 44], [3, 45], [2, 45], [2, 44]]] }, properties: { region: "Sud" } },
        ],
      },
    });
  });
  await page.route("**/collections/communes/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "region", rows: [{ region: "Nord", value: 1 }, { region: "Sud", value: 1 }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "communes", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte catégorielle");
  await addFeaturesSource(page, "communes");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("region");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Nord")).toBeVisible();
  await expect(page.getByText("Sud")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 23 (SP-14h) — couleur + taille numériques : le widget Carte
// dimensionne et colore une couche ponctuelle par deux champs numériques ;
// la légende affiche les bornes des deux domaines (deux requêtes
// statistics distinctes, une par champ).
// -------------------------------------------------------------------------
test("a map with numeric color and size encodings shows a legend with both domains' bounds (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/points/schema", async (route) => {
    await route.fulfill({
      json: { collection: "points", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 },
        fields: [{ name: "valeur", type: "number" }, { name: "montant", type: "number" }] },
    });
  });
  await page.route("**/collections/points/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, geometry: { type: "Point", coordinates: [2.3, 46.5] }, properties: { valeur: 10, montant: 2 } },
          { id: 2, geometry: { type: "Point", coordinates: [2.5, 46.7] }, properties: { valeur: 90, montant: 18 } },
        ],
      },
    });
  });
  await page.route("**/collections/points/aggregate", async (route) => {
    const body = route.request().postDataJSON() as { measures?: { field: string }[] };
    const field = body.measures?.[0]?.field;
    if (field === "valeur") {
      await route.fulfill({ json: { categoryKey: "valeur", rows: [{ min: 10, max: 90 }] } });
      return;
    }
    await route.fulfill({ json: { categoryKey: "montant", rows: [{ min: 2, max: 18 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "points", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte numérique");
  await addFeaturesSource(page, "points");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("valeur");
  await page.getByLabel("Type de couleur").selectOption("numeric");
  await page.getByLabel("Champ taille").fill("montant");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("10 – 90")).toBeVisible();
  await expect(page.getByText("2 – 18")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 24 (SP-14h) — non-régression : un clic sur une entité stylée
// déclenche toujours le cross-filter par pk (comportement pk existant,
// inchangé par la symbologie). Fixture : une entité (id=1) en polygone
// couvrant tout le viewport par défaut (center [2.4,46.6], zoom 5), une
// seconde (id=2) placée hors champ (jamais rendue à l'écran) — n'importe
// quel clic sur le canvas ne peut donc toucher que id=1, sans dépendre
// d'un calcul précis de projection Web Mercator.
// -------------------------------------------------------------------------
test("a click on a styled map feature still cross-filters a sibling table by pk (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/zones/schema", async (route) => {
    await route.fulfill({
      json: { collection: "zones", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/zones/items*", async (route) => {
    const url = new URL(route.request().url());
    const id = url.searchParams.get("id");
    const all = [
      { id: 1, geometry: { type: "Polygon", coordinates: [[[-20, 30], [30, 30], [30, 65], [-20, 65], [-20, 30]]] }, properties: { region: "Nord" } },
      { id: 2, geometry: { type: "Polygon", coordinates: [[[170, -80], [175, -80], [175, -75], [170, -75], [170, -80]]] }, properties: { region: "Sud" } },
    ];
    const features = id ? all.filter((f) => String(f.id) === id) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/zones/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "region", rows: [{ region: "Nord", value: 1 }, { region: "Sud", value: 1 }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "zones", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte cross-filter");
  await addFeaturesSource(page, "zones");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "zones");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("region");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });
  await page.getByLabel("Colonnes").fill("region");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/zones/items") && r.url().includes("id=1"));
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 25 (SP-14h) — non-régression : sans encodings configurés, le
// widget Carte se comporte exactement comme avant (aucune requête statistics
// de domaine n'est émise).
// -------------------------------------------------------------------------
test("a map with no encodings configured issues no domain query (SP-14h)", async ({ page }) => {
  await mockCore(page);
  let aggregateCalls = 0;
  await page.route("**/collections/parcelles/schema", async (route) => {
    await route.fulfill({
      json: { collection: "parcelles", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/parcelles/items*", async (route) => {
    await route.fulfill({
      json: { type: "FeatureCollection", features: [
        { id: 1, geometry: { type: "Polygon", coordinates: [[[2, 46], [3, 46], [3, 47], [2, 47], [2, 46]]] }, properties: { region: "Nord" } },
      ] },
    });
  });
  await page.route("**/collections/parcelles/aggregate", async (route) => {
    aggregateCalls++;
    await route.fulfill({ json: { categoryKey: "region", rows: [] } });
  });

  await createApp(page, "Carte sans symbologie");
  await addFeaturesSource(page, "parcelles");

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  const itemsReq = page.waitForRequest((r) => r.url().includes("/collections/parcelles/items"));
  await page.goto("/apps/9");
  await itemsReq;
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  expect(aggregateCalls).toBe(0);
});
```

- [ ] **Step 2: Run the four new E2E tests**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts -g "SP-14h"`
Expected: PASS — 4 tests green. If a selector or assertion fails, use Playwright's trace/HTML report (`npx playwright show-report`) to inspect the actual DOM and adjust the test to match real rendered output — do not change the widget implementation to satisfy an incorrect test expectation without re-checking the spec first.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS — all existing specs remain green (72+ scenarios), plus the 4 new SP-14h scenarios.

- [ ] **Step 4: Run the full non-regression check (unit + build)**

Run: `cd shell && npm run test && npm run build`
Expected: PASS — full Vitest suite green, `tsc --noEmit` clean, Vite build succeeds.

- [ ] **Step 5: Commit**

```bash
cd shell && git add e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover map categorical/numeric symbology legends, pk cross-filter regression and no-encodings no-op (SP-14h)"
```
