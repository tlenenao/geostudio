// SPDX-License-Identifier: Apache-2.0
// ARC-17 : 4 modes de symbologie avancés (Dot Density, Predominant, bivarié,
// Compare A to B) + effets. Module pur, sans dépendance : les expressions sont
// des JSON MapLibre figés dans le document (domaines calculés à l'édition,
// jamais au rendu — invariant SP-25).

export type BivariateDomain = { min: number; max: number };

export type AdvancedSymbology =
  | { kind: "dotDensity"; field: string; valuePerDot: number; color: string }
  | { kind: "predominant"; fields: string[] }
  | {
      kind: "bivariate";
      fieldX: string;
      fieldY: string;
      domainX: BivariateDomain;
      domainY: BivariateDomain;
      computedAt: string;
    }
  | { kind: "compare"; fieldA: string; fieldB: string; maxAbs: number; computedAt: string };

// Bloom = halo flou, shadow = ombre portée décalée, blend = fusion (les formes
// voisines se fondent). MapLibre n'a pas de mode de fusion par couche : chaque
// effet est une couche « dessous » dérivée de la couche principale.
export type LayerEffects = { bloom?: boolean; shadow?: boolean; blend?: boolean };

export type AdvancedLegend =
  | { kind: "predominant"; entries: { value: string; color: string }[] }
  | { kind: "bivariate"; fieldX: string; fieldY: string; colors: string[] }
  | {
      kind: "compare";
      fieldA: string;
      fieldB: string;
      maxAbs: number;
      colorLow: string;
      colorMid: string;
      colorHigh: string;
    }
  | { kind: "dotDensity"; field: string; valuePerDot: number; color: string };

// gs-raw-color-ok-begin: rampes cartographiques (bivariée 3x3, divergente) — valeurs de donnée, pas un style d'UI
// Rampe bivariée 3x3 (Stevens), indexée y*3+x : x croît vers la droite, y vers le haut.
export const BIVARIATE_COLORS = [
  "#e8e8e8",
  "#ace4e4",
  "#5ac8c8",
  "#dfb0d6",
  "#a5add3",
  "#5698b9",
  "#be64ac",
  "#8c62aa",
  "#3b4994",
];
export const COMPARE_COLORS = { low: "#b2182b", mid: "#f7f7f7", high: "#2166ac" };
export const DOT_DEFAULT_COLOR = "#dc2626";
const NEUTRAL_FILL = "#9ca3af";
const SHADOW_COLOR = "rgba(0,0,0,0.5)";
// gs-raw-color-ok-end

const num = (field: string) => ["to-number", ["get", field], 0];

function binExpr(field: string, d: BivariateDomain): unknown {
  const w = (d.max - d.min) / 3;
  return ["step", num(field), 0, d.min + w, 1, d.min + 2 * w, 2];
}

export function advancedColorExpression(adv: AdvancedSymbology, colors: string[]): unknown {
  switch (adv.kind) {
    case "predominant": {
      const fields = adv.fields;
      if (fields.length < 2) return colors[0];
      const branches = fields.flatMap((f, i) => [
        ["all", ...fields.filter((o) => o !== f).map((o) => [">=", num(f), num(o)])],
        colors[i % colors.length],
      ]);
      return ["case", ...branches, colors[0]];
    }
    case "bivariate": {
      const { domainX: dx, domainY: dy } = adv;
      if (dx.min >= dx.max || dy.min >= dy.max) return BIVARIATE_COLORS[0];
      const idx = ["+", ["*", 3, binExpr(adv.fieldY, dy)], binExpr(adv.fieldX, dx)];
      return ["match", idx, ...BIVARIATE_COLORS.flatMap((c, i) => [i, c]), BIVARIATE_COLORS[0]];
    }
    case "compare": {
      const m = adv.maxAbs;
      if (!(m > 0)) return COMPARE_COLORS.mid;
      const diff = ["-", num(adv.fieldA), num(adv.fieldB)];
      return [
        "interpolate",
        ["linear"],
        diff,
        -m,
        COMPARE_COLORS.low,
        0,
        COMPARE_COLORS.mid,
        m,
        COMPARE_COLORS.high,
      ];
    }
    default:
      return undefined; // dotDensity : pas de couleur de remplissage
  }
}

export function advancedLegend(adv: AdvancedSymbology, colors: string[]): AdvancedLegend | null {
  switch (adv.kind) {
    case "predominant":
      return adv.fields.length < 2
        ? null
        : {
            kind: "predominant",
            entries: adv.fields.map((f, i) => ({ value: f, color: colors[i % colors.length] })),
          };
    case "bivariate":
      return {
        kind: "bivariate",
        fieldX: adv.fieldX,
        fieldY: adv.fieldY,
        colors: BIVARIATE_COLORS,
      };
    case "compare":
      return {
        kind: "compare",
        fieldA: adv.fieldA,
        fieldB: adv.fieldB,
        maxAbs: adv.maxAbs,
        colorLow: COMPARE_COLORS.low,
        colorMid: COMPARE_COLORS.mid,
        colorHigh: COMPARE_COLORS.high,
      };
    case "dotDensity":
      return adv.field && adv.valuePerDot > 0
        ? { kind: "dotDensity", field: adv.field, valuePerDot: adv.valuePerDot, color: adv.color }
        : null;
  }
}

// Fond neutre d'un polygone en Dot Density : les points portent l'information.
export const DOT_BASE_FILL = { color: NEUTRAL_FILL, opacity: 0.15 };

export type EffectLayer = {
  suffix: "__fx_shadow" | "__fx_bloom" | "__fx_blend";
  type: "circle" | "line" | "fill";
  paint: Record<string, unknown>;
};

