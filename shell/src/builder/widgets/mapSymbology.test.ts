// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
// Dépendance transitive de maplibre-gl (présente dans node_modules, cf.
// package-lock.json), pas un ajout à shell/package.json — utilisée ici
// uniquement pour prouver contre la vraie bibliothèque, comme le brief du
// round 2 de C-new le demande explicitement, qu'une expression de peinture
// produite est réellement valide pour MapLibre (et pas seulement conforme à
// la forme qu'on s'attend à lui voir).
import { createExpression } from "@maplibre/maplibre-gl-style-spec";
import {
  buildLegend,
  buildMapPaint,
  computeColorDomain,
  computeSizeDomain,
  detectGeometryKind,
  equalIntervalBreaks,
  iconImageId,
  jenksBreaks,
  normalizeDomain,
  quantileBreaksFromRow,
  quantileMeasures,
  renderAsFor,
  symbologyToPaintInputs,
} from "./mapSymbology";
import type { ColorDomain, LayerSymbology } from "./mapSymbology";

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
    "match",
    ["get", "region"],
    "Nord",
    "#2563eb",
    "Sud",
    "#dc2626",
    "#2563eb",
  ]);
});

test("buildMapPaint returns a match expression on line-color for a categorical domain on line geometry", () => {
  const { renderAs, paint } = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "line",
  );
  expect(renderAs).toBe("line");
  expect(paint["line-color"]).toEqual([
    "match",
    ["get", "region"],
    "Nord",
    "#2563eb",
    "Sud",
    "#dc2626",
    "#2563eb",
  ]);
});

test("cycles the categorical palette past 8 distinct values", () => {
  const values = Array.from({ length: 9 }, (_, i) => `v${i}`);
  const { paint } = buildMapPaint(
    { color: { field: "cat", mode: "categorical" } },
    { kind: "categorical", values },
    null,
    "polygon",
  );
  const match = paint["fill-color"] as unknown[];
  // ["match", ["get","cat"], v0,c0, v1,c1, ..., v8,c8, default] — v8 is the
  // 9th distinct value (index 8) and must reuse c0 (palette wraps at 8).
  expect(match[2]).toBe("v0");
  expect(match[3]).toBe("#2563eb");
  expect(match[18]).toBe("v8");
  expect(match[19]).toBe("#2563eb");
});

test("buildMapPaint returns an interpolate expression for a numeric color domain", () => {
  const { paint } = buildMapPaint(
    { color: { field: "valeur", mode: "numeric" } },
    { kind: "numeric", min: 0, max: 100 },
    null,
    "point",
  );
  expect(paint["circle-color"]).toEqual([
    "interpolate",
    ["linear"],
    ["get", "valeur"],
    0,
    "#dbeafe",
    100,
    "#1e3a8a",
  ]);
});

test("a numeric color domain with min === max renders a constant color, not an interpolate expression", () => {
  const { paint } = buildMapPaint(
    { color: { field: "valeur", mode: "numeric" } },
    { kind: "numeric", min: 5, max: 5 },
    null,
    "polygon",
  );
  expect(paint["fill-color"]).toBe("#dbeafe");
});

test("renderAs follows the geometry kind, independent of encodings", () => {
  expect(buildMapPaint(undefined, null, null, "point").renderAs).toBe("circle");
  expect(buildMapPaint(undefined, null, null, "line").renderAs).toBe("line");
  expect(buildMapPaint(undefined, null, null, "polygon").renderAs).toBe("fill");
});

