// SPDX-License-Identifier: Apache-2.0
import * as maplibregl from "maplibre-gl";
import type { DataRecord, MapConfig, ThemeColors } from "../api/types";
import { type GeometryKind } from "../builder/widgets/mapSymbology";
import { decodeIconImage, rasterizeLucideIcon } from "../builder/widgets/iconLibrary";
import { buildLabelFeatureCollection } from "./labelSource";
import { generateDots } from "../builder/widgets/advancedSymbology";
import { t } from "../i18n";
import {
  layerTypeFor,
  MIXED_GEOMETRY_SUBLAYERS,
  SUBLAYER_SUFFIXES,
  SUBSOURCE_SUFFIXES,
  paintFor,
  effectivePaint,
  addTypedLayer,
  addAggregateLayer,
  notAggregated,
  addOutlineLayer,
  addIconLayer,
  addLabelLayer,
  makeFeatureClickHandler,
  addClusterLayers,
  addDotLayer,
  addEffectLayers,
  clusterSourceOptions,
  makeClusterClickHandler,
} from "./mapLayerBuild";
import "../i18n/domains/map";

export function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  // Ref-backed, par instance de MapView — voir lastLabelPayloadsRef.
  lastLabelPayloads: Map<string, string>,
  onFeatureClick: (record: DataRecord) => void,
  onPopup: (
    layerId: string,
    properties: Record<string, unknown>,
    lngLat: { lng: number; lat: number },
    id: string | number | undefined,
  ) => void,
  themeColors: ThemeColors | undefined,
  // Rempli par CETTE passe : les ids d'image résolus par `effectivePaint`
  // (déjà filtrés au domaine figé, dédoublonnés, ordre valeurs-puis-repli —
  // cf. buildMapPaint) pour chaque sous-couche réellement posée. Fix I1 de la
  // revue finale SP-27 : `loadIconImages` consommait auparavant
  // `layer.symbology.icon.mapping` directement, sans garde de géométrie ni
  // filtre de domaine — une seconde copie de la logique que `effectivePaint`
  // calcule déjà ICI, dans la même passe. On la retourne au lieu de la
  // recalculer.
): string[] {
  const iconImages = new Set<string>();
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
    // Purge la dernière charge mémorisée (garde d'idempotence du constat
    // N3) : sans cela, un cycle retrait → ré-ajout de la même couche
    // d'étiquettes avec les mêmes entités ne reposerait jamais la source, la
    // source neuve étant alors vide alors que le garde croit que rien n'a
    // changé. No-op pour tout id qui n'est pas une source d'étiquettes.
    lastLabelPayloads.delete(id);
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
            for (const imageId of result.iconImages) iconImages.add(imageId);
            addTypedLayer(map, {
              id,
              type: sub.type,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: notAggregated(["match", ["geometry-type"], [...sub.geometries], true, false]),
              paint: paintFor(result.paint, sub.paintPrefix),
            });
            layerIds.push(id);
            decorativeIds.push(
              ...addEffectLayers(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: notAggregated([
                  "match",
                  ["geometry-type"],
                  [...sub.geometries],
                  true,
                  false,
                ]),
                renderAs: sub.type,
                paint: paintFor(result.paint, sub.paintPrefix),
                effects: layer.symbology?.effects,
              }),
            );
            if (sub.suffix === "point" && result.iconLayout) {
              addIconLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: notAggregated([
                  "match",
                  ["geometry-type"],
                  [...sub.geometries],
                  true,
                  false,
                ]),
                layout: result.iconLayout,
              });
              decorativeIds.push(`${id}__icon`);
            }
            if (sub.suffix === "polygon" && result.outlinePaint) {
              addOutlineLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: notAggregated([
                  "match",
                  ["geometry-type"],
                  [...sub.geometries],
                  true,
                  false,
                ]),
                paint: result.outlinePaint,
              });
              decorativeIds.push(`${id}__outline`);
            }
          }
        } else {
          const result = effectivePaint(layer, layer.geometryKind, themeColors);
          for (const imageId of result.iconImages) iconImages.add(imageId);
          addTypedLayer(map, {
            id: layer.id,
            type: layerTypeFor(layer.geometryKind),
            source: layer.id,
            sourceLayer: layer.sourceLayer,
            filter: notAggregated(),
            paint: result.paint,
          });
          layerIds.push(layer.id);
          decorativeIds.push(
            ...addEffectLayers(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: notAggregated(),
              renderAs: layerTypeFor(layer.geometryKind),
              paint: result.paint,
              effects: layer.symbology?.effects,
            }),
          );
          if (layer.geometryKind === "point" && result.iconLayout) {
            addIconLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: notAggregated(),
              layout: result.iconLayout,
            });
            decorativeIds.push(`${layer.id}__icon`);
          }
          if (layer.geometryKind === "polygon" && result.outlinePaint) {
            addOutlineLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: notAggregated(),
              paint: result.outlinePaint,
            });
            decorativeIds.push(`${layer.id}__outline`);
          }
        }
        // REV-283a : cellules posées par le cœur sous le zoom seuil.
        addAggregateLayer(map, layer.id, layer.sourceLayer, themeColors?.primary);
        decorativeIds.push(`${layer.id}__agg`);
        for (const id of layerIds) {
          const handler = makeFeatureClickHandler(
            layer.pkColumn,
            onFeatureClick,
            // Le popup est toujours identifié par l'id de la COUCHE de la
            // config, jamais par celui d'une sous-couche : c'est lui que
            // MapView recroise avec config.layers.
            (properties, lngLat, featureId) => onPopup(layer.id, properties, lngLat, featureId),
          );
          map.on("click", id, handler);
          clickHandlers.set(id, handler);
          applied.add(id);
        }
        for (const id of decorativeIds) applied.add(id);
        const dotColor = layer.symbology?.advanced;
        if (
          dotColor?.kind === "dotDensity" &&
          layer.geometryKind !== "point" &&
          layer.geometryKind !== "line"
        ) {
          addDotLayer(map, { parentId: layer.id, color: dotColor.color }, lastLabelPayloads);
          applied.add(`${layer.id}__dots`);
          applied.add(`${layer.id}__dotsrc`);
        }
        const label = layer.symbology?.label;
        if (label && addLabelLayer(map, { parentId: layer.id, label }, lastLabelPayloads)) {
          applied.add(`${layer.id}__label`);
          applied.add(`${layer.id}__labels`);
        }
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        // ARC-01 : le regroupement ne vaut que pour des points (renderAs circle).
        const cluster = layer.renderAs === "circle" ? layer.cluster : undefined;
        map.addSource(layer.id, {
          type: "geojson",
          data: layer.url,
          // AUD-049 : id d'entité = PK (MapLibre abandonne les id GeoJSON non numériques).
          ...(layer.pkColumn ? { promoteId: layer.pkColumn } : {}),
          ...(cluster ? clusterSourceOptions(cluster) : {}),
        });
        const featureGeometryKind: GeometryKind =
          layer.renderAs === "circle" ? "point" : layer.renderAs === "line" ? "line" : "polygon";
        const unclustered = cluster ? { filter: notAggregated() } : {};
        const featureResult = effectivePaint(layer, featureGeometryKind, themeColors);
        for (const imageId of featureResult.iconImages) iconImages.add(imageId);
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({
              id: layer.id,
              type: "circle",
              source: layer.id,
              ...unclustered,
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
        for (const id of addEffectLayers(map, {
          parentId: layer.id,
          source: layer.id,
          ...unclustered,
          renderAs: layer.renderAs ?? "fill",
          paint: featureResult.paint,
          effects: layer.symbology?.effects,
        }))
          applied.add(id);
        if (featureResult.dots) {
          addDotLayer(
            map,
            { parentId: layer.id, color: featureResult.dots.color },
            lastLabelPayloads,
          );
          applied.add(`${layer.id}__dots`);
          applied.add(`${layer.id}__dotsrc`);
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
            ...unclustered,
            layout: featureResult.iconLayout,
          });
          applied.add(`${layer.id}__icon`);
        }
        if (cluster) {
          addClusterLayers(map, layer.id, cluster, themeColors?.primary);
          const clusterHandler = makeClusterClickHandler(map, layer.id);
          map.on("click", `${layer.id}__cluster`, clusterHandler);
          clickHandlers.set(`${layer.id}__cluster`, clusterHandler);
          applied.add(`${layer.id}__cluster`);
          applied.add(`${layer.id}__cluster_count`);
        }
        const featureLabel = layer.symbology?.label;
        if (
          featureLabel &&
          addLabelLayer(map, { parentId: layer.id, label: featureLabel }, lastLabelPayloads)
        ) {
          applied.add(`${layer.id}__label`);
          applied.add(`${layer.id}__labels`);
        }
        // AUD-049 : `pkColumn` transmis (sélection/cross-filter sur PK non numérique).
        const handler = makeFeatureClickHandler(
          layer.pkColumn,
          onFeatureClick,
          (properties, lngLat, featureId) => onPopup(layer.id, properties, lngLat, featureId),
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
        const staleHandler = clickHandlers.get(id);
        if (staleHandler) {
          map.off("click", id, staleHandler);
          clickHandlers.delete(id);
        }
        applied.delete(id);
        // Le contour d'une sous-couche de géométrie mixte porte un double
        // suffixe (ex. "communes__polygon__outline").
        for (const inner of SUBLAYER_SUFFIXES) {
          const nested = `${id}${inner}`;
          if (map.getLayer(nested)) map.removeLayer(nested);
          applied.delete(nested);
        }
      }
      // Un `__labels` (source) qu'un `__label` (couche) n'a jamais atteint —
      // ex. addLayer a levé après que addSource ait réussi — fuirait sinon :
      // la boucle SUBLAYER_SUFFIXES ci-dessus ne retire que des LAYERS.
      for (const suffix of SUBSOURCE_SUFFIXES) {
        const id = `${layer.id}${suffix}`;
        if (map.getSource(id)) map.removeSource(id);
        applied.delete(id);
        lastLabelPayloads.delete(id);
      }
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      applied.delete(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
  return [...iconImages];
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
// `iconImageIds` vient de `applyLayers` (son retour, la même passe) : déjà
// filtré au `geometryKind === "point"` et au domaine figé par `buildMapPaint`
// (fix I1 de la revue finale SP-27 — cette fonction dérivait auparavant ses
// propres ids depuis `layer.symbology.icon.mapping`, sans garde de géométrie
// ni filtre de domaine, chargeant des icônes pour des couches polygone/ligne
// et des valeurs de mapping oubliées par un recalcul de domaine).
export async function loadIconImages(
  map: maplibregl.Map,
  iconImageIds: readonly string[],
  loadCustomIcon: ((iconId: string) => Promise<Blob>) | undefined,
) {
  await Promise.allSettled(
    [...new Set(iconImageIds)].map(async (id) => {
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
        console.warn(t("mapView.iconNotLoadedWarning", { id }), err);
      }
    }),
  );
}

