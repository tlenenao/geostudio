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