test("size encoding produces a circle-radius interpolate expression only for point geometry", () => {
  const point = buildMapPaint({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "point");
  expect(point.paint["circle-radius"]).toEqual([
    "interpolate",
    ["linear"],
    ["get", "montant"],
    0,
    4,
    50,
    24,
  ]);

  const polygon = buildMapPaint(
    { size: { field: "montant" } },
    null,
    { min: 0, max: 50 },
    "polygon",
  );
  expect(polygon.paint["circle-radius"]).toBeUndefined();
});

test("a size domain with min === max renders a constant radius", () => {
  const { paint } = buildMapPaint(
    { size: { field: "montant" } },
    null,
    { min: 10, max: 10 },
    "point",
  );
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
  const legend = buildLegend(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "polygon",
  );
  expect(legend).toEqual({
    color: {
      kind: "categorical",
      field: "region",
      entries: [
        { value: "Nord", color: "#2563eb" },
        { value: "Sud", color: "#dc2626" },
      ],
    },
  });
});

test("buildLegend builds a numeric color section", () => {
  const legend = buildLegend(
    { color: { field: "valeur", mode: "numeric" } },
    { kind: "numeric", min: 0, max: 100 },
    null,
    "point",
  );
  expect(legend).toEqual({
    color: {
      kind: "numeric",
      field: "valeur",
      min: 0,
      max: 100,
      colorLow: "#dbeafe",
      colorHigh: "#1e3a8a",
    },
  });
});

test("buildLegend builds a size section only for point geometry", () => {
  const onPoint = buildLegend({ size: { field: "montant" } }, null, { min: 0, max: 50 }, "point");
  expect(onPoint).toEqual({
    size: { field: "montant", min: 0, max: 50, radiusMin: 4, radiusMax: 24 },
  });

  const onPolygon = buildLegend(
    { size: { field: "montant" } },
    null,
    { min: 0, max: 50 },
    "polygon",
  );
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
  const runStatistics = vi
    .fn()
    .mockResolvedValue([{ id: "", properties: { min: 0, q1: 10, q2: 20, q3: 30, max: 40 } }]);
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
    "#808080",
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
  expect(paint["fill-color"]).toEqual([
    "match",
    ["get", "region"],
    "Nord",
    "#111111",
    "Sud",
    "#222222",
    "#111111",
  ]);
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
  expect(inputs).toEqual({
    encodings: {},
    colorDomain: null,
    sizeDomain: null,
    palette: undefined,
  });
});

// C1 de la revue finale SP-25 : normalizeDomain (+ son intégration dans
// buildMapPaint/buildLegend) — un domaine jamais recalculé ou dégénéré ne
// doit plus jamais atteindre une expression MapLibre `match`/`step` cassée.

test("normalizeDomain rejects an empty categorical domain (never-recomputed encoding)", () => {
  expect(normalizeDomain({ kind: "categorical", values: [] })).toBeNull();
});

test("normalizeDomain keeps a non-empty categorical domain unchanged", () => {
  const domain: ColorDomain = { kind: "categorical", values: ["Nord"] };
  expect(normalizeDomain(domain)).toEqual(domain);
});

test("normalizeDomain passes a continuous numeric domain through unchanged", () => {
  const domain: ColorDomain = { kind: "numeric", min: 0, max: 10 };
  expect(normalizeDomain(domain)).toEqual(domain);
});

test("normalizeDomain rejects a single-break numeric-classed domain", () => {
  expect(normalizeDomain({ kind: "numeric-classed", breaks: [10] })).toBeNull();
});

test("normalizeDomain rejects fully collapsed breaks (equalIntervalBreaks(10, 10, 3))", () => {
  expect(
    normalizeDomain({ kind: "numeric-classed", breaks: equalIntervalBreaks(10, 10, 3) }),
  ).toBeNull();
});

test("normalizeDomain rejects a non-finite break", () => {
  expect(normalizeDomain({ kind: "numeric-classed", breaks: [0, NaN, 20] })).toBeNull();
  expect(
    normalizeDomain({
      kind: "numeric-classed",
      breaks: [0, undefined as unknown as number, 20],
    }),
  ).toBeNull();
});

test("normalizeDomain rejects breaks that regress after a duplicate (not strictly ascending)", () => {
  expect(normalizeDomain({ kind: "numeric-classed", breaks: [0, 10, 5, 20] })).toBeNull();
});

test("normalizeDomain collapses an adjacent duplicate break into fewer, still-usable classes", () => {
  expect(normalizeDomain({ kind: "numeric-classed", breaks: [0, 10, 10, 20] })).toEqual({
    kind: "numeric-classed",
    breaks: [0, 10, 20],
  });
});

test("normalizeDomain of null is null", () => {
  expect(normalizeDomain(null)).toBeNull();
});

test("buildMapPaint silently renders unstyled (no color paint key) instead of throwing on an empty categorical domain", () => {
  const { paint } = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: [] },
    null,
    "polygon",
  );
  expect(paint["fill-color"]).toBeUndefined();
});

