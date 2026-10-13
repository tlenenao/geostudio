// SPDX-License-Identifier: Apache-2.0
// ARC-28 : export / import d'un style MapLibre (spec v8) pour la carte.
// L'export réutilise `effectivePaint` (le même code que le rendu) et joint la
// symbologie déclarative en `metadata["geostudio:symbology"]` : un style
// exporté puis réimporté redonne donc EXACTEMENT le même `paint` (ré-évalué par
// `effectivePaint`). Un style étranger (sans métadonnée) est repris tel quel via
// `MapLayer.paint` — pas de rétro-ingénierie des expressions en symbologie.
import type { MapLayer } from "../api/types";
import type { LayerSymbology } from "../builder/widgets/mapSymbology";
import { effectivePaint } from "./mapLayerBuild";
import type { ThemeColors } from "../api/types";

type StyleSource = Record<string, unknown>;
type StyleLayer = {
  id: string;
  type: string;
  source: string;
  "source-layer"?: string;
  layout?: Record<string, unknown>;
  paint?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};
export type MapLibreStyle = {
  version: 8;
  name: string;
  metadata: Record<string, unknown>;
  sources: Record<string, StyleSource>;
  layers: StyleLayer[];
};

const SYMBOLOGY_KEY = "geostudio:symbology";
const KIND_TYPE = { point: "circle", line: "line", polygon: "fill" } as const;
const RENDER_KIND = { circle: "point", line: "line", fill: "polygon" } as const;

export function exportMapLibreStyle(
  layers: MapLayer[],
  name: string,
  themeColors?: ThemeColors,
): MapLibreStyle {
  const style: MapLibreStyle = {
    version: 8,
    name,
    metadata: { "geostudio:exported": true },
    sources: {},
    layers: [],
  };
  for (const l of layers) {
    const layout = l.visible ? undefined : { visibility: "none" };
    const meta = { "geostudio:title": l.title };
    if (l.kind === "raster") {
      style.sources[l.id] = { type: "raster", tiles: [l.tilesUrl], tileSize: 256 };
      style.layers.push({
        id: l.id,
        type: "raster",
        source: l.id,
        ...(layout ? { layout } : {}),
        paint: l.opacity === undefined ? {} : { "raster-opacity": l.opacity },
        metadata: meta,
      });
      continue;
    }
    if (l.kind !== "vector" && l.kind !== "feature") continue; // deck/tiles3d : pas d'équivalent
    const geometryKind =
      l.kind === "vector" ? (l.geometryKind ?? "polygon") : RENDER_KIND[l.renderAs ?? "fill"];
    const { paint, outlinePaint } = effectivePaint(l, geometryKind, themeColors);
    style.sources[l.id] =
      l.kind === "vector"
        ? { type: "vector", tiles: [l.tilesUrl] }
        : { type: "geojson", data: l.url };
    const base = {
      source: l.id,
      ...(l.kind === "vector" ? { "source-layer": l.sourceLayer } : {}),
      ...(layout ? { layout } : {}),
    };
    style.layers.push({
      id: l.id,
      type: KIND_TYPE[geometryKind],
      ...base,
      paint,
      metadata: { ...meta, ...(l.symbology ? { [SYMBOLOGY_KEY]: l.symbology } : {}) },
    });
    if (outlinePaint)
      style.layers.push({
        id: `${l.id}__outline`,
        type: "line",
        ...base,
        paint: outlinePaint,
        metadata: { "geostudio:outlineOf": l.id },
      });
  }
  return style;
}

// Un style importé est non fiable : seules les URLs http(s) ou relatives sont reprises
// (pas de javascript:/data:/file:) ; la CSP connect-src borne ensuite les origines.
const safeUrl = (v: unknown): v is string =>
  typeof v === "string" && /^(https?:\/\/|\/(?!\/))/i.test(v);

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

// Prend un document JSON non fiable : ne lève jamais, renvoie les couches
// reprises et les ids ignorés (types non pris en charge ou sources illisibles).
export function importMapLibreStyle(doc: unknown): { layers: MapLayer[]; skipped: string[] } {
  const out: MapLayer[] = [];
  const skipped: string[] = [];
  if (!isRecord(doc) || doc.version !== 8 || !Array.isArray(doc.layers))
    return { layers: out, skipped };
  const sources = isRecord(doc.sources) ? doc.sources : {};
  const seen = new Set<string>();
  for (const raw of doc.layers) {
    if (!isRecord(raw) || typeof raw.id !== "string") continue;
    const id = raw.id;
    const meta = isRecord(raw.metadata) ? raw.metadata : {};
    if (meta["geostudio:outlineOf"]) continue; // couche dérivée, recréée par le rendu
    const src = typeof raw.source === "string" ? sources[raw.source] : undefined;
    const visible = !(isRecord(raw.layout) && raw.layout.visibility === "none");
    const title = typeof meta["geostudio:title"] === "string" ? meta["geostudio:title"] : id;
    const paint = isRecord(raw.paint) ? raw.paint : {};
    const tile0 = isRecord(src) && Array.isArray(src.tiles) ? src.tiles[0] : undefined;
    const tile = safeUrl(tile0) ? tile0 : undefined;
    const type = raw.type;
    if (seen.has(id) || !isRecord(src)) {
      skipped.push(id);
      continue;
    }
    seen.add(id);
    const geometryKind =
      type === "circle" ? "point" : type === "line" ? "line" : type === "fill" ? "polygon" : null;
    if (type === "raster" && src.type === "raster" && tile !== undefined) {
      const op = paint["raster-opacity"];
      out.push({
        id,
        title,
        visible,
        kind: "raster",
        tilesUrl: tile,
        ...(typeof op === "number" ? { opacity: op } : {}),
      });
    } else if (geometryKind && src.type === "vector" && tile !== undefined) {
      const sourceLayer = raw["source-layer"];
      if (typeof sourceLayer !== "string") {
        skipped.push(id);
        continue;
      }
      out.push({
        id,
        title,
        visible,
        kind: "vector",
        tilesUrl: tile,
        sourceLayer,
        geometryKind,
        paint,
        ...(isRecord(meta[SYMBOLOGY_KEY])
          ? { symbology: meta[SYMBOLOGY_KEY] as LayerSymbology }
          : {}),
      });
    } else if (geometryKind && src.type === "geojson" && safeUrl(src.data)) {
      out.push({
        id,
        title,
        visible,
        kind: "feature",
        url: src.data,
        renderAs: type as "fill" | "circle" | "line",
        paint,
        ...(isRecord(meta[SYMBOLOGY_KEY])
          ? { symbology: meta[SYMBOLOGY_KEY] as LayerSymbology }
          : {}),
      });
    } else {
      skipped.push(id);
    }
  }
  return { layers: out, skipped };
}
