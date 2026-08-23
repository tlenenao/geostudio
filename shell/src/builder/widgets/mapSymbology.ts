// SPDX-License-Identifier: Apache-2.0
import { colorsForClasses, resolvePalette } from "./palette";
import type { PaletteId, ResolvedPalette } from "./palette";
import type { DataRecord, ThemeColors } from "../../api/types";

export type GeometryKind = "point" | "line" | "polygon";

export type { PaletteId, ResolvedPalette };

export type ColorClassification =
  | { method: "quantile"; classes: number }
  | { method: "equalInterval"; classes: number }
  | { method: "jenks"; classes: number };

export type ColorDomain =
  | { kind: "categorical"; values: string[] }
  | { kind: "numeric"; min: number; max: number }
  | { kind: "numeric-classed"; breaks: number[] };

export type SizeDomain = { min: number; max: number };

export type MapEncodings = {
  color?: { field: string; mode: "categorical" | "numeric"; classification?: ColorClassification };
  size?: { field: string };
};

// L'enveloppe de stockage/édition d'une symbologie de couche : la version
// figée (domaine + palette résolus au moment du calcul, `computedAt` pour un
// futur affichage "recalculer ?") que `symbologyToPaintInputs` adapte vers
// les entrées existantes de `buildMapPaint`/`buildLegend`.
export type LayerSymbology = {
  color?: NonNullable<MapEncodings["color"]> & {
    palette: PaletteId;
    domain: ColorDomain;
    computedAt: string;
  };
  size?: NonNullable<MapEncodings["size"]> & { domain: SizeDomain; computedAt: string };
};

export type MapPaintResult = {
  renderAs: "fill" | "circle" | "line";
  paint: Record<string, unknown>;
};

export type LegendSpec = {
  color?:
    | { kind: "categorical"; field: string; entries: { value: string; color: string }[] }
    | { kind: "classed"; field: string; classes: { color: string; from: number; to: number }[] }
    | {
        kind: "numeric";
        field: string;
        min: number;
        max: number;
        colorLow: string;
        colorHigh: string;
      };
  size?: { field: string; min: number; max: number; radiusMin: number; radiusMax: number };
};

const CATEGORICAL_PALETTE = [
  "#2563eb",
  "#dc2626",
  "#16a34a",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#65a30d",
];
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

// Défendu comme le chemin min/max voisin (computeSizeDomain, la branche
// equalInterval de computeColorDomain) : `?? 0` sur chaque lecture plutôt que
// `Number(undefined)` → NaN. Sur une collection vide, l'agrégat ne renvoie
// aucune ligne (`rows[0]?.properties ?? {}` → `{}`), donc AVANT ce fix
// chaque break devenait NaN — silencieusement sérialisé en `null` par
// `JSON.stringify`, persistant une config cassée (I1 de la revue finale
// SP-25). Un `[0, 0, …]` dégénéré reste défendu en aval par
// `normalizeDomain` (C1) plutôt que de fuiter un NaN dans une expression
// MapLibre.
export function quantileBreaksFromRow(row: Record<string, unknown>, classes: number): number[] {
  const breaks = [Number(row.min ?? 0)];
  for (let i = 1; i < classes; i++) breaks.push(Number(row[`q${i}`] ?? 0));
  breaks.push(Number(row.max ?? 0));
  return breaks;
}

