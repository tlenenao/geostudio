## Task 6: Shell — classification, palette-aware paint/legend, and orchestration in `mapSymbology.ts`

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`
- Modify: `shell/src/api/types.ts` (`MapLayer.symbology`, `LegendSpec.color` classed variant)

**Interfaces:**
- Consumes: `PaletteId`, `ResolvedPalette`, `resolvePalette`,
  `colorsForClasses` from `./palette` (Task 4); `DataRecord`, `ThemeColors`
  from `../../api/types`.
- Produces: `ColorClassification`, `LayerSymbology`, extended `ColorDomain`
  (adds `"numeric-classed"`), `equalIntervalBreaks(min, max, classes)`,
  `quantileMeasures(field, classes)`, `quantileBreaksFromRow(row, classes)`,
  `jenksBreaks(sample, classes)`, `computeColorDomain(params, deps)`,
  `computeSizeDomain(field, deps)`, `symbologyToPaintInputs(symbology,
  themeColors)`, extended `buildMapPaint`/`buildLegend` (5th optional
  `palette` parameter, classed branch) — all consumed by
  `MapSymbologyEditor` (Task 7), `LayersPanel` (Task 8), `mapWidget.tsx`
  (Task 10), `MapView.tsx` (Task 9).

This is the largest task. It's still one task (not split further) because
every piece here is exercised by the same test file and reviewed as one
coherent unit — splitting it would leave intermediate commits with
half-finished, untestable types.

- [ ] **Step 1: Write the failing tests for classification math**

Append to `shell/src/builder/widgets/mapSymbology.test.ts` (existing 15
tests stay untouched above this point):

```ts
test("equalIntervalBreaks divides [min, max] into `classes` equal-width breaks", () => {
  expect(equalIntervalBreaks(0, 100, 4)).toEqual([0, 25, 50, 75, 100]);
  expect(equalIntervalBreaks(10, 10, 3)).toEqual([10, 10, 10, 10]);
});

test("quantileMeasures builds one min/max plus classes-1 percentile measures", () => {
  expect(quantileMeasures("pop", 4)).toEqual([
    { field: "pop", agg: "min", label: "min" },
    { field: "pop", agg: "percentile", label: "q1", p: 25 },
    { field: "pop", agg: "percentile", label: "q2", p: 50 },
    { field: "pop", agg: "percentile", label: "q3", p: 75 },
    { field: "pop", agg: "max", label: "max" },
  ]);
});

test("quantileBreaksFromRow reads min/q1..qk-1/max in order", () => {
  const row = { min: 0, q1: 10, q2: 20, q3: 30, max: 40 };
  expect(quantileBreaksFromRow(row, 4)).toEqual([0, 10, 20, 30, 40]);
});

test("jenksBreaks finds the boundaries of three well-separated clusters", () => {
  const sample = [1, 1, 2, 2, 50, 51, 52, 100, 101, 102];
  expect(jenksBreaks(sample, 3)).toEqual([1, 2, 52, 102]);
});

test("jenksBreaks is invariant to input order", () => {
  const sample = [102, 1, 51, 2, 100, 1, 52, 2, 50, 101];
  expect(jenksBreaks(sample, 3)).toEqual([1, 2, 52, 102]);
});
```

```ts
test("computeColorDomain: categorical mode runs a groupBy statistics query", async () => {
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "Nord", properties: {} },
    { id: "Sud", properties: {} },
  ]);
  const domain = await computeColorDomain(
    { field: "region", mode: "categorical" },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "categorical", values: ["Nord", "Sud"] });
  expect(runStatistics).toHaveBeenCalledWith({ groupBy: "region" });
});

test("computeColorDomain: numeric without classification runs min/max and returns a continuous domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric" },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric", min: 0, max: 100 });
});

test("computeColorDomain: equalInterval derives breaks from min/max client-side", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "equalInterval", classes: 4 } },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [0, 25, 50, 75, 100] });
});

test("computeColorDomain: quantile issues one measures call and reads it back", async () => {
  const runStatistics = vi.fn().mockResolvedValue([
    { id: "", properties: { min: 0, q1: 10, q2: 20, q3: 30, max: 40 } },
  ]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "quantile", classes: 4 } },
    { runStatistics, sampleField: vi.fn() },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [0, 10, 20, 30, 40] });
  expect(runStatistics).toHaveBeenCalledTimes(1);
});