// Couches « dessous » d'une couche principale de type `renderAs` (déjà peinte
// par `paint`). Un polygone ne peut pas être flouté : bloom/fusion passent par
// un contour `line` flou.
export function buildEffectLayers(
  effects: LayerEffects | undefined,
  renderAs: "fill" | "circle" | "line",
  paint: Record<string, unknown>,
): EffectLayer[] {
  if (!effects) return [];
  const out: EffectLayer[] = [];
  const colorKey =
    renderAs === "circle" ? "circle-color" : renderAs === "line" ? "line-color" : "fill-color";
  const color = paint[colorKey] ?? NEUTRAL_FILL;
  if (effects.shadow) {
    out.push({
      suffix: "__fx_shadow",
      type: renderAs,
      paint:
        renderAs === "circle"
          ? {
              "circle-color": SHADOW_COLOR,
              "circle-radius": paint["circle-radius"] ?? 5,
              "circle-translate": [3, 3],
              "circle-blur": 0.6,
            }
          : renderAs === "line"
            ? {
                "line-color": SHADOW_COLOR,
                "line-width": paint["line-width"] ?? 2,
                "line-translate": [3, 3],
                "line-blur": 2,
              }
            : { "fill-color": SHADOW_COLOR, "fill-translate": [3, 3] },
    });
  }
  const glow = (
    suffix: "__fx_bloom" | "__fx_blend",
    scale: number,
    blur: number,
    opacity: number,
  ) =>
    out.push({
      suffix,
      type: renderAs === "circle" ? "circle" : "line",
      paint:
        renderAs === "circle"
          ? {
              "circle-color": color,
              "circle-radius": ["*", scale, paint["circle-radius"] ?? 5],
              "circle-blur": blur,
              "circle-opacity": opacity,
            }
          : {
              "line-color": color,
              "line-width": 8 * scale,
              "line-blur": 6 * blur,
              "line-opacity": opacity,
            },
    });
  if (effects.bloom) glow("__fx_bloom", 2, 1, 0.4);
  if (effects.blend) glow("__fx_blend", 1.5, 0.8, 0.6);
  return out;
}

// ---------------------------------------------------------------- Dot Density

export const MAX_DOTS = 5000;

type Ring = number[][];
type Piece = {
  id: string | number | undefined;
  properties: Record<string, unknown>;
  geometry: unknown;
};
export type DotCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    properties: Record<string, never>;
    geometry: { type: "Point"; coordinates: number[] };
  }[];
};
export const EMPTY_DOTS: DotCollection = { type: "FeatureCollection", features: [] };

function polygonsOf(geometry: unknown): Ring[][] {
  const g = geometry as { type?: string; coordinates?: unknown } | null;
  if (g?.type === "Polygon") return [g.coordinates as Ring[]];
  if (g?.type === "MultiPolygon") return g.coordinates as Ring[][];
  return [];
}

function ringArea(r: Ring): number {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++)
    a += r[j][0] * r[i][1] - r[i][0] * r[j][1];
  return Math.abs(a / 2);
}

function inRing(x: number, y: number, r: Ring): boolean {
  let inside = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i];
    const [xj, yj] = r[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// Anneau extérieur moins trous.
const inPolygon = (x: number, y: number, rings: Ring[]) =>
  inRing(x, y, rings[0]) && !rings.slice(1).some((h) => inRing(x, y, h));

const polygonsArea = (polys: Ring[][]) =>
  polys.reduce((s, p) => s + ringArea(p[0]) - p.slice(1).reduce((h, r) => h + ringArea(r), 0), 0);

function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

// `querySourceFeatures` renvoie un morceau par tuile : on regroupe par entité et
// chaque morceau reçoit sa part (aire) du nombre de points de l'entité. Sortie
// déterministe (PRNG graine = entité + morceau), donc idempotente. Plafond
// MAX_DOTS (ponytail : au-delà, les entités suivantes ne sont pas dotées —
// échantillonnage par tuile si un jeu réel le dépasse).
export function generateDots(
  pieces: Piece[],
  cfg: { field: string; valuePerDot: number },
  maxDots = MAX_DOTS,
): DotCollection {
  const out: DotCollection["features"] = [];
  if (!(cfg.valuePerDot > 0)) return { type: "FeatureCollection", features: out };
  const groups = new Map<string, { value: number; polys: Ring[][][] }>();
  for (const p of pieces) {
    const polys = polygonsOf(p.geometry);
    if (polys.length === 0) continue;
    const key = String(p.id ?? JSON.stringify(p.properties));
    const g = groups.get(key) ?? { value: Number(p.properties[cfg.field]), polys: [] };
    g.polys.push(polys);
    groups.set(key, g);
  }
  for (const [key, g] of groups) {
    const n = Math.round(g.value / cfg.valuePerDot);
    if (!(n > 0)) continue;
    const areas = g.polys.map(polygonsArea);
    const total = areas.reduce((a, b) => a + b, 0);
    if (!(total > 0)) continue;
    g.polys.forEach((polys, pi) => {
      const count = Math.round((n * areas[pi]) / total);
      const rand = mulberry32(hash(`${key}#${pi}`));
      const xs = polys.flatMap((p) => p[0].map((c) => c[0]));
      const ys = polys.flatMap((p) => p[0].map((c) => c[1]));
      const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
      const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
      let placed = 0;
      for (let tries = 0; placed < count && tries < count * 30 && out.length < maxDots; tries++) {
        const x = x0 + rand() * (x1 - x0);
        const y = y0 + rand() * (y1 - y0);
        if (polys.some((p) => inPolygon(x, y, p))) {
          out.push({
            type: "Feature",
            properties: {},
            geometry: { type: "Point", coordinates: [x, y] },
          });
          placed++;
        }
      }
    });
    if (out.length >= maxDots) break;
  }
  return { type: "FeatureCollection", features: out };
}
