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