test("computeColorDomain: jenks samples then classifies client-side", async () => {
  const sampleField = vi.fn().mockResolvedValue([1, 1, 2, 2, 50, 51, 52, 100, 101, 102]);
  const domain = await computeColorDomain(
    { field: "pop", mode: "numeric", classification: { method: "jenks", classes: 3 } },
    { runStatistics: vi.fn(), sampleField },
  );
  expect(domain).toEqual({ kind: "numeric-classed", breaks: [1, 2, 52, 102] });
  expect(sampleField).toHaveBeenCalledWith("pop", 2000);
});

test("computeSizeDomain runs min/max and returns it", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 50 } }]);
  const domain = await computeSizeDomain("montant", { runStatistics });
  expect(domain).toEqual({ min: 0, max: 50 });
});
```

```ts
test("buildMapPaint with a numeric-classed domain and a palette emits a step expression", () => {
  const { paint } = buildMapPaint(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: [0, 10, 20, 30] },
    null,
    "polygon",
    { kind: "sequential", low: "#000000", high: "#ffffff" },
  );
  expect(paint["fill-color"]).toEqual([
    "step",
    ["get", "pop"],
    "#000000",
    10,
    "#7f7f7f",
    20,
    "#ffffff",
  ]);
});

test("buildMapPaint categorical with an explicit palette uses its colors instead of the constants", () => {
  const { paint } = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "polygon",
    { kind: "categorical", colors: ["#111111", "#222222"] },
  );
  expect(paint["fill-color"]).toEqual(["match", ["get", "region"], "Nord", "#111111", "Sud", "#222222", "#111111"]);
});

test("buildLegend with a numeric-classed domain returns one range per class", () => {
  const legend = buildLegend(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: [0, 10, 20] },
    null,
    "polygon",
    { kind: "sequential", low: "#000000", high: "#ffffff" },
  );
  expect(legend).toEqual({
    color: {
      kind: "classed",
      field: "pop",
      classes: [
        { color: "#000000", from: 0, to: 10 },
        { color: "#ffffff", from: 10, to: 20 },
      ],
    },
  });
});
```

```ts
test("symbologyToPaintInputs maps a frozen LayerSymbology to buildMapPaint's inputs", () => {
  const symbology: LayerSymbology = {
    color: {
      field: "pop",
      mode: "numeric",
      classification: { method: "quantile", classes: 2 },
      palette: "sequential-blue",
      domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
      computedAt: "2026-08-23T00:00:00Z",
    },
  };
  const inputs = symbologyToPaintInputs(symbology, undefined);
  expect(inputs.encodings).toEqual({
    color: { field: "pop", mode: "numeric", classification: { method: "quantile", classes: 2 } },
  });
  expect(inputs.colorDomain).toEqual({ kind: "numeric-classed", breaks: [0, 50, 100] });
  expect(inputs.sizeDomain).toBeNull();
  expect(inputs.palette).toEqual({ kind: "sequential", low: "#dbeafe", high: "#1e3a8a" });
});

test("symbologyToPaintInputs on undefined symbology returns empty/null inputs", () => {
  const inputs = symbologyToPaintInputs(undefined, undefined);
  expect(inputs).toEqual({ encodings: {}, colorDomain: null, sizeDomain: null, palette: undefined });
});
```

Add the necessary imports at the top of the test file:

```ts
import {
  buildLegend,
  buildMapPaint,
  computeColorDomain,
  computeSizeDomain,
  detectGeometryKind,
  equalIntervalBreaks,
  jenksBreaks,
  quantileBreaksFromRow,
  quantileMeasures,
  symbologyToPaintInputs,
} from "./mapSymbology";
import type { LayerSymbology } from "./mapSymbology";
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: FAIL — none of the new exports exist yet; the 15 pre-existing
tests above still pass (confirm this explicitly in the output — that's the
backward-compatibility guarantee this task is built around).

- [ ] **Step 3: Implement classification helpers**

In `shell/src/builder/widgets/mapSymbology.ts`, add near the top (after the
existing type exports, before `paletteColor`):

```ts
export type PaletteId = import("./palette").PaletteId;
export type ResolvedPalette = import("./palette").ResolvedPalette;

export type ColorClassification =
  | { method: "quantile"; classes: number }
  | { method: "equalInterval"; classes: number }
  | { method: "jenks"; classes: number };
```

Update `MapEncodings` and `ColorDomain` (existing types) additively:

```ts
export type ColorDomain =
  | { kind: "categorical"; values: string[] }
  | { kind: "numeric"; min: number; max: number }
  | { kind: "numeric-classed"; breaks: number[] };

export type MapEncodings = {
  color?: { field: string; mode: "categorical" | "numeric"; classification?: ColorClassification };
  size?: { field: string };
};

export type LayerSymbology = {
  color?: NonNullable<MapEncodings["color"]> & {
    palette: PaletteId;
    domain: ColorDomain;
    computedAt: string;
  };
  size?: NonNullable<MapEncodings["size"]> & { domain: SizeDomain; computedAt: string };
};
```

