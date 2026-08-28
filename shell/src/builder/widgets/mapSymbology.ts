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

export type StrokeStyle = "solid" | "dashed" | "dotted";

// Forme PERSISTÉE : la palette est un identifiant, jamais des couleurs
// résolues — même règle que LayerSymbology.color (cf. déviation 5 du plan).
export type StrokeColorEncoding =
  | { fixed: string }
  | {
      field: string;
      // Même union que LayerSymbology.color : `mode` distingue la
      // classification catégorielle de la numérique, et l'éditeur en a besoin
      // pour savoir quel domaine recalculer.
      mode: "categorical" | "numeric";
      // Domaine FIGÉ au moment du calcul, comme LayerSymbology.color
      // (invariant SP-25) : le rendu ne recalcule jamais un domaine.
      domain: ColorDomain;
      palette: PaletteId;
      classification?: ColorClassification;
      computedAt: string;
    };

export type StrokeWidthEncoding = { fixed: number } | { field: string; domain: SizeDomain };

export type LayerStroke = {
  color: StrokeColorEncoding;
  width: StrokeWidthEncoding;
  style: StrokeStyle;
};

// Forme d'ENTRÉE de buildMapPaint/buildLegend : palette déjà résolue par
// symbologyToPaintInputs, exactement comme le paramètre `palette` existant.
export type StrokePaintInput = {
  color:
    | { fixed: string }
    | { field: string; domain: ColorDomain; palette: ResolvedPalette | undefined };
  width: StrokeWidthEncoding;
  style: StrokeStyle;
};

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
  stroke?: LayerStroke;
  opacity?: number; // 0-100
};

