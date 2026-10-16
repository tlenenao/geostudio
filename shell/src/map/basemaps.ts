// SPDX-License-Identifier: Apache-2.0
import type { StyleSpecification } from "maplibre-gl";

export type Basemap = { id: string; label: string; style: string };

export const BASEMAPS: Basemap[] = [
  { id: "clair", label: "Clair", style: "https://demotiles.maplibre.org/style.json" },
  {
    id: "positron",
    label: "Positron",
    style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  },
  {
    id: "voyager",
    label: "Voyager",
    style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
  },
];

export const DEFAULT_BASEMAP: Basemap = BASEMAPS[0];

const XYZ_PREFIX = "xyz:";

/** REV-367 i : un fond du tenant `xyz:<gabarit {z}/{x}/{y}>` devient un style raster minimal ;
 * toute autre valeur (URL de style.json) est transmise telle quelle à MapLibre. */
export function resolveBasemapStyle(style: string): string | StyleSpecification {
  if (!style.startsWith(XYZ_PREFIX)) return style;
  return {
    version: 8,
    sources: {
      basemap: { type: "raster", tiles: [style.slice(XYZ_PREFIX.length)], tileSize: 256 },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}