test("buildMapPaint silently renders unstyled instead of throwing on collapsed breaks", () => {
  const { paint } = buildMapPaint(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: equalIntervalBreaks(10, 10, 3) },
    null,
    "polygon",
  );
  expect(paint["fill-color"]).toBeUndefined();
});

test("buildLegend returns no color section (not a broken one) for an empty categorical domain", () => {
  const legend = buildLegend(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: [] },
    null,
    "polygon",
  );
  expect(legend).toBeNull();
});

test("buildLegend returns no color section for collapsed breaks", () => {
  const legend = buildLegend(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: equalIntervalBreaks(10, 10, 3) },
    null,
    "polygon",
  );
  expect(legend).toBeNull();
});

// I1 de la revue finale SP-25 : quantileBreaksFromRow/jenksBreaks ne
// doivent jamais émettre de NaN/undefined, y compris sur une collection
// vide ou un échantillon plus court que le nombre de classes demandé.

test("quantileBreaksFromRow never emits NaN on a missing/empty row", () => {
  expect(quantileBreaksFromRow({}, 4)).toEqual([0, 0, 0, 0, 0]);
});

test("quantileBreaksFromRow defends each field independently (partial row)", () => {
  expect(quantileBreaksFromRow({ min: 0, max: 40 }, 4)).toEqual([0, 0, 0, 0, 40]);
});

test("jenksBreaks on an empty sample returns [] rather than a run of undefined", () => {
  expect(jenksBreaks([], 3)).toEqual([]);
});

test("jenksBreaks with more classes than data points returns [] rather than out-of-bounds reads", () => {
  expect(jenksBreaks([1, 2], 5)).toEqual([]);
});

// C-new de la re-revue finale SP-25 (round 2, boundary hole du fix C1 de
// round 1) : normalizeDomain acceptait un domaine numérique dédupliqué à
// exactement 2 breaks (1 seule classe) — le garde d'origine ne rejetait que
// "< 2 breaks distincts". buildMapPaint transformait alors ce domaine en
// expression MapLibre "step" à 2 arguments (["step", get, color0]), que
// MapLibre rejette réellement ("Expected at least 4 arguments, but found
// only 2.") : la couche entière disparaissait sans aucun signal, exactement
// le symptôme d'origine de C1. Cas réaliste, pas un edge case : toute
// colonne numérique où une bonne part des lignes partage le minimum
// (comptage, note, beaucoup de zéros) produit ce genre de breaks dédupliqués
// à 2 valeurs via quantile ou jenks.

test("quantileBreaksFromRow on tied data dedups to exactly 2 breaks (the re-review's repro)", () => {
  const breaks = quantileBreaksFromRow({ min: 0, q1: 0, q2: 0, q3: 0, max: 10 }, 4);
  expect(breaks).toEqual([0, 0, 0, 0, 10]);
});

test("jenksBreaks on the same tied-data shape also dedups to exactly 2 breaks", () => {
  expect(jenksBreaks([0, 0, 0, 0, 10], 3)).toEqual([0, 0, 0, 10]);
});

test("normalizeDomain now rejects a numeric-classed domain that dedups to exactly 2 breaks (1 class)", () => {
  const breaks = quantileBreaksFromRow({ min: 0, q1: 0, q2: 0, q3: 0, max: 10 }, 4);
  expect(normalizeDomain({ kind: "numeric-classed", breaks })).toBeNull();
  expect(
    normalizeDomain({ kind: "numeric-classed", breaks: jenksBreaks([0, 0, 0, 0, 10], 3) }),
  ).toBeNull();
});

