// SPDX-License-Identifier: Apache-2.0
import type { StyleSpecification } from "maplibre-gl";

/** `external` : fond servi par un tiers (masqué quand l'instance coupe les fonds externes,
 * AUD-122). */
export type Basemap = { id: string; label: string; style: string; external?: boolean };

// Géoplateforme IGN (WMTS en KVP, grille PM = WebMercatorQuad) — gabarit vérifié (HTTP 200).
const IGN_WMTS =
  "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=normal" +
  "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}";

/** Fond local sans aucune requête réseau. `style` est un identifiant (aussi servi par le
 * shell sous public/basemaps pour les clients tiers) : le rendu passe par
 * resolveBasemapStyle, qui le remplace par le style en ligne ci-dessous. */
export const BLANK_BASEMAP: Basemap = {
  id: "vierge",
  label: "Vierge",
  style: "/basemaps/blank.json",
};

export const BASEMAPS: Basemap[] = [
  {
    id: "clair",
    label: "Clair",
    style: "https://demotiles.maplibre.org/style.json",
    external: true,
  },
  {
    id: "positron",
    label: "Positron",
    style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    external: true,
  },
  {
    id: "voyager",
    label: "Voyager",
    style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    external: true,
  },
  {
    id: "ign-plan",
    label: "Plan IGN",
    style: `xyz:${IGN_WMTS}&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&FORMAT=image/png`,
    external: true,
  },
  {
    id: "ign-ortho",
    label: "Ortho IGN",
    style: `xyz:${IGN_WMTS}&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&FORMAT=image/jpeg`,
    external: true,
  },
  BLANK_BASEMAP,
];

export const DEFAULT_BASEMAP: Basemap = BASEMAPS[0];

export function defaultBasemapStyle(externalEnabled: boolean): string {
  return externalEnabled ? DEFAULT_BASEMAP.style : BLANK_BASEMAP.style;
}

export function allowedBasemaps(all: Basemap[], externalEnabled: boolean): Basemap[] {
  return externalEnabled ? all : all.filter((b) => !b.external);
}

const XYZ_PREFIX = "xyz:";
const XYZ_GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";

// Revue L6 I2 : style vierge en ligne — une URL "/basemaps/blank.json" sort du sous-chemin
// d'un export statique (base "./") et devient file:///basemaps/… dans le desktop.
const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#f2efe9" /* gs-raw-color-ok: fond cartographique neutre */ },
    },
  ],
};

/** REV-367 i : un fond `xyz:<gabarit {z}/{x}/{y}>` devient un style raster minimal ;
 * toute autre valeur (URL de style.json) est transmise telle quelle à MapLibre. */
export function resolveBasemapStyle(style: string): string | StyleSpecification {
  if (style === BLANK_BASEMAP.style) return BLANK_STYLE;
  if (!style.startsWith(XYZ_PREFIX)) return style;
  const tiles = style.slice(XYZ_PREFIX.length);
  // Licence ouverte Etalab 2.0 : l'attribution IGN est requise.
  const attribution = tiles.startsWith("https://data.geopf.fr/") ? "© IGN" : undefined;
  return {
    version: 8,
    // AUD-049 : sans `glyphs`, étiquettes, comptes de cluster et mesures n'apparaissent
    // pas. Un fond xyz est déjà un fond externe : polices libres de la démo MapLibre.
    // (Le fond vierge, sans réseau, reste sans glyphs : voir REV-371.)
    glyphs: XYZ_GLYPHS,
    sources: {
      basemap: {
        type: "raster",
        tiles: [tiles],
        tileSize: 256,
        ...(attribution ? { attribution } : {}),
      },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}
