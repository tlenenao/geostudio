// SPDX-License-Identifier: Apache-2.0
import type { DomainId, Profile } from "../../auth/capabilities";

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

// SP-42/F-securite-autorisation-08(b) : le domaine "admin" (capabilities.ts)
// se montre dès qu'un seul des six privilèges admin.* est détenu, mais
// DOMAIN_PATHS.admin ci-dessus pointe toujours vers /admin/extensions, gardé
// côté route (routes.tsx) par admin.extensions.manage seul — un rôle sur
// mesure ne portant qu'un autre privilège admin (ex. admin.users.manage)
// voyait le domaine et atterrissait sur un refus. Priorité de résolution
// calée sur l'ancien défaut (extensions en tête, pour ne rien changer au
// cas déjà correct — admin complet ou porteur d'extensions.manage) puis les
// cinq autres routes /admin/* réellement montées (routes.tsx) ; un profil ne
// portant que admin.secrets.manage (aucune page /admin/* dédiée, seulement
// des routes /secrets consommées depuis le pipeline builder) retombe sur ce
// même défaut — résidu assumé, hors du scénario falsifié par ce correctif.
const ADMIN_DESTINATIONS: readonly { privilege: string; path: string }[] = [
  { privilege: "admin.extensions.manage", path: "/admin/extensions" },
  { privilege: "admin.collections.manage", path: "/admin/collections" },
  { privilege: "admin.harvest.manage", path: "/admin/harvest" },
  { privilege: "admin.roles.manage", path: "/admin/roles" },
  { privilege: "admin.users.manage", path: "/admin/users" },
];

/**
 * Chemin réel de la destination d'un domaine pour ce profil — à utiliser à
 * la place de `DOMAIN_PATHS[domain]` partout où un profil est disponible
 * (DomainBar/BottomNav). Seul le domaine "admin" varie selon le profil ;
 * tous les autres renvoient leur entrée statique de `DOMAIN_PATHS`.
 */
export function getDomainPath(domain: DomainId, profile: Profile): string {
  if (domain === "admin") {
    const reachable = ADMIN_DESTINATIONS.find((d) => profile.privileges.has(d.privilege));
    if (reachable) return reachable.path;
  }
  return DOMAIN_PATHS[domain];
}

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
