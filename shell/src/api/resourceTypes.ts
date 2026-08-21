// SPDX-License-Identifier: Apache-2.0
import type { ResourceType } from "./types";

// Source unique des libellés de type de ressource, lue par le filtre du
// catalogue (CatalogPage) ET par la pastille des cartes d'item (ItemCard).
//
// Le type est `Record<ResourceType, string>` et NON `Partial<Record<…>>` :
// c'est ce qui donne le critère de sortie du chantier 4.6 (« aucun type de
// ResourceType n'est absent du sélecteur »). Ajouter un 13e type à
// ResourceType casse la compilation tant qu'il n'a pas son libellé ici —
// même argument d'exhaustivité prouvée par le typage que StaticItemClient
// (SP-18a).
export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  app: "App",
  dashboard: "Dashboard",
  map: "Carte",
  site: "Site",
  dataset: "Dataset",
  bookmark: "Vue enregistrée",
  pipeline: "Pipeline",
  alert: "Alerte",
  report: "Rapport",
  tileset3d: "Tuiles 3D",
  terrain3d: "Terrain 3D",
  external: "Externe",
};

// Ordre d'affichage dans le filtre : les objets que l'on crée le plus
// souvent d'abord, les objets techniques et moissonnés ensuite.
export const RESOURCE_TYPE_ORDER: ResourceType[] = [
  "app",
  "dashboard",
  "map",
  "site",
  "dataset",
  "bookmark",
  "pipeline",
  "alert",
  "report",
  "tileset3d",
  "terrain3d",
  "external",
];
