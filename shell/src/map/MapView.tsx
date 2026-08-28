// SPDX-License-Identifier: Apache-2.0
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import maplibregl, { type FilterSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { Tiles3DLoader } from "@loaders.gl/3d-tiles";
import type { DataRecord, MapConfig, MapLayer, ThemeColors } from "../api/types";
import { MapLegend } from "./MapLegend";
import { MapPopup } from "./MapPopup";
import { resolvePopupContent } from "./popupContent";
import {
  buildMapPaint,
  iconImageId,
  renderAsFor,
  symbologyToPaintInputs,
  type GeometryKind,
  type MapPaintResult,
} from "../builder/widgets/mapSymbology";
import { decodeIconImage, rasterizeLucideIcon } from "../builder/widgets/iconLibrary";

const HIGHLIGHT_ID = "__highlight__";
const TERRAIN_SOURCE_ID = "__terrain__";
// Path segments distinguishing our own authenticated proxies (served by
// core, design docs §4) from an externally-hosted resource at the same-
// looking path — the latter must never receive our session's bearer token.
const HOSTED_TILESET3D_PATH = "/tileset3d/";
const HOSTED_TERRAIN3D_PATH = "/terrain3d/";
const HOSTED_COLLECTION_PATH = "/collections/";

// Real "is this hosted by us" check: a substring match on the URL is not
// enough — layer/terrain URLs are freeform (an author can type any external
// URL via LayerPicker/TerrainPanel), so an attacker-controlled URL like
// "https://attacker.example/x/terrain3d/y/tiles/0/0/0.png" would otherwise
// pass a bare `.includes(pathPrefix)` check and leak the session's bearer
// token cross-origin. A URL only counts as hosted when its origin matches
// the configured core API's origin AND its pathname starts with the proxy
// route's own path segment. Shared by both the tileset3d (deck.gl
// Tile3DLayer, see buildTiles3DLayer) and terrain3d (MapLibre
// transformRequest, see below) call sites — never duplicate this check.
// Le chemin de base du cœur fait partie de la comparaison depuis C1 de la
// revue finale SP-24 : en production `VITE_CORE_URL` vaut `https://hôte/api`
// (docker-compose.prod.yml), donc une vraie URL de tuile est
// `/api/collections/…` et ne commence PAS par `/collections/`. Le jeton
// n'était alors jamais attaché et toute collection non publique renvoyait un
// 404 — invisible en test, où toutes les URL de cœur étaient sans chemin.
function isHostedCoreUrl(url: string, coreUrl: string | undefined, pathPrefix: string): boolean {
  if (!coreUrl) return false;
  try {
    const target = new URL(url);
    const core = new URL(coreUrl);
    // "https://hôte" → pathname "/" → base "" ; "https://hôte/api/" → "/api".
    const base = core.pathname.replace(/\/+$/, "");
    return target.origin === core.origin && target.pathname.startsWith(base + pathPrefix);
  } catch {
    return false;
  }
}

function isHostedTilesetUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TILESET3D_PATH);
}

function isHostedTerrainUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TERRAIN3D_PATH);
}

// Les tuiles MVT d'une collection (SP-24) et le GeoJSON /items sont servis par
// le cœur sous can() : ils doivent porter le jeton de session, sinon une
// collection non publique n'est pas lisible du tout. Même vérification
// d'origine réelle que pour tileset3d/terrain3d — jamais un includes().
function isHostedCollectionUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_COLLECTION_PATH);
}

export type MapViewHandle = {
  flyTo: (opts: {
    center: [number, number];
    zoom?: number;
    pitch?: number;
    bearing?: number;
  }) => void;
  highlight: (geometry: unknown | null) => void;
};

// Une couche tuilée était jusqu'ici ajoutée en "fill" quel que soit son
// contenu : une collection de points ne s'affichait donc pas du tout. Le type
// MapLibre suit désormais la géométrie déclarée par la couche.
function layerTypeFor(geometryKind: "point" | "line" | "polygon") {
  if (geometryKind === "point") return "circle" as const;
  if (geometryKind === "line") return "line" as const;
  return "fill" as const;
}

// Géométrie inconnue ou mixte (I1 de la revue finale SP-24) : le cœur renvoie
// geometryType "GEOMETRY" pour toute colonne PostGIS non typée — issue
// courante de l'ingestion d'un fichier mêlant Point et MultiPoint, ou
// LineString et MultiLineString — et itemClient.ts ne sait alors pas la
// mapper, d'où un `geometryKind` absent. Un unique layer "fill" ne rend RIEN
// pour des points ou des lignes : la couche était silencieusement blanche,
// sans erreur ni avertissement. On pose donc les trois, chacun filtré par le
// type de géométrie de l'entité. Multi* est cité explicitement plutôt que de
// parier sur la normalisation de ["geometry-type"] par la version de MapLibre.
const MIXED_GEOMETRY_SUBLAYERS = [
  { suffix: "point", type: "circle", paintPrefix: "circle-", geometries: ["Point", "MultiPoint"] },
  {
    suffix: "line",
    type: "line",
    paintPrefix: "line-",
    geometries: ["LineString", "MultiLineString"],
  },
  {
    suffix: "polygon",
    type: "fill",
    paintPrefix: "fill-",
    geometries: ["Polygon", "MultiPolygon"],
  },
] as const;

