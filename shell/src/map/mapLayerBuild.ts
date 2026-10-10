// SPDX-License-Identifier: Apache-2.0
import * as maplibregl from "maplibre-gl";
import { type ExpressionSpecification, type FilterSpecification } from "maplibre-gl";
import type { DataRecord, MapLayer, ThemeColors } from "../api/types";
import {
  buildMapPaint,
  renderAsFor,
  symbologyToPaintInputs,
  type GeometryKind,
  type LayerLabel,
  type MapPaintResult,
} from "../builder/widgets/mapSymbology";
import { t } from "../i18n";

export const HIGHLIGHT_ID = "__highlight__";

// Une couche tuilée était jusqu'ici ajoutée en "fill" quel que soit son
// contenu : une collection de points ne s'affichait donc pas du tout. Le type
// MapLibre suit désormais la géométrie déclarée par la couche.
export function layerTypeFor(geometryKind: "point" | "line" | "polygon") {
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
export const MIXED_GEOMETRY_SUBLAYERS = [
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
export const SUBLAYER_SUFFIXES = [
  "__point",
  "__line",
  "__polygon",
  "__outline",
  "__icon",
  "__label",
  "__agg",
] as const;

// Les sources auxiliaires posées par applyLayers, à retirer avec la couche.
// (`__labels` est une SOURCE, `__label` la couche qui la consomme.)
export const SUBSOURCE_SUFFIXES = ["__labels"] as const;

// Le `paint` de l'auteur est typé pour UNE géométrie : poser un "fill-color"
// sur un layer "circle" fait lever MapLibre, et la garde par couche
// d'applyLayers avalerait alors toute la couche. On ne transmet à chaque
// sous-couche que les propriétés de peinture qui la concernent.
export function paintFor(paint: Record<string, unknown> | undefined, prefix: string) {
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
export function effectivePaint(
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
export function addTypedLayer(
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
export function addOutlineLayer(
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
export function addIconLayer(
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

// Charge initiale d'une source d'étiquettes, partagée par addLabelLayer (pour
// `addSource`) et le garde d'idempotence de refreshLabelSources (pour amorcer
// `lastLabelPayloads`) : les deux DOIVENT produire la même sérialisation, sous
// peine de reposer inutilement cette charge vide au tout premier `idle`.
export const EMPTY_LABEL_COLLECTION = { type: "FeatureCollection" as const, features: [] };

// Étiquettes : source GeoJSON dédiée, calculée côté client (déviation 3).
// `text-field` ne peut PAS être ["feature-state", …] — c'est une propriété
// layout, et le validateur le refuse ; il lit donc une vraie propriété
// `label` de la source. Cette source est vide à la pose : elle est remplie
// par refreshLabelSources dès que des tuiles sont chargées.
//
// `text-field` exige par ailleurs que le STYLE déclare `glyphs`. Sans lui, la
// couche serait rejetée par le validateur et disparaîtrait sans erreur : on
// préfère ne pas la poser du tout et le dire.
export function addLabelLayer(
  map: maplibregl.Map,
  spec: { parentId: string; label: LayerLabel },
  // Ref-backed Map appartenant à l'instance de MapView appelante (voir sa
  // déclaration dans le composant) — jamais un Map de portée module, sous
  // peine de partager cette bookkeeping entre deux <MapView> montés en même
  // temps (revue post-Task 14, cf. commentaire sur lastLabelPayloadsRef).
  lastLabelPayloads: Map<string, string>,
): boolean {
  // L'optional chaining est NÉCESSAIRE et non défensif : Map.getStyle() fait
  // `if (this.style) return this.style.serialize();` et Style.serialize()
  // commence par `if (!this._loaded) return;` (dist/maplibre-gl-dev.js:
  // 45157-45163) — sur un style non encore chargé, getStyle() vaut undefined.
  //
  // Le message ne doit donc PAS affirmer une cause qu'il ne connaît pas
  // (constat N10) : « le style ne déclare pas de glyphs » est faux quand le
  // style n'est simplement pas encore chargé. Deux messages distincts.
  const style = map.getStyle() as { glyphs?: string } | undefined;
  if (style === undefined) {
    console.warn(t("mapView.labelsSkippedNoStyleWarning", { parentId: spec.parentId }));
    return false;
  }
  if (!style.glyphs) {
    console.warn(t("mapView.labelsSkippedNoGlyphsWarning", { parentId: spec.parentId }));
    return false;
  }
  // Coût assumé (seconde moitié du constat N10) : serialize() sérialise TOUT
  // le style — sources et couches comprises via _serializeByIds — et
  // addLabelLayer est appelé une fois par couche étiquetée à chaque
  // applyLayers. Lire getStyle() une seule fois par passe et le passer en
  // argument serait plus économe ; ce n'est pas fait parce que applyLayers a
  // déjà huit paramètres et que le nombre de couches ÉTIQUETÉES par carte est
  // de l'ordre de 1 à 3. Consigné dans les suivis.
  const sourceId = `${spec.parentId}__labels`;
  map.addSource(sourceId, {
    type: "geojson",
    data: EMPTY_LABEL_COLLECTION,
  });
  // Amorce le garde d'idempotence (constat N3) sur cet état initial : le
  // premier `refreshLabelSources`, appelé juste après `applyLayers` alors
  // qu'aucune tuile n'est encore chargée, calculerait lui aussi une
  // FeatureCollection vide — sans cette amorce, il la reposerait via
  // `setData` une fois pour rien (un aller-retour worker + repaint gratuit,
  // exactement le coût que le garde existe pour éviter).
  lastLabelPayloads.set(sourceId, JSON.stringify(EMPTY_LABEL_COLLECTION));
  map.addLayer({
    id: `${spec.parentId}__label`,
    type: "symbol",
    source: sourceId,
    // Pas de `text-font` : le défaut du style-spec est
    // ["Open Sans Regular", "Arial Unicode MS Regular"], et nommer une police
    // absente du jeu de glyphes est un autre échec silencieux.
    layout: { "text-field": ["get", "label"], "text-size": spec.label.size },
    paint: {
      "text-color": spec.label.color,
      "text-halo-color": spec.label.haloColor,
      "text-halo-width": spec.label.haloWidth,
    },
  } as maplibregl.AddLayerObject);
  return true;
}

export function makeFeatureClickHandler(
  pkColumn: string | undefined,
  onFeatureClick: (record: DataRecord) => void,
  // Toujours appelé : c'est `handlePopup` (côté React, qui relit la config à
  // chaque rendu) qui décide si la couche a encore un popup — le handler ne
  // capture donc plus `layer.popup`, et une modification du popup n'oblige
  // plus à reconstruire la carte (I5 de la revue finale SP-24).
  onPopup: (
    properties: Record<string, unknown>,
    lngLat: { lng: number; lat: number },
    id: string | number | undefined,
  ) => void,
) {
  return (e: maplibregl.MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f) return;
    const properties = (f.properties ?? {}) as Record<string, unknown>;
    // `f.id` (id de feature top-level MapLibre) prime sur properties[pkColumn] :
    // ST_AsMVT retire la colonne PK des attributs quand elle est entière
    // (feature_id_name, cf. core/app/features/tiles.py::mvt_feature_id_column)
    // — elle n'existe alors QUE dans f.id, jamais dans properties (chantier
    // 4.12, Tâche 20). properties[pkColumn] reste le repli pour une PK non
    // entière ou une couche `feature` (GeoJSON, jamais de feature_id MVT).
    const fallback = pkColumn ? properties[pkColumn] : undefined;
    const id = (f.id ?? fallback) as string | number | undefined;
    // Le popup s'ouvre même sans identité utilisable : les attributs sont là,
    // c'est la seule chose dont il a besoin — mais on transmet quand même
    // l'id résolu, dont dépend maintenant aussi le popup (pièces jointes).
    onPopup(properties, e.lngLat, id);
    if (id == null) return;
    onFeatureClick({ id, properties, geometry: f.geometry });
  };
}

// REV-283a : sous le zoom seuil, le cœur remplace une tuile dense par des
// cellules (propriété `point_count`, même couche source). Les couches de
// données les excluent ; `__agg` les dessine seules.
export function notAggregated(filter?: ExpressionSpecification): ExpressionSpecification {
  const not: ExpressionSpecification = ["!", ["has", "point_count"]];
  return filter ? ["all", filter, not] : not;
}

export function addAggregateLayer(
  map: maplibregl.Map,
  parentId: string,
  sourceLayer: string,
  // gs-raw-color-ok: couleur de couche par défaut, valeur de symbologie utilisateur
  color = "#3b6fb6",
) {
  map.addLayer({
    id: `${parentId}__agg`,
    type: "circle",
    source: parentId,
    "source-layer": sourceLayer,
    filter: ["has", "point_count"],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "point_count"], 1, 6, 1000, 22],
      "circle-color": color,
      "circle-opacity": 0.6,
    },
  });
}
