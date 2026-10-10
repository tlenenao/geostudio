// SPDX-License-Identifier: Apache-2.0
import * as maplibregl from "maplibre-gl";
import type { DataRecord, MapConfig, ThemeColors } from "../api/types";
import { type GeometryKind } from "../builder/widgets/mapSymbology";
import { decodeIconImage, rasterizeLucideIcon } from "../builder/widgets/iconLibrary";
import { buildLabelFeatureCollection } from "./labelSource";
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
} from "./mapLayerBuild";

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
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        const featureGeometryKind: GeometryKind =
          layer.renderAs === "circle" ? "point" : layer.renderAs === "line" ? "line" : "polygon";
        const featureResult = effectivePaint(layer, featureGeometryKind, themeColors);
        for (const imageId of featureResult.iconImages) iconImages.add(imageId);
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
        const featureLabel = layer.symbology?.label;
        if (
          featureLabel &&
          addLabelLayer(map, { parentId: layer.id, label: featureLabel }, lastLabelPayloads)
        ) {
          applied.add(`${layer.id}__label`);
          applied.add(`${layer.id}__labels`);
        }
        const handler = makeFeatureClickHandler(
          undefined,
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
) {
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
    const features =
      layer.kind === "vector"
        ? map.querySourceFeatures(layer.id, { sourceLayer: layer.sourceLayer })
        : map.querySourceFeatures(layer.id);
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