export type MapPaintResult = {
  renderAs: "fill" | "circle" | "line";
  // JAMAIS une propriété layout : `icon-image`/`text-field` sont layout-only
  // dans le style-spec, et Style.addLayer fait `if (this._validate(...))
  // return;` — une clé layout posée ici ferait disparaître la couche
  // ENTIÈRE, silencieusement, sans exception pour le try/catch d'applyLayers.
  paint: Record<string, unknown>;
  // Contour de polygone : seconde couche `line` (fill-outline-color n'a
  // aucune largeur stylable). Absent quand il n'y a pas de contour.
  outlinePaint?: Record<string, unknown>;
  // Ids d'images MapLibre référencées par iconLayout ; l'appelant doit les
  // charger via map.addImage (Task 8). Toujours présent, vide sans icône.
  iconImages: string[];
  // Layout de la couche `symbol` appariée (Task 7/7). Absent sans icône.
  iconLayout?: Record<string, unknown>;
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
  stroke?: { kind: "categorical"; field: string; entries: { value: string; color: string }[] };
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

// Même table que `renderAs` dans buildMapPaint : un seul endroit où
// "géométrie → type de couche MapLibre" est écrit.
export function renderAsFor(geometryKind: GeometryKind): "fill" | "circle" | "line" {
  return geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
}

function colorPaintProperty(renderAs: "fill" | "circle" | "line"): string {
  if (renderAs === "circle") return "circle-color";
  if (renderAs === "line") return "line-color";
  return "fill-color";
}

// Largeurs de contour : 1 px à 8 px sur le domaine, distinctes des rayons de
// cercle (SIZE_RADIUS_MIN/MAX = 4/24) — un contour de 24 px mangerait le
// polygone. Constantes locales, pas de réutilisation trompeuse.
const STROKE_WIDTH_MIN = 1;
const STROKE_WIDTH_MAX = 8;

// Cœur commun aux deux sites qui construisent une expression MapLibre de
// couleur data-driven — le bloc `color` de buildMapPaint et strokeColorValue
// ci-dessous (constat Important de la revue Task 2, tranché par Tanguy en
// faveur de la factorisation). `domain` DOIT déjà être passé par
// `normalizeDomain` par l'appelant : cette fonction ne fait plus ce garde,
// elle suppose un domaine utilisable (comme le faisaient déjà les deux sites
// une fois leur propre normalisation faite).
function colorExpression(
  field: string,
  domain: ColorDomain,
  palette: ResolvedPalette | undefined,
): unknown {
  if (domain.kind === "categorical") {
    const colors = palette
      ? colorsForClasses(palette, domain.values.length)
      : domain.values.map((_, i) => paletteColor(i));
    const match: unknown[] = ["match", ["get", field]];
    domain.values.forEach((v, i) => match.push(v, colors[i % colors.length]));
    match.push(colors[0]);
    return match;
  }
  if (domain.kind === "numeric-classed") {
    const nClasses = domain.breaks.length - 1;
    const colors = palette
      ? colorsForClasses(palette, nClasses)
      : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
    const step: unknown[] = ["step", ["get", field], colors[0]];
    for (let i = 1; i < nClasses; i++) step.push(domain.breaks[i], colors[i]);
    return step;
  }
  // numeric continu : même interpolation que fill-color/circle-color.
  const low = palette?.kind === "sequential" ? palette.low : NUMERIC_COLOR_LOW;
  const high = palette?.kind === "sequential" ? palette.high : NUMERIC_COLOR_HIGH;
  if (domain.min === domain.max) return low;
  return ["interpolate", ["linear"], ["get", field], domain.min, low, domain.max, high];
}

function strokeColorValue(color: StrokePaintInput["color"]): unknown {
  if ("fixed" in color) return color.fixed;
  const normalized = normalizeDomain(color.domain);
  if (!normalized) return undefined;
  return colorExpression(color.field, normalized, color.palette);
}

function strokeWidthValue(width: StrokeWidthEncoding): unknown {
  if ("fixed" in width) return width.fixed;
  if (width.domain.min === width.domain.max) return STROKE_WIDTH_MIN;
  return [
    "interpolate",
    ["linear"],
    ["get", width.field],
    width.domain.min,
    STROKE_WIDTH_MIN,
    width.domain.max,
    STROKE_WIDTH_MAX,
  ];
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
// identiques — il reste moins de 3 valeurs distinctes (moins de 2 classes)
// ou une valeur qui ne croît pas strictement (un doublon non adjacent, ou
// une régression). Le seuil de 3 (pas 2) est délibéré — C-new de la
// re-revue finale SP-25 : un domaine dédupliqué à exactement 2 breaks (1
// seule classe) passait le garde d'origine, et `buildMapPaint` le
// transformait en expression MapLibre `step` avec seulement 2 arguments
// (`["step", get, color0]`), que MapLibre rejette ("Expected at least 4
// arguments") — couche entière invisible sans signal, sur un cas de données
// réaliste (colonne à égalités, ex. `quantileBreaksFromRow` sur une
// distribution où le premier quartile vaut déjà le minimum). Un domaine
// numérique continu (min/max) n'a pas cette classe de bug (un `interpolate`
// à deux stops égaux est déjà géré par un rendu constant plus bas) et n'est
// donc pas concerné par ce garde.
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
  if (deduped.length < 3) return null;
  for (let i = 1; i < deduped.length; i++) {
    if (deduped[i] <= deduped[i - 1]) return null;
  }
  return { kind: "numeric-classed", breaks: deduped };
}

export type PaintExtras = {
  stroke?: StrokePaintInput;
  opacity?: number; // 0-100
};

export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  extras?: PaintExtras,
): MapPaintResult {
  const renderAs = renderAsFor(geometryKind);
  const paint: Record<string, unknown> = {};
  const result: MapPaintResult = { renderAs, paint, iconImages: [] };
  const normalizedColorDomain = normalizeDomain(colorDomain);

  if (encodings?.color && normalizedColorDomain) {
    const prop = colorPaintProperty(renderAs);
    paint[prop] = colorExpression(encodings.color.field, normalizedColorDomain, palette);
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

  const stroke = extras?.stroke;
  if (stroke) {
    const colorValue = strokeColorValue(stroke.color);
    const widthValue = strokeWidthValue(stroke.width);
    const dasharray =
      stroke.style === "dashed" ? [2, 2] : stroke.style === "dotted" ? [1, 2] : undefined;

    if (geometryKind === "point" && colorValue !== undefined) {
      paint["circle-stroke-color"] = colorValue;
      paint["circle-stroke-width"] = widthValue;
      // `line-dasharray` n'a pas d'équivalent sur un cercle : le style est
      // volontairement ignoré pour les points (aucune propriété MapLibre).
    } else if (geometryKind === "polygon" && colorValue !== undefined) {
      // Les DEUX sont posés à dessein, et c'est un arbitrage assumé (constat
      // N7 du 2026-08-28, gravité Mineur) : `fill-outline-color` dessine un
      // filet de 1 px soumis à `fill-opacity` (v8.paint_fill exige
      // `fill-antialias: true`, qui est le défaut), donc à `opacity: 30` on
      // superpose un filet à α=0,3 et la couche `line` à α=0,3 — une couture
      // d'1 px sensiblement plus sombre à l'intérieur du contour. Purement
      // cosmétique. On le garde parce que c'est le seul contour qui survive
      // si `addOutlineLayer` échoue (le rollback de Task 3 retire la couche
      // `line`, pas la peinture du remplissage) et parce que les assertions
      // data-driven de cette tâche et de Task 5 portent dessus. Consigné dans
      // les suivis non bloquants.
      paint["fill-outline-color"] = colorValue;
      result.outlinePaint = {
        "line-color": colorValue,
        "line-width": widthValue,
        ...(dasharray ? { "line-dasharray": dasharray } : {}),
      };
    }
    // geometryKind === "line" : no-op délibéré (déviation 2). Une ligne a
    // déjà line-color/line-width via les encodages color/size ; un second
    // contour sur une ligne n'a aucun sens cartographique.
  }

  if (extras?.opacity !== undefined) {
    const alpha = extras.opacity / 100;
    paint[
      renderAs === "circle"
        ? "circle-opacity"
        : renderAs === "line"
          ? "line-opacity"
          : "fill-opacity"
    ] = alpha;
    // Le contour est une couche à part : sans ça, un polygone à 30 %
    // gardait un contour parfaitement opaque (constat 3.11 du pré-vol).
    if (result.outlinePaint) result.outlinePaint["line-opacity"] = alpha;
  }

  return result;
}

export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  extras?: PaintExtras,
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

  const stroke = extras?.stroke;
  if (stroke && "field" in stroke.color) {
    const normalized = normalizeDomain(stroke.color.domain);
    if (normalized?.kind === "categorical") {
      const colors = stroke.color.palette
        ? colorsForClasses(stroke.color.palette, normalized.values.length)
        : normalized.values.map((_, i) => paletteColor(i));
      legend.stroke = {
        kind: "categorical",
        field: stroke.color.field,
        entries: normalized.values.map((v, i) => ({ value: v, color: colors[i % colors.length] })),
      };
    }
  }

  return legend.color || legend.size || legend.stroke ? legend : null;
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
  stroke: StrokePaintInput | undefined;
} {
  if (!symbology)
    return {
      encodings: {},
      colorDomain: null,
      sizeDomain: null,
      palette: undefined,
      stroke: undefined,
    };
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
  const stroke: StrokePaintInput | undefined = symbology.stroke
    ? {
        ...symbology.stroke,
        color:
          "fixed" in symbology.stroke.color
            ? symbology.stroke.color
            : {
                field: symbology.stroke.color.field,
                domain: symbology.stroke.color.domain,
                palette: resolvePalette(symbology.stroke.color.palette, themeColors) ?? undefined,
              },
      }
    : undefined;
  return { encodings, colorDomain, sizeDomain, palette, stroke };
}
