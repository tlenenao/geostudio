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