test("normalizeDomain still accepts a domain that dedups to exactly 3 breaks (2 classes)", () => {
  expect(normalizeDomain({ kind: "numeric-classed", breaks: [0, 10, 20] })).toEqual({
    kind: "numeric-classed",
    breaks: [0, 10, 20],
  });
});

test("buildMapPaint never emits a MapLibre-invalid step for tied-data breaks that dedup to 1 class", () => {
  const breaks = quantileBreaksFromRow({ min: 0, q1: 0, q2: 0, q3: 0, max: 10 }, 4);
  const { paint } = buildMapPaint(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks },
    null,
    "polygon",
  );
  // Domaine traité comme non utilisable (pas de "fill-color"), pas comme un
  // domaine à 1 classe rendu par une expression "step" mal formée.
  expect(paint["fill-color"]).toBeUndefined();

  // Preuve contre la vraie bibliothèque, pas seulement une assertion de
  // forme : la forme que le code d'AVANT ce fix aurait produite pour ce
  // domaine est effectivement rejetée par MapLibre (vérifié aussi via un
  // one-liner node : `createExpression(["step", ["get","pop"], "#2563eb"])
  // .result === "error"`, message "Expected at least 4 arguments, but
  // found only 2.").
  const preFixShape = ["step", ["get", "pop"], "#2563eb"];
  const validated = createExpression(preFixShape);
  expect(validated.result).toBe("error");
});

test("buildLegend shows no color section for a domain that dedups to exactly 2 breaks", () => {
  const breaks = quantileBreaksFromRow({ min: 0, q1: 0, q2: 0, q3: 0, max: 10 }, 4);
  const legend = buildLegend(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks },
    null,
    "polygon",
  );
  expect(legend).toBeNull();
});

test("buildMapPaint's step expression for a usable (>= 2 classes) domain validates against the real MapLibre style spec", () => {
  const { paint } = buildMapPaint(
    { color: { field: "pop", mode: "numeric" } },
    { kind: "numeric-classed", breaks: [0, 10, 20] },
    null,
    "polygon",
  );
  const validated = createExpression(paint["fill-color"]);
  expect(validated.result).toBe("success");
});

test("buildMapPaint emits circle-stroke-* for a point layer with a fixed stroke color/width", () => {
  const { paint } = buildMapPaint({}, null, null, "point", undefined, {
    stroke: { color: { fixed: "#111111" }, width: { fixed: 2 }, style: "solid" },
  });
  expect(paint["circle-stroke-color"]).toBe("#111111");
  expect(paint["circle-stroke-width"]).toBe(2);
});

test("buildMapPaint emits fill-outline-color plus an outline line-paint for a polygon with stroke", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: { color: { fixed: "#222222" }, width: { fixed: 3 }, style: "dashed" },
  });
  expect(result.paint["fill-outline-color"]).toBe("#222222");
  expect(result.outlinePaint).toEqual({
    "line-color": "#222222",
    "line-width": 3,
    "line-dasharray": [2, 2],
  });
});

test("stroke on a line geometry is a no-op and never overwrites the color encoding", () => {
  const result = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "line",
    undefined,
    { stroke: { color: { fixed: "#333333" }, width: { fixed: 7 }, style: "dotted" } },
  );
  // The `color` encoding owns line-color; the stroke must not touch it…
  expect(result.paint["line-color"]).toEqual([
    "match",
    ["get", "region"],
    "Nord",
    "#2563eb",
    "Sud",
    "#dc2626",
    "#2563eb",
  ]);
  // …nor introduce a width, a dash, or a second layer.
  expect(result.paint["line-width"]).toBeUndefined();
  expect(result.paint["line-dasharray"]).toBeUndefined();
  expect(result.outlinePaint).toBeUndefined();
});

test("buildMapPaint applies data-driven stroke color from a categorical domain", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "region",
        domain: { kind: "categorical", values: ["Nord", "Sud"] },
        palette: { kind: "categorical", colors: ["#aaaaaa", "#bbbbbb"] },
      },
      width: { fixed: 1 },
      style: "solid",
    },
  });
  expect(result.paint["fill-outline-color"]).toEqual([
    "match",
    ["get", "region"],
    "Nord",
    "#aaaaaa",
    "Sud",
    "#bbbbbb",
    "#aaaaaa",
  ]);
});