// Remplit les sources d'étiquettes depuis les entités RÉELLEMENT chargées.
// Déclenché sur `idle` : querySourceFeatures ne parcourt que les tuiles
// rendables (getRenderableIds), donc l'appeler plus tôt renvoie du vide.
export function refreshLabelSources(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  // Ref-backed, par instance de MapView — voir lastLabelPayloadsRef. Passé
  // en paramètre plutôt que fermé sur une variable de portée module : deux
  // <MapView> peuvent partager un `layer.id` (deux widgets carte sur le même
  // tableau de bord affichant la même collection), et un Map de portée
  // module aurait alors partagé cette même entrée de garde entre les deux
  // instances (revue post-Task 14).
  lastLabelPayloads: Map<string, string>,
  // AUD-049 : fenêtre du lecteur temps ; une entité hors fenêtre n'a ni étiquette ni point.
  timeRange?: { from: string; to: string } | null,
) {
  refreshDotSources(map, layers, lastLabelPayloads, timeRange);
  for (const layer of layers) {
    if (!layer.visible) continue;
    if (layer.kind !== "vector" && layer.kind !== "feature") continue;
    const label = layer.symbology?.label;
    if (!label) continue;
    const sourceId = `${layer.id}__labels`;
    const source = map.getSource(sourceId) as { setData?: (d: unknown) => void } | undefined;
    if (!source?.setData) {
      // Couche d'étiquettes non posée (glyphs absents) : ce n'est PAS une
      // anomalie ici, addLabelLayer a déjà averti une fois. Ne pas journaliser
      // à chaque `idle`.
      continue;
    }
    // sourceLayer est OBLIGATOIRE sur une source vecteur (sinon la requête
    // renvoie zéro entité, sans erreur) et doit être ABSENT sur du GeoJSON.
    const features = timeWindowed(
      layer,
      layer.kind === "vector"
        ? map.querySourceFeatures(layer.id, { sourceLayer: layer.sourceLayer })
        : map.querySourceFeatures(layer.id),
      timeRange,
    );
    const collection = buildLabelFeatureCollection(
      features.map((f) => ({
        id: f.id,
        properties: (f.properties ?? {}) as Record<string, unknown>,
        geometry: f.geometry,
      })),
      label.template,
      { pkColumn: layer.kind === "vector" ? layer.pkColumn : undefined },
    );
    // GARDE D'IDEMPOTENCE (constat N3). Le JSON.stringify est le même travail
    // que celui que _updateWorkerData ferait de toute façon derrière setData :
    // il ne coûte donc rien de plus dans le cas « ça a changé », et il évite
    // TOUT le reste (aller-retour worker + re-tuilage + repaint + nouvel idle)
    // dans le cas « rien n'a changé », qui est le cas de tous les idle
    // consécutifs sur une carte immobile.
    const serialized = JSON.stringify(collection);
    if (lastLabelPayloads.get(sourceId) === serialized) continue;
    lastLabelPayloads.set(sourceId, serialized);
    source.setData(collection);
  }
}

