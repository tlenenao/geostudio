// SPDX-License-Identifier: Apache-2.0
export type Basemap = { id: string; label: string; style: string };

export const BASEMAPS: Basemap[] = [
  { id: "clair", label: "Clair", style: "https://demotiles.maplibre.org/style.json" },
  { id: "positron", label: "Positron", style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" },
  { id: "voyager", label: "Voyager", style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json" },
];

export const DEFAULT_BASEMAP: Basemap = BASEMAPS[0];