test("buildMapPaint applies data-driven stroke width from a numeric domain", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: { fixed: "#000000" },
      width: { field: "pop", domain: { min: 0, max: 100 } },
      style: "solid",
    },
  });
  expect(result.outlinePaint?.["line-width"]).toEqual([
    "interpolate",
    ["linear"],
    ["get", "pop"],
    0,
    1,
    100,
    8,
  ]);
});

test("buildMapPaint applies fixed opacity per geometry, outline included", () => {
  expect(
    buildMapPaint({}, null, null, "polygon", undefined, { opacity: 50 }).paint["fill-opacity"],
  ).toBe(0.5);
  expect(
    buildMapPaint({}, null, null, "point", undefined, { opacity: 25 }).paint["circle-opacity"],
  ).toBe(0.25);
  expect(
    buildMapPaint({}, null, null, "line", undefined, { opacity: 100 }).paint["line-opacity"],
  ).toBe(1);
  // I3.11 du pré-vol : un polygone à 30 % gardait un contour opaque.
  const withOutline = buildMapPaint({}, null, null, "polygon", undefined, {
    opacity: 30,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
  });
  expect(withOutline.outlinePaint?.["line-opacity"]).toBe(0.3);
});

test("buildMapPaint emits an opacity of 0 rather than omitting it", () => {
  // Cas limite : `extras?.opacity !== undefined` (pas `if (extras?.opacity)`)
  // doit laisser passer une opacité de 0 — une couche invisible mais
  // présente, distincte d'une couche sans opacity configurée du tout.
  const result = buildMapPaint({}, null, null, "polygon", undefined, { opacity: 0 });
  expect(result.paint["fill-opacity"]).toBe(0);
  expect("fill-opacity" in result.paint).toBe(true);
});

test("buildMapPaint never writes a layout-only property into paint", () => {
  const LAYOUT_ONLY = ["icon-image", "icon-size", "icon-allow-overlap", "text-field", "text-size"];
  const result = buildMapPaint({}, null, null, "point", undefined, {
    opacity: 40,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
  for (const key of LAYOUT_ONLY) expect(result.paint[key]).toBeUndefined();
});

test("buildLegend includes a stroke entry for a data-driven stroke color", () => {
  const legend = buildLegend({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "region",
        domain: { kind: "categorical", values: ["Nord"] },
        palette: { kind: "categorical", colors: ["#aaaaaa"] },
      },
      width: { fixed: 1 },
      style: "solid",
    },
  });
  expect(legend?.stroke).toEqual({
    kind: "categorical",
    field: "region",
    entries: [{ value: "Nord", color: "#aaaaaa" }],
  });
});

test("symbologyToPaintInputs resolves stroke.color.palette from an id, like color", () => {
  const inputs = symbologyToPaintInputs(
    {
      stroke: {
        color: {
          field: "region",
          mode: "categorical",
          domain: { kind: "categorical", values: ["A"] },
          palette: "theme-primary",
          computedAt: "2026-08-27T00:00:00Z",
        },
        width: { fixed: 1 },
        style: "solid",
      },
    },
    { primary: "#123456" },
  );
  expect(inputs.stroke).toBeDefined();
  expect(inputs.stroke && "field" in inputs.stroke.color && inputs.stroke.color.palette).toEqual(
    expect.objectContaining({ kind: expect.any(String) }),
  );
});

test("renderAsFor maps a geometry kind to the MapLibre layer type", () => {
  expect(renderAsFor("point")).toBe("circle");
  expect(renderAsFor("line")).toBe("line");
  expect(renderAsFor("polygon")).toBe("fill");
});

// Le comportement (domaine figé, computedAt propagé jusqu'au rendu) est
// vérifié par le test qui suit (« buildMapPaint compile un contour classé en
// expression step »). Un test séparé qui ne faisait que relire au runtime le
// littéral `LayerSymbology` qu'il venait d'écrire a été supprimé ici (constat
// de revue Task 5, SP-27) : son assertion ne pouvait jamais échouer — sa
// seule valeur réelle était une vérification de TYPE (compile sous tsc),
// déjà couverte par `npm run build` / `tsc --noEmit`, mais sa forme de test
// Vitest faisait croire à une vérification de comportement.