// Couches `vector` à `timeField` : ne garde que les entités de la fenêtre (les `feature`
// sont déjà filtrées côté cœur par `datetime=`).
function timeWindowed<F extends { properties?: unknown }>(
  layer: MapConfig["layers"][number],
  features: F[],
  range: { from: string; to: string } | null | undefined,
): F[] {
  if (!range || layer.kind !== "vector" || !layer.timeField) return features;
  const field = layer.timeField;
  return features.filter((f) =>
    inTimeWindow(f.properties as Record<string, unknown> | null | undefined, field, range),
  );
}

// ARC-17 : remplit les sources de points Dot Density depuis les polygones
// chargés (même mécanique et même garde d'idempotence que les étiquettes ;
// déterministe, donc un `idle` sur carte immobile ne repose rien).
function refreshDotSources(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  lastPayloads: Map<string, string>,
  timeRange?: { from: string; to: string } | null,
) {
  for (const layer of layers) {
    if (!layer.visible || (layer.kind !== "vector" && layer.kind !== "feature")) continue;
    const adv = layer.symbology?.advanced;
    if (adv?.kind !== "dotDensity") continue;
    const sourceId = `${layer.id}__dotsrc`;
    const source = map.getSource(sourceId) as { setData?: (d: unknown) => void } | undefined;
    if (!source?.setData) continue;
    const features = timeWindowed(
      layer,
      layer.kind === "vector"
        ? map.querySourceFeatures(layer.id, { sourceLayer: layer.sourceLayer })
        : map.querySourceFeatures(layer.id),
      timeRange,
    );
    const collection = generateDots(
      features.map((f) => ({
        id: f.id ?? (layer.kind === "vector" ? f.properties?.[layer.pkColumn ?? ""] : undefined),
        properties: (f.properties ?? {}) as Record<string, unknown>,
        geometry: f.geometry,
      })),
      adv,
    );
    const serialized = JSON.stringify(collection);
    if (lastPayloads.get(sourceId) === serialized) continue;
    lastPayloads.set(sourceId, serialized);
    source.setData(collection);
  }
}