// Tous les suffixes de sous-couche que `applyLayers` peut poser sur une
// couche : les trois de la géométrie mixte, plus les couches décoratives de
// SP-27. Une seule liste, utilisée par le rollback du catch ET par le suivi
// dans `applied` — le rollback codait auparavant en dur les trois suffixes
// de MIXED_GEOMETRY_SUBLAYERS, et toute nouvelle sous-couche fuyait, laissant
// la source référencée donc non supprimable (constat 3.5 du pré-vol).
const SUBLAYER_SUFFIXES = ["__point", "__line", "__polygon", "__outline", "__icon"] as const;

// Le `paint` de l'auteur est typé pour UNE géométrie : poser un "fill-color"
// sur un layer "circle" fait lever MapLibre, et la garde par couche
// d'applyLayers avalerait alors toute la couche. On ne transmet à chaque
// sous-couche que les propriétés de peinture qui la concernent.
function paintFor(paint: Record<string, unknown> | undefined, prefix: string) {
  return Object.fromEntries(Object.entries(paint ?? {}).filter(([k]) => k.startsWith(prefix)));
}

// `symbology`, quand présent, l'emporte sur `paint` : le domaine/la palette
// sont déjà figés dans la config (Task 6, mapSymbology.ts), donc ce calcul
// est pur et synchrone, sans appel réseau. `paint` reste le chemin manuel
// pour toute couche sans symbology (branche inchangée ci-dessous).
//
// Le `geometryKind` est désormais un paramètre explicite, jamais dérivé en
// interne : une couche tuilée de géométrie mixte/inconnue (I1 de la revue
// finale SP-24) pose TROIS sous-couches (MIXED_GEOMETRY_SUBLAYERS), chacune
// d'une géométrie réelle différente. Avant ce fix, `effectivePaint`
// calculait un seul paint pour `layer.geometryKind ?? "polygon"` — la
// géométrie mixte tombait donc toujours sur "polygon", et `buildMapPaint` ne
// produisait que des clés `fill-*` : les sous-couches point/ligne recevaient
// un paint vide (non stylé), sans aucune indication qu'un encodage avait été
// perdu (I4 de la revue finale SP-25). Chaque appelant fournit maintenant la
// géométrie réelle de la sous-couche qu'il pose — un appel de
// `buildMapPaint` par géométrie présente sur la couche, jamais un seul calcul
// partagé. Pour une couche "feature", le `geometryKind` doit produire la même
// clé de paint que le type de layer MapLibre réellement posé par le switch
// existant sur `layer.renderAs ?? "fill"` juste plus bas (circle→"point",
// line→"line", fill→"polygon") : jamais une géométrie détectée, toujours
// celle qu'implique le choix d'auteur `renderAs`, sous peine de poser par ex.
// "fill-color" sur un layer MapLibre de type "circle" (rejeté par MapLibre,
// la couche entière serait alors avalée par le garde-fou try/catch
// d'applyLayers).
function effectivePaint(
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>,
  geometryKind: GeometryKind,
  themeColors: ThemeColors | undefined,
): MapPaintResult {
  if (!layer.symbology)
    return { renderAs: renderAsFor(geometryKind), paint: layer.paint ?? {}, iconImages: [] };
  const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
    layer.symbology,
    themeColors,
  );
  return buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette, {
    stroke,
    opacity: layer.symbology.opacity,
    icon: layer.symbology.icon,
  });
}

// `AddLayerObject` est une union discriminée par `type` : un `type` calculé ne
// la réduit pas, d'où le switch — même raison que la branche `feature`
// ci-dessous, et jamais un cast (cf. commentaire de la branche `vector`).
function addTypedLayer(
  map: maplibregl.Map,
  spec: {
    id: string;
    type: "circle" | "line" | "fill";
    source: string;
    sourceLayer?: string;
    filter?: FilterSpecification;
    paint: Record<string, unknown>;
  },
) {
  const common = {
    id: spec.id,
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    paint: spec.paint,
  };
  switch (spec.type) {
    case "circle":
      map.addLayer({ ...common, type: "circle" });
      break;
    case "line":
      map.addLayer({ ...common, type: "line" });
      break;
    default:
      map.addLayer({ ...common, type: "fill" });
      break;
  }
}