Add the classification math functions (anywhere below the type
declarations, above `buildMapPaint`):

```ts
export function equalIntervalBreaks(min: number, max: number, classes: number): number[] {
  return Array.from({ length: classes + 1 }, (_, i) => min + (i * (max - min)) / classes);
}

export function quantileMeasures(
  field: string,
  classes: number,
): { field: string; agg: string; label: string; p?: number }[] {
  const measures: { field: string; agg: string; label: string; p?: number }[] = [
    { field, agg: "min", label: "min" },
  ];
  for (let i = 1; i < classes; i++) {
    measures.push({ field, agg: "percentile", label: `q${i}`, p: (100 * i) / classes });
  }
  measures.push({ field, agg: "max", label: "max" });
  return measures;
}

export function quantileBreaksFromRow(row: Record<string, unknown>, classes: number): number[] {
  const breaks = [Number(row.min)];
  for (let i = 1; i < classes; i++) breaks.push(Number(row[`q${i}`]));
  breaks.push(Number(row.max));
  return breaks;
}

// Fisher-Jenks natural breaks, classic dynamic-programming form. O(n^2 * k) —
// deliberately not the SMAWK-accelerated variant: bounded to a 2000-point
// sample and ≤ 9 classes (spec §4 decision 2), well within budget (~36M ops).
export function jenksBreaks(data: number[], classes: number): number[] {
  const sorted = [...data].sort((a, b) => a - b);
  const n = sorted.length;
  const mat1: number[][] = Array.from({ length: n + 1 }, () => new Array(classes + 1).fill(0));
  const mat2: number[][] = Array.from({ length: n + 1 }, () => new Array(classes + 1).fill(0));
  for (let i = 1; i <= classes; i++) {
    mat1[1][i] = 1;
    mat2[1][i] = 0;
    for (let j = 2; j <= n; j++) mat2[j][i] = Infinity;
  }
  let v = 0;
  for (let l = 2; l <= n; l++) {
    let s1 = 0;
    let s2 = 0;
    let w = 0;
    for (let m = 1; m <= l; m++) {
      const i3 = l - m + 1;
      const val = sorted[i3 - 1];
      s2 += val * val;
      s1 += val;
      w++;
      v = s2 - (s1 * s1) / w;
      const i4 = i3 - 1;
      if (i4 !== 0) {
        for (let j = 2; j <= classes; j++) {
          if (mat2[l][j] >= v + mat2[i4][j - 1]) {
            mat1[l][j] = i3;
            mat2[l][j] = v + mat2[i4][j - 1];
          }
        }
      }
    }
    mat1[l][1] = 1;
    mat2[l][1] = v;
  }
  const kClass = new Array(classes + 1).fill(0);
  kClass[classes] = sorted[n - 1];
  kClass[0] = sorted[0];
  let k = n;
  for (let j = classes; j >= 2; j--) {
    const id = mat1[k][j] - 2;
    kClass[j - 1] = sorted[id];
    k = mat1[k][j] - 1;
  }
  return kClass;
}
```

- [ ] **Step 4: Run to verify the classification-math tests pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "equalIntervalBreaks|quantileMeasures|quantileBreaksFromRow|jenksBreaks"`
Expected: PASS (5 tests). If `jenksBreaks` doesn't match the exact expected
arrays, print `mat1`/`mat2` for the small fixture and compare against the
well-known Fisher-Jenks reference behavior before changing the test
expectations — this is a textbook algorithm, a mismatch is far more likely
an off-by-one in the transcription above than in the test's expectation.

- [ ] **Step 5: Implement `computeColorDomain`/`computeSizeDomain`**

Add (needs `DataRecord` imported from `../../api/types`):

```ts
export type StatQueryFn = (query: Record<string, unknown>) => Promise<DataRecord[]>;
export type SampleFieldFn = (field: string, limit: number) => Promise<number[]>;