test("buildMapPaint compile un contour classé en expression step", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "pop",
        domain: { kind: "numeric-classed", breaks: [0, 10, 20, 30] },
        palette: { kind: "sequential", low: "#dbeafe", high: "#1e3a8a" },
      },
      width: { fixed: 2 },
      style: "solid",
    },
  });
  const step = result.paint["fill-outline-color"] as unknown[];
  expect(step[0]).toBe("step");
  expect(step[1]).toEqual(["get", "pop"]);
  // 3 classes ⇒ couleur initiale + 2 paires (seuil, couleur).
  expect(step).toHaveLength(2 + 1 + 4);
  expect(result.outlinePaint?.["line-color"]).toEqual(step);
});

// Miroir du garde côté couleur : c'est exactement l'état que produit le
// bouton « Couleur de contour par attribut » avant tout recalcul (champ vide,
// `values: []`). Sans ce garde, `match` n'aurait pas assez d'arguments et
// MapLibre ferait disparaître la couche ENTIÈRE, silencieusement.
test("un contour classé jamais recalculé ne peint aucun contour au lieu d'une expression cassée", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "",
        domain: { kind: "categorical", values: [] },
        palette: undefined,
      },
      width: { fixed: 2 },
      style: "solid",
    },
  });
  expect(result.paint["fill-outline-color"]).toBeUndefined();
  expect(result.outlinePaint).toBeUndefined();
});

test("buildMapPaint on a point layer with a categorical icon emits iconLayout, never paint", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["ecole", "commerce"] },
      mapping: {
        ecole: { source: "lucide", name: "school" },
        commerce: { source: "lucide", name: "shopping-cart" },
      },
      fallback: { source: "lucide", name: "map-pin" },
    },
  });
  expect(result.iconLayout).toEqual({
    "icon-image": [
      "match",
      ["get", "categorie"],
      "ecole",
      "lucide:school",
      "commerce",
      "lucide:shopping-cart",
      "lucide:map-pin",
    ],
    "icon-size": 1,
    "icon-allow-overlap": true,
  });
  expect(result.paint["icon-image"]).toBeUndefined();
  expect(result.iconImages).toEqual(["lucide:school", "lucide:shopping-cart", "lucide:map-pin"]);
});

test("without an explicit fallback the match default is the first mapped icon", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["a"] },
      mapping: { a: { source: "lucide", name: "star" } },
    },
  });
  expect(result.iconLayout?.["icon-image"]).toEqual([
    "match",
    ["get", "categorie"],
    "a",
    "lucide:star",
    "lucide:star",
  ]);
  expect(result.iconImages).toEqual(["lucide:star"]);
});

test("an icon encoding with no mapped value produces no icon layer at all", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: { field: "categorie", domain: { kind: "categorical", values: ["a"] }, mapping: {} },
  });
  expect(result.iconLayout).toBeUndefined();
  expect(result.iconImages).toEqual([]);
});

test("buildMapPaint icon on a non-point geometry is a no-op", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["a"] },
      mapping: { a: { source: "lucide", name: "star" } },
    },
  });
  expect(result.iconLayout).toBeUndefined();
  expect(result.iconImages).toEqual([]);
});

test("iconImageId distinguishes lucide from custom refs", () => {
  expect(iconImageId({ source: "lucide", name: "school" })).toBe("lucide:school");
  expect(iconImageId({ source: "custom", id: "abc123" })).toBe("custom:abc123");
});

test("buildLegend includes an icon entry per mapped value", () => {
  const legend = buildLegend({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["ecole", "jamais-mappe"] },
      mapping: { ecole: { source: "lucide", name: "school" } },
    },
  });
  expect(legend?.icon).toEqual({
    field: "categorie",
    entries: [{ value: "ecole", imageId: "lucide:school" }],
  });
});