// Le contour d'un polygone a besoin d'une vraie couche `line` : MapLibre n'a
// pas de fill-outline-width (déviation 2 du plan). Partage la source, la
// source-layer et le filtre de la couche de remplissage qu'elle décore.
// Volontairement SANS handler de clic : deux couches superposées sur la même
// source déclenchent le handler deux fois pour un seul clic (popup ouvert
// deux fois, cross-filter émis deux fois).
function addOutlineLayer(
  map: maplibregl.Map,
  spec: {
    parentId: string;
    source: string;
    sourceLayer?: string;
    filter?: FilterSpecification;
    paint: Record<string, unknown>;
  },
) {
  map.addLayer({
    id: `${spec.parentId}__outline`,
    type: "line",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    paint: spec.paint,
  });
}

// Partagé par les couches tuilées et GeoJSON : une seule définition du "que
// vaut l'identité d'une entité cliquée". ST_AsMVT ne pose un feature id que
// sur une PK entière, d'où le repli sur la propriété de PK.
// Les icônes catégorielles vivent sur une couche `symbol` appariée : le
// `icon-image` est une propriété LAYOUT, qu'un layer `circle` n'accepte pas
// (le validateur rejetterait la couche entière, en silence). Sans handler de
// clic, comme le contour : la couche est posée exactement sur les points, et
// un handler y ferait doubler chaque clic.
function addIconLayer(
  map: maplibregl.Map,
  spec: {
    parentId: string;
    source: string;
    sourceLayer?: string;
    filter?: FilterSpecification;
    layout: Record<string, unknown>;
  },
) {
  map.addLayer({
    id: `${spec.parentId}__icon`,
    type: "symbol",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    layout: spec.layout,
  } as maplibregl.AddLayerObject);
}

function makeFeatureClickHandler(
  pkColumn: string | undefined,
  onFeatureClick: (record: DataRecord) => void,
  // Toujours appelé : c'est `handlePopup` (côté React, qui relit la config à
  // chaque rendu) qui décide si la couche a encore un popup — le handler ne
  // capture donc plus `layer.popup`, et une modification du popup n'oblige
  // plus à reconstruire la carte (I5 de la revue finale SP-24).
  onPopup: (properties: Record<string, unknown>, lngLat: { lng: number; lat: number }) => void,
) {
  return (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f) return;
    const properties = (f.properties ?? {}) as Record<string, unknown>;
    // Le popup s'ouvre même sans identité utilisable : les attributs sont là,
    // c'est la seule chose dont il a besoin. Le repli d'id ne conditionne que
    // la sélection et le cross-filter.
    onPopup(properties, e.lngLat);
    const fallback = pkColumn ? properties[pkColumn] : undefined;
    const id = (f.id ?? fallback) as string | number | undefined;
    if (id == null) return;
    onFeatureClick({ id, properties, geometry: f.geometry });
  };
}

