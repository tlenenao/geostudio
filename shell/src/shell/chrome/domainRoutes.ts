// SPDX-License-Identifier: Apache-2.0
import type { DomainId } from "../../auth/capabilities";

// Cartes/Données/Apps & sites/Automatisation n'ont pas encore de page dédiée
// (SP-30b+ les reconstruit sur TriptychLayout) : en attendant, leur entrée de
// la barre de domaines pointe vers le Catalogue pré-filtré par type
// (CatalogPage lit `?type=`, cf. Task 6) — pas une fausse promesse de
// fonctionnalité manquante, juste une réorganisation de ce qui existe déjà.
export const DOMAIN_PATHS: Record<DomainId, string> = {
  catalog: "/",
  maps: "/?type=map",
  data: "/?type=dataset",
  apps: "/?type=app",
  automation: "/?type=pipeline",
  analytics: "/analytics/sql",
  tasks: "/tasks",
  admin: "/admin/extensions",
  settings: "/settings",
};