// Projection d'une couche sur ce que MapLibre/deck.gl en consomment : `popup`
// n'est jamais lu par le moteur cartographique, seulement par le rendu React
// d'un clic déjà survenu (cf. layersKey dans MapView).
export function mapRelevantLayer(layer: MapConfig["layers"][number]) {
  if ("popup" in layer) {
    const { popup: _popup, ...rest } = layer;
    return rest;
  }
  return layer;
}

// REV-304 : fenêtre temporelle sur les couches `vector` déclarant un
// `timeField`, par setFilter sur les sous-couches déjà posées — jamais en
// recréant sources et couches (une tuile rechargée à chaque pas du lecteur).
// `bases` mémorise le filtre d'origine de chaque sous-couche (celui posé par
// applyLayers) pour ne jamais empiler les clauses temporelles ; MapView le
// vide chaque fois que applyLayers recrée les couches. Les valeurs MVT d'une
// date sont des chaînes ISO : la comparaison lexicographique est exacte, et
// la borne haute couvre toute la journée `to`. Étiquettes et points de densité
// (alimentés par querySourceFeatures) suivent via `inTimeWindow` (AUD-049).
/** Vrai si l'entité tombe dans la fenêtre (même sémantique que le filtre MapLibre). */
export function inTimeWindow(
  properties: Record<string, unknown> | null | undefined,
  timeField: string,
  range: { from: string; to: string } | null | undefined,
): boolean {
  if (!range) return true;
  const v = properties?.[timeField];
  if (typeof v !== "string") return false;
  return v >= range.from && v <= `${range.to}T23:59:59.999999`;
}

