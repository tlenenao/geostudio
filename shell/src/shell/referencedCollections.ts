// SPDX-License-Identifier: Apache-2.0
import { useAppConfig, useMapConfig } from "../api/hooks";
import type { Item } from "../api/types";

/** Identifiants des collections que la config d'une carte/app/dashboard lit
 *  (couches vectorielles de carte, sources `features` d'app). Les sources
 *  passant par un dataset (`datasetId`) sont des items à part, hors de ce
 *  calcul. Sert aux avertissements de partage/publication (j13-008, j03-012) :
 *  partager ou publier la config ne partage pas les données qu'elle lit. */
export function useReferencedCollectionIds(item: Item, enabled = true): string[] {
  const isMap = item.resourceType === "map";
  const isApp = item.resourceType === "app" || item.resourceType === "dashboard";
  const map = useMapConfig(item.pk, { enabled: enabled && isMap });
  const app = useAppConfig(item.pk, { enabled: enabled && isApp });
  const ids = new Set<string>();
  for (const layer of map.data?.layers ?? []) {
    if (layer.kind === "vector" && layer.collectionId) ids.add(layer.collectionId);
  }
  for (const ds of app.data?.dataSources ?? []) {
    if (ds.type !== "static" && !ds.datasetId && ds.layer) ids.add(ds.layer);
  }
  return [...ids];
}