function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  onFeatureClick: (record: DataRecord) => void,
  onPopup: (
    layerId: string,
    properties: Record<string, unknown>,
    lngLat: { lng: number; lat: number },
  ) => void,
  themeColors: ThemeColors | undefined,
) {
  // Deux passes : tous les layers, PUIS toutes les sources. Une couche de
  // géométrie mixte pose plusieurs layers sur une seule source (cf.
  // MIXED_GEOMETRY_SUBLAYERS) et MapLibre refuse de retirer une source encore
  // référencée par un layer.
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    const prevHandler = clickHandlers.get(id);
    if (prevHandler) {
      map.off("click", id, prevHandler);
      clickHandlers.delete(id);
    }
  });
  applied.forEach((id) => {
    if (map.getSource(id)) map.removeSource(id);
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck" || layer.kind === "tiles3d") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        // Une couche = une source, mais pas forcément un seul layer : une
        // géométrie inconnue/mixte en pose trois (MIXED_GEOMETRY_SUBLAYERS).
        const layerIds: string[] = [];
        // Couches décoratives (contour, ...) : jamais de handler de clic,
        // seulement suivies dans `applied` pour le nettoyage.
        const decorativeIds: string[] = [];
        if (layer.geometryKind === undefined) {
          // Un paint par sous-couche, calculé pour SA géométrie réelle (I4
          // de la revue finale SP-25) — jamais un unique `vectorPaint`
          // calculé pour "polygon" puis filtré par préfixe, qui ne stylait
          // jamais les sous-couches point/ligne. `paintFor` reste
          // nécessaire même ici : pour le chemin `layer.paint` manuel (sans
          // symbology), le même objet brut peut porter des clés de
          // plusieurs préfixes à la fois (cf. test "paint is split by
          // prefix").
          for (const sub of MIXED_GEOMETRY_SUBLAYERS) {
            const id = `${layer.id}__${sub.suffix}`;
            const result = effectivePaint(layer, sub.suffix, themeColors);
            addTypedLayer(map, {
              id,
              type: sub.type,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
              paint: paintFor(result.paint, sub.paintPrefix),
            });
            layerIds.push(id);
            if (sub.suffix === "point" && result.iconLayout) {
              addIconLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
                layout: result.iconLayout,
              });
              decorativeIds.push(`${id}__icon`);
            }
            if (sub.suffix === "polygon" && result.outlinePaint) {
              addOutlineLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
                paint: result.outlinePaint,
              });
              decorativeIds.push(`${id}__outline`);
            }
          }
        } else {
          const result = effectivePaint(layer, layer.geometryKind, themeColors);
          addTypedLayer(map, {
            id: layer.id,
            type: layerTypeFor(layer.geometryKind),
            source: layer.id,
            sourceLayer: layer.sourceLayer,
            paint: result.paint,
          });
          layerIds.push(layer.id);
          if (layer.geometryKind === "point" && result.iconLayout) {
            addIconLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              layout: result.iconLayout,
            });
            decorativeIds.push(`${layer.id}__icon`);
          }
          if (layer.geometryKind === "polygon" && result.outlinePaint) {
            addOutlineLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              paint: result.outlinePaint,
            });
            decorativeIds.push(`${layer.id}__outline`);
          }
        }
        for (const id of layerIds) {
          const handler = makeFeatureClickHandler(
            layer.pkColumn,
            onFeatureClick,
            // Le popup est toujours identifié par l'id de la COUCHE de la
            // config, jamais par celui d'une sous-couche : c'est lui que
            // MapView recroise avec config.layers.
            (properties, lngLat) => onPopup(layer.id, properties, lngLat),
          );
          map.on("click", id, handler);
          clickHandlers.set(id, handler);
          applied.add(id);
        }
        for (const id of decorativeIds) applied.add(id);
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        const featureGeometryKind: GeometryKind =
          layer.renderAs === "circle" ? "point" : layer.renderAs === "line" ? "line" : "polygon";
        const featureResult = effectivePaint(layer, featureGeometryKind, themeColors);
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({
              id: layer.id,
              type: "circle",
              source: layer.id,
              paint: featureResult.paint,
            });
            break;
          case "line":
            map.addLayer({
              id: layer.id,
              type: "line",
              source: layer.id,
              paint: featureResult.paint,
            });
            break;
          default:
            map.addLayer({
              id: layer.id,
              type: "fill",
              source: layer.id,
              paint: featureResult.paint,
            });
            break;
        }
        if (featureGeometryKind === "polygon" && featureResult.outlinePaint) {
          addOutlineLayer(map, {
            parentId: layer.id,
            source: layer.id,
            paint: featureResult.outlinePaint,
          });
          applied.add(`${layer.id}__outline`);
        }
        if (featureGeometryKind === "point" && featureResult.iconLayout) {
          addIconLayer(map, {
            parentId: layer.id,
            source: layer.id,
            layout: featureResult.iconLayout,
          });
          applied.add(`${layer.id}__icon`);
        }
        const handler = makeFeatureClickHandler(undefined, onFeatureClick, (properties, lngLat) =>
          onPopup(layer.id, properties, lngLat),
        );
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map. Roll back any
      // half-added source/layer so it can't orphan or clash on the next apply.
      // Les sous-couches d'une géométrie mixte en font partie : elles sont
      // déjà dans `applied`, donc la prochaine passe de nettoyage les prendra,
      // mais on les retire tout de suite pour ne pas laisser la source
      // référencée (et donc non supprimable) derrière nous.
      for (const suffix of SUBLAYER_SUFFIXES) {
        const id = `${layer.id}${suffix}`;
        if (map.getLayer(id)) map.removeLayer(id);
        applied.delete(id);
        // Le contour d'une sous-couche de géométrie mixte porte un double
        // suffixe (ex. "communes__polygon__outline").
        for (const inner of SUBLAYER_SUFFIXES) {
          const nested = `${id}${inner}`;
          if (map.getLayer(nested)) map.removeLayer(nested);
          applied.delete(nested);
        }
      }
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      applied.delete(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
}