export function applyTimeFilters(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  range: { from: string; to: string } | null | undefined,
  bases: Map<string, maplibregl.FilterSpecification | undefined>,
): void {
  for (const layer of layers) {
    if (layer.kind !== "vector" || !layer.timeField || !layer.visible) continue;
    const roots =
      layer.geometryKind === undefined
        ? MIXED_GEOMETRY_SUBLAYERS.map((s) => `${layer.id}__${s.suffix}`)
        : [layer.id];
    // REV-304 : les cellules `__agg` sont précalculées par le cœur, sans champ
    // temporel — leurs comptes seraient ceux de toute la période. Pendant qu'une
    // fenêtre est active on les masque (un compte faux est pire qu'une absence) :
    // la couche de détail, filtrée, réapparaît en zoomant.
    const aggId = `${layer.id}__agg`;
    if (map.getLayer(aggId)) {
      if (!bases.has(aggId)) bases.set(aggId, map.getFilter(aggId) ?? undefined);
      map.setFilter(
        aggId,
        (range
          ? ["==", 1, 0]
          : (bases.get(aggId) ?? null)) as maplibregl.FilterSpecification | null,
      );
    }
    // AUD-049 : toutes les sous-couches dérivées lisent la même source MVT ; on filtre
    // aussi les effets (ombre/halo/fusion), pas seulement la couche et son contour.
    const derived = ["", "__icon", "__outline", "__fx_shadow", "__fx_bloom", "__fx_blend"];
    for (const id of roots.flatMap((r) => derived.map((d) => `${r}${d}`))) {
      if (!map.getLayer(id)) continue;
      if (!bases.has(id)) bases.set(id, map.getFilter(id) ?? undefined);
      const base = bases.get(id);
      const time = range
        ? [
            "all",
            [">=", ["get", layer.timeField], range.from],
            ["<=", ["get", layer.timeField], `${range.to}T23:59:59.999999`],
          ]
        : undefined;
      const next = time ? (base ? ["all", base, time] : time) : base;
      map.setFilter(id, (next ?? null) as maplibregl.FilterSpecification | null);
    }
  }
}