export async function computeColorDomain(
  params: { field: string; mode: "categorical" | "numeric"; classification?: ColorClassification },
  deps: { runStatistics: StatQueryFn; sampleField: SampleFieldFn },
): Promise<ColorDomain> {
  if (params.mode === "categorical") {
    const rows = await deps.runStatistics({ groupBy: params.field });
    return { kind: "categorical", values: rows.map((r) => String(r.id)) };
  }
  const classification = params.classification;
  if (!classification || classification.method === "equalInterval") {
    const rows = await deps.runStatistics({
      measures: [
        { field: params.field, agg: "min", label: "min" },
        { field: params.field, agg: "max", label: "max" },
      ],
    });
    const p = rows[0]?.properties ?? {};
    const min = Number(p.min ?? 0);
    const max = Number(p.max ?? 0);
    if (!classification) return { kind: "numeric", min, max };
    return { kind: "numeric-classed", breaks: equalIntervalBreaks(min, max, classification.classes) };
  }
  if (classification.method === "quantile") {
    const rows = await deps.runStatistics({ measures: quantileMeasures(params.field, classification.classes) });
    const p = rows[0]?.properties ?? {};
    return { kind: "numeric-classed", breaks: quantileBreaksFromRow(p, classification.classes) };
  }
  const sample = await deps.sampleField(params.field, 2000);
  return { kind: "numeric-classed", breaks: jenksBreaks(sample, classification.classes) };
}

export async function computeSizeDomain(
  field: string,
  deps: { runStatistics: StatQueryFn },
): Promise<SizeDomain> {
  const rows = await deps.runStatistics({
    measures: [
      { field, agg: "min", label: "min" },
      { field, agg: "max", label: "max" },
    ],
  });
  const p = rows[0]?.properties ?? {};
  return { min: Number(p.min ?? 0), max: Number(p.max ?? 0) };
}
```

Add the import at the top of `mapSymbology.ts`: `import type { DataRecord }
from "../../api/types";`

- [ ] **Step 6: Run to verify the orchestration tests pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t computeColorDomain`
Expected: PASS (5 tests), plus `computeSizeDomain` (1 test).

- [ ] **Step 7: Extend `buildMapPaint`/`buildLegend` with the optional palette parameter and the classed branch**

Replace the existing `buildMapPaint` function body's color section:

```ts
export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPaletteRuntime,
): MapPaintResult {
  const renderAs: "fill" | "circle" | "line" =
    geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
  const paint: Record<string, unknown> = {};

  if (encodings?.color && colorDomain) {
    const prop = colorPaintProperty(renderAs);
    if (colorDomain.kind === "categorical") {
      const colors = palette
        ? colorsForClasses(palette, colorDomain.values.length)
        : colorDomain.values.map((_, i) => paletteColor(i));
      const match: unknown[] = ["match", ["get", encodings.color.field]];
      colorDomain.values.forEach((value, i) => match.push(value, colors[i]));
      match.push(colors[0]);
      paint[prop] = match;
    } else if (colorDomain.kind === "numeric-classed") {
      const nClasses = colorDomain.breaks.length - 1;
      const colors = palette
        ? colorsForClasses(palette, nClasses)
        : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
      const step: unknown[] = ["step", ["get", encodings.color.field], colors[0]];
      for (let i = 1; i < nClasses; i++) step.push(colorDomain.breaks[i], colors[i]);
      paint[prop] = step;
    } else if (colorDomain.min === colorDomain.max) {
      paint[prop] = palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW;
    } else {
      const low = palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW;
      const high = palette?.kind === "sequential" ? palette.high : NUMERIC_COLOR_HIGH;
      paint[prop] = [
        "interpolate",
        ["linear"],
        ["get", encodings.color.field],
        colorDomain.min,
        low,
        colorDomain.max,
        high,
      ];
    }
  }

  if (encodings?.size && sizeDomain && renderAs === "circle") {
    paint["circle-radius"] =
      sizeDomain.min === sizeDomain.max
        ? SIZE_RADIUS_MIN
        : [
            "interpolate",
            ["linear"],
            ["get", encodings.size.field],
            sizeDomain.min,
            SIZE_RADIUS_MIN,
            sizeDomain.max,
            SIZE_RADIUS_MAX,
          ];
  }

  return { renderAs, paint };
}
```

(`ResolvedPaletteRuntime` here is just `import("./palette").ResolvedPalette`
— add `import type { ResolvedPalette as ResolvedPaletteRuntime,
colorsForClasses } from "./palette";` — actually `colorsForClasses` is a
value import, not a type: `import { colorsForClasses } from "./palette";
import type { ResolvedPalette } from "./palette";` and use `ResolvedPalette`
directly as the parameter type instead of introducing an alias — simplify
the sketch above accordingly when writing the real file.)

Update `buildLegend` similarly — add the classed branch and the `palette`
parameter:

```ts
export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
): LegendSpec | null {
  const legend: LegendSpec = {};

  if (encodings?.color && colorDomain) {
    if (colorDomain.kind === "categorical") {
      const colors = palette
        ? colorsForClasses(palette, colorDomain.values.length)
        : colorDomain.values.map((_, i) => paletteColor(i));
      legend.color = {
        kind: "categorical",
        field: encodings.color.field,
        entries: colorDomain.values.map((value, i) => ({ value, color: colors[i] })),
      };
    } else if (colorDomain.kind === "numeric-classed") {
      const nClasses = colorDomain.breaks.length - 1;
      const colors = palette
        ? colorsForClasses(palette, nClasses)
        : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
      legend.color = {
        kind: "classed",
        field: encodings.color.field,
        classes: Array.from({ length: nClasses }, (_, i) => ({
          color: colors[i],
          from: colorDomain.breaks[i],
          to: colorDomain.breaks[i + 1],
        })),
      };
    } else {
      legend.color = {
        kind: "numeric",
        field: encodings.color.field,
        min: colorDomain.min,
        max: colorDomain.max,
        colorLow: palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW,
        colorHigh: palette?.kind === "sequential" ? palette.high : NUMERIC_COLOR_HIGH,
      };
    }
  }

  if (encodings?.size && sizeDomain && geometryKind === "point") {
    legend.size = {
      field: encodings.size.field,
      min: sizeDomain.min,
      max: sizeDomain.max,
      radiusMin: SIZE_RADIUS_MIN,
      radiusMax: SIZE_RADIUS_MAX,
    };
  }

  return legend.color || legend.size ? legend : null;
}
```

Update `LegendSpec` (existing type) to add the classed variant:

```ts
export type LegendSpec = {
  color?:
    | { kind: "categorical"; field: string; entries: { value: string; color: string }[] }
    | { kind: "classed"; field: string; classes: { color: string; from: number; to: number }[] }
    | { kind: "numeric"; field: string; min: number; max: number; colorLow: string; colorHigh: string };
  size?: { field: string; min: number; max: number; radiusMin: number; radiusMax: number };
};
```

- [ ] **Step 8: Run to verify the paint/legend tests pass, and the original 15 still pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, all tests (15 original + ~15 new).

- [ ] **Step 9: Implement `symbologyToPaintInputs`**

```ts
export function symbologyToPaintInputs(
  symbology: LayerSymbology | undefined,
  themeColors: ThemeColors | undefined,
): {
  encodings: MapEncodings;
  colorDomain: ColorDomain | null;
  sizeDomain: SizeDomain | null;
  palette: ResolvedPalette | undefined;
} {
  if (!symbology) return { encodings: {}, colorDomain: null, sizeDomain: null, palette: undefined };
  const encodings: MapEncodings = {};
  let colorDomain: ColorDomain | null = null;
  let palette: ResolvedPalette | undefined;
  if (symbology.color) {
    encodings.color = {
      field: symbology.color.field,
      mode: symbology.color.mode,
      classification: symbology.color.classification,
    };
    colorDomain = symbology.color.domain;
    palette = resolvePalette(symbology.color.palette, themeColors) ?? undefined;
  }
  if (symbology.size) encodings.size = { field: symbology.size.field };
  const sizeDomain = symbology.size?.domain ?? null;
  return { encodings, colorDomain, sizeDomain, palette };
}
```

Add `import { resolvePalette } from "./palette"; import type { ThemeColors }
from "../../api/types";` at the top.

- [ ] **Step 10: Run the full test file**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, all tests including the `symbologyToPaintInputs` pair.

- [ ] **Step 11: Add `MapLayer.symbology` in `shell/src/api/types.ts`**

```ts
export type MapLayer =
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "vector";
      tilesUrl: string;
      sourceLayer: string;
      paint?: Record<string, unknown>;
      collectionId?: string;
      geometryKind?: "point" | "line" | "polygon";
      pkColumn?: string;
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "feature";
      url: string;
      paint?: Record<string, unknown>;
      renderAs?: "fill" | "circle" | "line";
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | ... // raster/deck/tiles3d unchanged
```

(Using the inline `import(...)` type syntax avoids a circular value import —
`types.ts` has no runtime dependency on `mapSymbology.ts`, only a type one.)

- [ ] **Step 12: Full shell suite + build**

Run: `cd shell && npx vitest run && npm run build && npm run lint && npm run format:check`
Expected: all green.

- [ ] **Step 13: Commit**

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts shell/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(shell): classification et symbologie déclarative dans mapSymbology.ts

Quantile/intervalle égal/Jenks, palettes optionnelles sur
buildMapPaint/buildLegend (rétrocompatible, 15 tests existants
inchangés), LayerSymbology et son adaptateur vers le compilateur.
EOF
)"
```

---