// map.addImage doit finir par arriver pour que la couche `symbol` affiche
// quelque chose — mais PAS avant addLayer : Style.addImage appelle
// _afterImageUpdated(id), qui marque l'image changée et fait repeindre les
// couches symbol qui la référencent. On pose donc les couches
// synchroniquement (aucun test existant ne casse) et on charge les images
// après, en tâche de fond.
//
// allSettled + try/catch par id : une seule icône illisible ne doit jamais
// faire échouer les autres, ni remonter en rejection non gérée.
async function loadIconImages(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  loadCustomIcon: ((iconId: string) => Promise<Blob>) | undefined,
) {
  const ids = new Set<string>();
  for (const layer of layers) {
    if (!layer.visible) continue;
    if (layer.kind !== "vector" && layer.kind !== "feature") continue;
    const icon = layer.symbology?.icon;
    if (!icon) continue;
    for (const ref of Object.values(icon.mapping)) ids.add(iconImageId(ref));
    if (icon.fallback) ids.add(iconImageId(icon.fallback));
  }
  await Promise.allSettled(
    [...ids].map(async (id) => {
      try {
        if (map.hasImage(id)) return;
        let image: HTMLImageElement | undefined;
        if (id.startsWith("lucide:")) {
          image = await rasterizeLucideIcon(id.slice("lucide:".length));
        } else if (id.startsWith("custom:") && loadCustomIcon) {
          // Blob récupéré par fetch AUTHENTIFIÉ (ItemClient) puis décodé
          // localement : jamais `new Image().src = <url du cœur>`, qui ne
          // porte aucun en-tête et prendrait un 401 (constat 4.4). L'URL
          // passée à Image est une URL d'objet locale, same-origin.
          const blob = await loadCustomIcon(id.slice("custom:".length));
          image = await decodeIconImage(blob);
        }
        if (!image) return;
        // Pas d'option { sdf: true } : l'image est du RGBA ordinaire.
        // HTMLImageElement est accepté par addImage (signature vérifiée).
        if (!map.hasImage(id)) map.addImage(id, image);
      } catch (err) {
        console.warn(`MapView: icône ${id} non chargée`, err);
      }
    }),
  );
}

// Projection d'une couche sur ce que MapLibre/deck.gl en consomment : `popup`
// n'est jamais lu par le moteur cartographique, seulement par le rendu React
// d'un clic déjà survenu (cf. layersKey dans MapView).
function mapRelevantLayer(layer: MapConfig["layers"][number]) {
  if ("popup" in layer) {
    const { popup: _popup, ...rest } = layer;
    return rest;
  }
  return layer;
}

type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;
type Tiles3DMapLayer = Extract<MapConfig["layers"][number], { kind: "tiles3d" }>;

function buildDeckLayer(layer: DeckLayer) {
  // Canonical fields last so user props can't shadow the id Deck.gl uses for
  // layer reconciliation, nor the data source.
  const props = { ...(layer.props ?? {}), id: layer.id, data: layer.dataUrl };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
    default:
      // Exhaustiveness guard: a new deckType turns into a compile error here.
      return layer.deckType satisfies never;
  }
}

// Identity of a *tileset*, not of a layer: re-pointing the same layer id at a
// different tileset URL must invalidate the "already loaded" bookkeeping used
// by the export-readiness gate below.
function tilesetKey(layer: Tiles3DMapLayer) {
  return `${layer.id}\n${layer.url}`;
}

function buildTiles3DLayer(
  layer: Tiles3DMapLayer,
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
  getCoreUrl?: () => string,
) {
  const token = isHostedTilesetUrl(layer.url, getCoreUrl?.()) ? getAuthToken?.() : undefined;
  return new Tile3DLayer({
    id: layer.id,
    data: layer.url,
    loader: Tiles3DLoader,
    loadOptions: token ? { fetch: { headers: { Authorization: `Bearer ${token}` } } } : undefined,
    // Fired once the root tileset has loaded. Deck.gl loads 3D Tiles entirely
    // outside MapLibre's knowledge, so this is the only signal that tells the
    // export worker the tileset is actually on screen (see onReady below).
    onTilesetLoad: () => onTilesetLoad?.(tilesetKey(layer)),
  });
}

function applyDeckLayers(
  overlay: MapboxOverlay,
  layers: MapConfig["layers"],
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
  getCoreUrl?: () => string,
) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  const tiles3dLayers = layers
    .filter((l): l is Tiles3DMapLayer => l.visible && l.kind === "tiles3d")
    .map((l) => buildTiles3DLayer(l, onTilesetLoad, getAuthToken, getCoreUrl));
  overlay.setProps({ layers: [...deckLayers, ...tiles3dLayers] });
}

// Full teardown-then-rebuild on every apply, mirroring applyLayers' pattern
// for the MapLibre-native layer array — simpler than diffing, and the only
// way to pick up a changed tilesUrl (MapLibre raster-dem sources are
// immutable once created).
function applyTerrain(map: maplibregl.Map, terrain: MapConfig["terrain"] | null | undefined) {
  map.setTerrain(null);
  if (map.getSource(TERRAIN_SOURCE_ID)) map.removeSource(TERRAIN_SOURCE_ID);
  // A blank URL is the transient state right after the author ticks "Activer
  // le terrain 3D" (TerrainPanel emits tilesUrl: "" first). Building a
  // raster-dem source on it fires doomed tile requests for nothing.
  if (!terrain || !terrain.tilesUrl.trim()) return;
  map.addSource(TERRAIN_SOURCE_ID, {
    type: "raster-dem",
    tiles: [terrain.tilesUrl],
    tileSize: 256,
    encoding: terrain.encoding,
  });
  map.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: terrain.exaggeration ?? 1 });
}