// Fisher-Jenks natural breaks, classic dynamic-programming form. O(n^2 * k) —
// deliberately not the SMAWK-accelerated variant: bounded to a 2000-point
// sample and ≤ 9 classes (spec §4 decision 2), well within budget (~36M ops).
export function jenksBreaks(data: number[], classes: number): number[] {
  // Un échantillon vide, ou plus court que le nombre de classes demandé,
  // ferait lire l'algorithme hors-limites plus bas et renvoyer un tableau
  // rempli d'`undefined` (I1 de la revue finale SP-25) — jamais matérialisé
  // comme domaine utilisable : `[]` est rejeté par `normalizeDomain` (C1)
  // exactement comme un domaine catégoriel vide.
  if (data.length === 0 || data.length < classes) return [];
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
    return {
      kind: "numeric-classed",
      breaks: equalIntervalBreaks(min, max, classification.classes),
    };
  }
  if (classification.method === "quantile") {
    const rows = await deps.runStatistics({
      measures: quantileMeasures(params.field, classification.classes),
    });
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

// C1 de la revue finale SP-25 : un domaine jamais recalculé (`values: []` par
// défaut à la création de l'encodage, cf. setColorField dans
// MapSymbologyEditor.tsx) ou dégénéré (`equalIntervalBreaks(10, 10, 3)` →
// `[10,10,10,10]`, un `quantile` sur des données à égalités répétées) produit
// une expression `match`/`step` MapLibre invalide — trop peu d'arguments, ou
// des stops non strictement croissants. `map.addLayer` lève alors à
// l'analyse, et le `try/catch` d'`applyLayers` (MapView.tsx) retire la
// source ET la couche avec un simple `console.error` : la couche disparaît
// sans aucun signal utilisateur. Ce garde pur retourne `null` — "pas
// utilisable, comme si aucun domaine n'était configuré" — plutôt que de
// laisser `buildMapPaint`/`buildLegend` émettre une expression cassée.
//
// Un domaine catégoriel est rejeté s'il n'a aucune valeur observée. Un
// domaine à classes (breaks) est rejeté s'il a moins de 2 breaks, si l'un
// d'eux n'est pas fini (NaN/undefined — cf. I1, `quantileBreaksFromRow`/
// `jenksBreaks`), ou si — après avoir fusionné les breaks adjacents
// identiques — il reste moins de 2 valeurs distinctes ou une valeur qui ne
// croît pas strictement (un doublon non adjacent, ou une régression). Un
// domaine numérique continu (min/max) n'a pas cette classe de bug (un
// `interpolate` à deux stops égaux est déjà géré par un rendu constant plus
// bas) et n'est donc pas concerné par ce garde.
export function normalizeDomain(domain: ColorDomain | null): ColorDomain | null {
  if (!domain) return null;
  if (domain.kind === "categorical") {
    return domain.values.length === 0 ? null : domain;
  }
  if (domain.kind === "numeric") {
    return domain;
  }
  if (domain.breaks.length < 2) return null;
  const deduped: number[] = [];
  for (const b of domain.breaks) {
    if (!Number.isFinite(b)) return null;
    if (deduped.length === 0 || deduped[deduped.length - 1] !== b) deduped.push(b);
  }
  if (deduped.length < 2) return null;
  for (let i = 1; i < deduped.length; i++) {
    if (deduped[i] <= deduped[i - 1]) return null;
  }
  return { kind: "numeric-classed", breaks: deduped };
}

export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
): MapPaintResult {
  const renderAs: "fill" | "circle" | "line" =
    geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
  const paint: Record<string, unknown> = {};
  const normalizedColorDomain = normalizeDomain(colorDomain);

  if (encodings?.color && normalizedColorDomain) {
    const colorDomain = normalizedColorDomain;
    const prop = colorPaintProperty(renderAs);
    if (colorDomain.kind === "categorical") {
      const colors = palette
        ? colorsForClasses(palette, colorDomain.values.length)
        : colorDomain.values.map((_, i) => paletteColor(i));
      const match: unknown[] = ["match", ["get", encodings.color.field]];
      colorDomain.values.forEach((value, i) => match.push(value, colors[i]));
      match.push(colors[0]); // default color for a value outside the observed domain
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

export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
): LegendSpec | null {
  const legend: LegendSpec = {};
  const normalizedColorDomain = normalizeDomain(colorDomain);

  if (encodings?.color && normalizedColorDomain) {
    const colorDomain = normalizedColorDomain;
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

  // Size legend only makes sense where size is actually rendered (points).
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

// Adaptateur pur : `LayerSymbology` est l'enveloppe de stockage/édition
// (domaine + palette déjà calculés, `computedAt`) ; `buildMapPaint`/
// `buildLegend` attendent des entrées séparées (encodings/domain/palette).
// Ce pont évite de dupliquer la logique de rendu pour la forme figée.
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
