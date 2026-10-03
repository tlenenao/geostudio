// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
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
// Glossaire arrêté (P34.18) : Application / Tableau de bord / Carte / Jeu de données.
export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  app: t("resourceType.app"),
  dashboard: t("resourceType.dashboard"),
  map: t("resourceType.map"),
  site: t("resourceType.site"),
  dataset: t("resourceType.dataset"),
  bookmark: t("resourceType.bookmark"),
  pipeline: t("resourceType.pipeline"),
  alert: t("resourceType.alert"),
  report: t("resourceType.report"),
  tileset3d: t("resourceType.tileset3d"),
  terrain3d: t("resourceType.terrain3d"),
  external: t("resourceType.external"),
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