export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: {
      center: [number, number];
      zoom: number;
      bbox: [number, number, number, number];
      pitch: number;
      bearing: number;
    }) => void;
    onFeatureClick?: (record: DataRecord) => void;
    // Fired once the map has settled after its first load (MapLibre "idle":
    // no pending tiles/style/sprite loads) *and* every visible tiles3d layer's
    // root tileset has loaded — the real "ready to capture" signal for
    // exportRender mode (SP-17a Task 10), as opposed to a fixed delay.
    // MapLibre knows nothing about deck.gl's Tile3DLayer streaming, so "idle"
    // on its own would let a capture happen with the tileset still missing.
    onReady?: () => void;
    // Suppresses the built-in interactive legend. Used by exportRender mode
    // (MapEditorPage), which renders its own legend overlay driven by
    // `printLayout.showLegend` — without this, that toggle couldn't ever
    // hide the legend from a capture (this MapLegend would still render
    // underneath it, and both would duplicate when showLegend is true).
    hideLegend?: boolean;
    // Couleurs de thème résolvant `palette: "theme-primary"` dans la
    // symbologie (Task 6/19) — sans elle, cette palette dégrade sur son
    // repli neutre.
    themeColors?: ThemeColors;
    // Authenticates Tile3DLayer requests against a hosted (design
    // /tileset3d/) tileset's proxy route — never sent for external tileset
    // URLs (see HOSTED_TILESET3D_PATH check in buildTiles3DLayer). Absent by
    // default: a MapView with no hosted tiles3d layer needs no auth plumbing.
    getAuthToken?: () => string | undefined;
    // The core API's base URL, used alongside getAuthToken to verify a
    // tiles3d layer's URL actually belongs to our own authenticated proxy
    // (origin+path check) before attaching a bearer token — see
    // isHostedTilesetUrl. Absent by default, same as getAuthToken.
    getCoreUrl?: () => string;
    // Récupère un blob d'icône personnalisée (fetch authentifié via
    // ItemClient), passé à `decodeIconImage` par `loadIconImages`. Absent par
    // défaut : un MapView sans icône personnalisée n'a besoin d'aucun
    // câblage (Task 12 le fournit depuis les deux hôtes).
    loadCustomIcon?: (iconId: string) => Promise<Blob>;
  }
  // Il n'y a délibérément pas de prop `exprContext` : le gabarit de popup
  // n'a qu'un seul vocabulaire, `record.*` (cf. popupContent.ts). La prop
  // existait, mais aucun site de montage réel ne la passait — I4 de la revue
  // finale SP-24 — et aucun n'a de quoi la remplir : MapEditorPage n'a ni
  // variables ni contexte d'app, et ni mapWidget ni ExplorerDrawer n'exposent
  // l'ExprContext de l'ActionBus au rendu. Une capacité annoncée par
  // l'éditeur et vide à l'exécution est pire que pas de capacité.
