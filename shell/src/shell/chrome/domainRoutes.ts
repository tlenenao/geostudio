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

// Plusieurs domaines (Cartes/Données/Apps & sites/Automatisation) pointent
// tous vers "/" avec un ?type= différent (Task 6) : comparer seulement le
// pathname les ferait paraître actifs tous en même temps. Comparer aussi la
// recherche pour ceux dont le chemin en porte une ; pour les autres (dont
// Catalogue, "/" sans ?type=), comparer le pathname ET exiger une recherche
// vide — sinon Catalogue ("/") paraîtrait actif même sur "/?type=map", qui
// partage le même pathname.
//
// Utiliser cette fonction avec `Link`, jamais `NavLink` : `NavLink` calcule
// sa PROPRE notion d'« actif » à partir du seul pathname de `to` (la query
// est perdue par `useResolvedPath`), et sa déstructuration par défaut
// réinjecte "page" dès qu'on lui passe `aria-current: undefined` —
// impossible d'annuler son `aria-current`/`className` internes depuis
// l'extérieur. Vérifié empiriquement : `NavLink` marquait Catalogue actif sur
// "/?type=map" malgré un `aria-current` explicite à `undefined`.
export function isDomainActive(path: string, location: { pathname: string; search: string }) {
  const currentHref = location.pathname + location.search;
  return path.includes("?")
    ? currentHref === path
    : location.pathname === path && location.search === "";
}
