// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type RefObject } from "react";
import type * as maplibregl from "maplibre-gl";
import { useOptionalItemClient } from "../api/ItemClientProvider";
import type { AttachmentSummary, CollectionSchemaField, MapConfig } from "../api/types";

// P30.02 : état du popup de MapView (ouverture, reprojection, fermeture,
// pièces jointes, schéma) extrait du composant. `setPopup` est appelé par le
// gestionnaire de clic de couche (handlePopup) que MapView garde.
export type MapPopupState = {
  layerId: string;
  properties: Record<string, unknown>;
  lngLat: { lng: number; lat: number };
  // Identité de l'entité cliquée, dérivée de `pkColumn` (uniquement pour les
  // couches `vector`/`feature`) : nécessaire pour retrouver ses pièces jointes
  // (chantier 4.12), absente pour tout le reste.
  fid: string | undefined;
};

export function useMapPopup(mapRef: RefObject<maplibregl.Map | null>, layers: MapConfig["layers"]) {
  const [popup, setPopup] = useState<MapPopupState | null>(null);
  const [popupPoint, setPopupPoint] = useState<{ x: number; y: number } | null>(null);
  // Résultats d'appels réseau asynchrones, jamais une projection pure de `popup`.
  const [popupAttachments, setPopupAttachments] = useState<AttachmentSummary[]>([]);
  // Schéma de la collection (D35) : formatage fr-FR des valeurs en mode `fields`.
  const [popupSchema, setPopupSchema] = useState<CollectionSchemaField[]>([]);
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
  }, [mapRef, popup]);

  // Ferme le popup quand la couche qui l'a ouvert disparaît de la config, ou
  // quand elle garde son id mais perd sa configuration `popup` — l'absence de
  // `popup` sur la couche EST l'état désactivé (types.ts), et
  // `resolvePopupContent` se réévalue à chaque rendu : le laisser ouvert
  // ferait retomber sur sa branche "pas de config → tout afficher", exposant
  // des champs que l'auteur avait explicitement exclus. Un popup ne doit
  // jamais survivre à la disparition de sa propre configuration.
  useEffect(() => {
    if (!popup) return;
    const layer = layers.find((l) => l.id === popup.layerId);
    const stillConfigured = !!layer && "popup" in layer && !!layer.popup;
    if (!stillConfigured) setPopup(null);
  }, [layers, popup]);

  const popupLayer = popup ? layers.find((l) => l.id === popup.layerId) : undefined;
  // `popup` n'est porté que par les variantes "vector"/"feature" de l'union
  // discriminée `MapLayer` — un accès défensif plutôt qu'un cast reste
  // compilable sur l'union complète (les variantes "raster"/"deck"/"tiles3d"
  // n'ont pas de champ `popup` du tout).
  const popupConfig = popupLayer && "popup" in popupLayer ? popupLayer.popup : undefined;

  // Pièces jointes et schéma de la couche du popup ouvert (chantier 4.12, D35) :
  // via ItemClient (P30.03 : délai, jeton ou lien de partage, erreurs typées).
  // `useOptionalItemClient` : MapView reste utilisable hors provider (export
  // statique) — sans client, ni pièces jointes ni formatage de schéma.
  // Placés après popupConfig/popupLayer, avant le `return` final (règles des Hooks).
  const itemClient = useOptionalItemClient();
  const popupCollectionId =
    popupLayer && (popupLayer.kind === "vector" || popupLayer.kind === "feature")
      ? popupLayer.collectionId
      : undefined;
  useEffect(() => {
    setPopupAttachments([]);
    if (!itemClient || !popupConfig?.attachmentField || popup?.fid === undefined) return;
    if (!popupCollectionId) return;
    let cancelled = false;
    // Promise.resolve().then : un ItemClient partiel (mock) sans la méthode
    // rejette ici au lieu de lever dans l'effet.
    Promise.resolve()
      .then(() =>
        itemClient.listAttachments(popupCollectionId, popup.fid!, popupConfig.attachmentField),
      )
      .then((list) => {
        if (!cancelled) setPopupAttachments(list ?? []);
      })
      .catch(() => {
        if (!cancelled) setPopupAttachments([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemClient, popup?.layerId, popup?.fid, popupConfig?.attachmentField]);

  // Schéma de la collection de la couche du popup actif (D35) : résolu par
  // `popup.layerId` seul (il ne dépend pas de l'entité cliquée).
  useEffect(() => {
    setPopupSchema([]);
    if (!itemClient || !popup || !popupCollectionId) return;
    let cancelled = false;
    Promise.resolve()
      .then(() => itemClient.getCollectionSchema(popupCollectionId))
      .then((data) => {
        if (!cancelled) setPopupSchema(data?.fields ?? []);
      })
      .catch(() => {
        if (!cancelled) setPopupSchema([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemClient, popup?.layerId]);

  async function downloadPopupAttachment(attachmentId: string, filename: string) {
    if (!itemClient || !popupCollectionId || !popup || popup.fid === undefined) return;
    try {
      const { blob } = await itemClient.downloadAttachment(
        popupCollectionId,
        popup.fid,
        attachmentId,
      );
      const objectUrl = URL.createObjectURL(blob);
      const el = document.createElement("a");
      el.href = objectUrl;
      el.download = filename;
      el.click();
      URL.revokeObjectURL(objectUrl);
    } catch {
      // Échec de téléchargement : sans effet visible, comme avant (res.ok faux).
    }
  }

  return {
    popup,
    setPopup,
    popupPoint,
    popupConfig,
    popupAttachments,
    popupSchema,
    downloadPopupAttachment,
  };
}