>(function MapView(
  {
    config,
    onViewChange,
    onFeatureClick,
    onReady,
    hideLegend,
    themeColors,
    getAuthToken,
    getCoreUrl,
    loadCustomIcon,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(
    new Map(),
  );
  // The style's *initial* load — the only real precondition of addSource /
  // addLayer / setTerrain. `map.isStyleLoaded()` was used here before and is a
  // different question ("is nothing loading right now?"): a single in-flight
  // tile request made it return false, and every config update that landed in
  // that window was silently dropped with nothing to retry it.
  const styleLoadedRef = useRef(false);
  // Export readiness (onReady) = MapLibre idle AND every visible tiles3d
  // tileset loaded. Deck.gl's Tile3DLayer streams outside MapLibre, so "idle"
  // alone can fire while a tileset is still missing from the capture.
  const idleRef = useRef(false);
  const readyFiredRef = useRef(false);
  const loadedTilesetsRef = useRef<Set<string>>(new Set());
  // Popup ouvert : la couche qui l'a ouvert, les propriétés de l'entité, et le
  // point géographique cliqué (reprojeté à chaque déplacement de la carte).
  const [popup, setPopup] = useState<{
    layerId: string;
    properties: Record<string, unknown>;
    lngLat: { lng: number; lat: number };
  } | null>(null);
  const [popupPoint, setPopupPoint] = useState<{ x: number; y: number } | null>(null);
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const onReadyRef = useRef(onReady);
  const getAuthTokenRef = useRef(getAuthToken);
  const getCoreUrlRef = useRef(getCoreUrl);
  const loadCustomIconRef = useRef(loadCustomIcon);
  const themeColorsRef = useRef(themeColors);
  const layersRef = useRef(config.layers);
  const terrainRef = useRef(config.terrain);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
  useEffect(() => {
    getAuthTokenRef.current = getAuthToken;
  }, [getAuthToken]);
  useEffect(() => {
    getCoreUrlRef.current = getCoreUrl;
  }, [getCoreUrl]);
  useEffect(() => {
    loadCustomIconRef.current = loadCustomIcon;
  }, [loadCustomIcon]);
  useEffect(() => {
    themeColorsRef.current = themeColors;
  }, [themeColors]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
  useEffect(() => {
    terrainRef.current = config.terrain;
  });

  const maybeFireReady = useCallback(() => {
    if (readyFiredRef.current || !idleRef.current) return;
    const pending = layersRef.current.some(
      (l) => l.visible && l.kind === "tiles3d" && !loadedTilesetsRef.current.has(tilesetKey(l)),
    );
    if (pending) return;
    readyFiredRef.current = true;
    onReadyRef.current?.();
  }, []);

  const handleTilesetLoad = useCallback(
    (key: string) => {
      loadedTilesetsRef.current.add(key);
      maybeFireReady();
    },
    [maybeFireReady],
  );

  // Un seul clic ouvre au plus un popup : une deuxième entité cliquée
  // remplace l'état plutôt que de l'empiler (setPopup, pas un tableau).
  // La porte « cette couche a-t-elle un popup ? » est ICI et pas dans le
  // handler MapLibre : lue depuis layersRef (à jour à chaque rendu), elle
  // n'oblige pas à réenregistrer les handlers — donc à détruire et
  // reconstruire toute la carte — quand l'auteur tape dans PopupEditor
  // (I5 de la revue finale SP-24).
  const handlePopup = useCallback(
    (
      layerId: string,
      properties: Record<string, unknown>,
      lngLat: { lng: number; lat: number },
    ) => {
      const layer = layersRef.current.find((l) => l.id === layerId);
      if (!layer || !("popup" in layer) || !layer.popup) return;
      setPopup({ layerId, properties, lngLat });
    },
    [],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
      transformRequest: (url: string) => {
        const coreUrl = getCoreUrlRef.current?.();
        if (isHostedTerrainUrl(url, coreUrl) || isHostedCollectionUrl(url, coreUrl)) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
    });
    mapRef.current = map;
    // interleaved: deck.gl layers are inserted into MapLibre's own layer stack
    // and share its WebGL2 context + depth buffer, so 3D Tiles are correctly
    // occluded by the terrain instead of always drawing on top.
    const overlay = new MapboxOverlay({ layers: [], interleaved: true });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      styleLoadedRef.current = true;
      map.addSource(HIGHLIGHT_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: HIGHLIGHT_ID,
        type: "line",
        source: HIGHLIGHT_ID,
        paint: { "line-color": "#ef4444", "line-width": 3 },
      });
      applyLayers(
        map,
        layersRef.current,
        appliedRef.current,
        clickHandlersRef.current,
        (r) => onFeatureClickRef.current?.(r),
        handlePopup,
        themeColorsRef.current,
      );
      void loadIconImages(map, layersRef.current, loadCustomIconRef.current);
      applyDeckLayers(
        overlay,
        layersRef.current,
        handleTilesetLoad,
        getAuthTokenRef.current,
        getCoreUrlRef.current,
      );
      applyTerrain(map, terrainRef.current);
      // `once()` est typé `this | Promise<any>` côté maplibre-gl (le
      // second membre de l'union ne s'applique que si aucun listener n'est
      // fourni — ici il y en a un, le retour réel est toujours `this`,
      // jamais une Promise) : `void` neutralise le faux positif de type
      // sans changer de comportement.
      void map.once("idle", () => {
        idleRef.current = true;
        maybeFireReady();
      });
    });
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      cb({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
        bbox: bounds,
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      });
    });
    // Style.addLayer/addSource valident et font `return` : l'erreur part sur
    // l'event `error`, JAMAIS en exception — le try/catch d'applyLayers ne
    // voit rien et la couche disparaît en silence. Ce listener est la seule
    // chose qui rend ce mode de panne observable.
    //
    // FILTRÉ (constat N13) : MapLibre fire `error` pour toute défaillance
    // ordinaire — tuile 404, sprite manquant, style partiellement
    // inaccessible. Journaliser tout produirait un bruit permanent sur
    // demotiles.maplibre.org ou sur une collection non publique, ce qui
    // détruirait précisément la valeur de signal cherchée ici. Les erreurs du
    // validateur de style sont reconnaissables : leur message commence par
    // `layers.` / `layers[` / `sources.` / `sources[` (préfixe posé par
    // Style._validate via `layers.${id}`).
    map.on("error", (e: unknown) => {
      const message = String(
        (e as { error?: { message?: unknown } } | undefined)?.error?.message ?? "",
      );
      if (!/^(layers|sources)[.[]/.test(message)) return;
      console.error("MapView: MapLibre a signalé une erreur", e);
    });
    return () => {
      map.removeControl(overlay);
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
      styleLoadedRef.current = false;
      idleRef.current = false;
      readyFiredRef.current = false;
      // La règle suggère de copier la ref dans une variable locale au
      // montage pour éviter qu'elle "ait changé" au nettoyage — mais c'est
      // précisément le comportement voulu ici : cet effet ne monte/démonte
      // qu'une fois (cf. dépendances [] ci-dessous), et on veut vider
      // l'ensemble accumulé sur toute la durée de vie du composant, pas un
      // instantané pris au montage.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      loadedTilesetsRef.current.clear();
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Identité de ce que MapLibre consomme réellement d'une couche, `popup`
  // exclu : lui n'affecte que le rendu React d'un clic déjà survenu. Sans
  // cette projection, chaque frappe dans un champ de PopupEditor produisait un
  // nouveau tableau `config.layers` et détruisait/reconstruisait TOUTES les
  // sources et couches — scintillement, re-requêtes de tuiles, et un refetch
  // complet du GeoJSON /items pour une couche `feature` (I5 de la revue
  // finale SP-24).
  const layersKey = useMemo(
    () => JSON.stringify({ layers: config.layers.map(mapRelevantLayer), themeColors }),
    [config.layers, themeColors],
  );

  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !styleLoadedRef.current || !overlay) return;
    // layersRef, pas config.layers : l'effet ne se déclenche que sur
    // `layersKey`, mais doit appliquer les couches courantes (la ref est
    // rafraîchie par un effet déclaré plus haut, donc exécuté avant celui-ci).
    const layers = layersRef.current;
    applyLayers(
      map,
      layers,
      appliedRef.current,
      clickHandlersRef.current,
      (r) => onFeatureClickRef.current?.(r),
      handlePopup,
      themeColorsRef.current,
    );
    void loadIconImages(map, layers, loadCustomIconRef.current);
    applyDeckLayers(
      overlay,
      layers,
      handleTilesetLoad,
      getAuthTokenRef.current,
      getCoreUrlRef.current,
    );
  }, [layersKey, handleTilesetLoad, handlePopup]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    applyTerrain(map, config.terrain);
  }, [config.terrain]);

  // Reprojection du point cliqué à chaque déplacement de la carte : sans ce
  // listener, un popup ouvert resterait figé au pixel de l'ouverture pendant
  // qu'on pan/zoom la carte sous lui. Un seul listener à la fois — le nettoyage
  // le retire avant que l'effet ne s'exécute à nouveau (nouveau popup ou
  // fermeture), jamais accumulé au clic.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !popup) {
      setPopupPoint(null);
      return;
    }
    const reproject = () => setPopupPoint(map.project(popup.lngLat));
    reproject();
    map.on("move", reproject);
    return () => {
      map.off("move", reproject);
    };
  }, [popup]);

  // Ferme le popup quand la couche qui l'a ouvert disparaît de la config, ou
  // quand elle garde son id mais perd sa configuration `popup` — l'absence de
  // `popup` sur la couche EST l'état désactivé (types.ts), et
  // `resolvePopupContent` se réévalue à chaque rendu : le laisser ouvert
  // ferait retomber sur sa branche "pas de config → tout afficher", exposant
  // des champs que l'auteur avait explicitement exclus. Un popup ne doit
  // jamais survivre à la disparition de sa propre configuration.
  useEffect(() => {
    if (!popup) return;
    const layer = config.layers.find((l) => l.id === popup.layerId);
    const stillConfigured = !!layer && "popup" in layer && !!layer.popup;
    if (!stillConfigured) setPopup(null);
  }, [config.layers, popup]);

  useImperativeHandle(
    ref,
    () => ({
      flyTo: (opts) => {
        mapRef.current?.flyTo(opts);
      },
      highlight: (geometry) => {
        const src = mapRef.current?.getSource(HIGHLIGHT_ID) as
          { setData?: (d: unknown) => void } | undefined;
        src?.setData?.(
          geometry
            ? { type: "Feature", geometry, properties: {} }
            : { type: "FeatureCollection", features: [] },
        );
      },
    }),
    [],
  );

  const popupLayer = popup ? config.layers.find((l) => l.id === popup.layerId) : undefined;
  // `popup` n'est porté que par les variantes "vector"/"feature" de l'union
  // discriminée `MapLayer` — un accès défensif plutôt qu'un cast reste
  // compilable sur l'union complète (les variantes "raster"/"deck"/"tiles3d"
  // n'ont pas de champ `popup` du tout).
  const popupConfig = popupLayer && "popup" in popupLayer ? popupLayer.popup : undefined;

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      {!hideLegend && <MapLegend layers={config.layers} />}
      {popup && popupPoint && (
        <MapPopup
          content={resolvePopupContent(popupConfig, popup.properties)}
          x={popupPoint.x}
          y={popupPoint.y}
          onClose={() => setPopup(null)}
        />
      )}
    </div>
  );
});
