// SPDX-License-Identifier: Apache-2.0
//
// L'état des neuf domaines du produit, dérivé d'une source unique : le profil
// servi par `GET /me` (privilèges du rôle + capacités du déploiement).
//
// Doctrine (spec §6.2) : un privilège manquant MASQUE, une capacité coupée
// VERROUILLE. Un privilège est une propriété de la personne (via son rôle) ;
// une capacité est une propriété du déploiement, qu'un administrateur doit
// pouvoir comprendre.
//
// La barre de domaines, la palette ⌘K et les onglets du volet gauche se
// calculent tous d'ici : retirer un privilège d'un rôle fait disparaître le
// domaine ET ses commandes, sans code supplémentaire.

import type { MessageKey } from "../i18n";

export type InstanceCapabilities = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
};

export type Profile = {
  privileges: Set<string>;
  capabilities: InstanceCapabilities;
};

export type DomainId =
  | "catalog"
  | "maps"
  | "data"
  | "apps"
  | "automation"
  | "analytics"
  | "tasks"
  | "admin"
  | "settings";

export type DomainState = "visible" | "locked" | "hidden";

export type DomainDef = {
  id: DomainId;
  labelKey: MessageKey;
  /** Absent = ouvert à tous. Un tableau = « au moins un » suffit. Présent et
   * non satisfait = domaine MASQUÉ. */
  requiresPrivilege?: string | string[];
  /** Absent = pas de dépendance. Présent et coupé = domaine VERROUILLÉ. */
  requiresCapability?: keyof InstanceCapabilities;
};

// L'ordre de ce tableau est l'ordre d'affichage de la barre de domaines.
export const DOMAINS: readonly DomainDef[] = [
  { id: "catalog", labelKey: "domain.catalog" },
  // SP-42/F-shell-pages-03 : seul domaine de contenu (hors catalog/settings,
  // ouverts par conception) qui n'exigeait aucun privilège, alors que
  // maps.manage existe et distingue déjà Créateur (l'a) de Lecteur (ne l'a
  // pas) — par symétrie avec data/apps ci-dessous.
  { id: "maps", labelKey: "domain.maps", requiresPrivilege: "maps.manage" },
  { id: "data", labelKey: "domain.data", requiresPrivilege: "data.view" },
  { id: "apps", labelKey: "domain.apps", requiresPrivilege: "apps.manage" },
  {
    id: "automation",
    labelKey: "domain.automation",
    requiresPrivilege: "automation.manage",
    requiresCapability: "etlEnabled",
  },
  // SP-42/F-securite-autorisation-08(a) : gaté sur analytics.sql_lab.access,
  // pas analytics.view — /analytics/sql (RequirePrivilege du même nom,
  // routes.tsx) est aujourd'hui l'unique destination de ce domaine ; un
  // Créateur (analytics.view sans sql_lab.access) verrait sinon un domaine
  // qui refuse systématiquement sa seule destination. Si un écran
  // analytics.view-seul existe un jour, ce gate devra être revu en même
  // temps que DOMAIN_PATHS.analytics (domainRoutes.ts).
  { id: "analytics", labelKey: "domain.analytics", requiresPrivilege: "analytics.sql_lab.access" },
  { id: "tasks", labelKey: "domain.tasks", requiresPrivilege: "tasks.view" },
  {
    id: "admin",
    labelKey: "domain.admin",
    requiresPrivilege: [
      "admin.users.manage",
      "admin.roles.manage",
      "admin.harvest.manage",
      "admin.collections.manage",
      "admin.extensions.manage",
      "admin.secrets.manage",
    ],
  },
  { id: "settings", labelKey: "domain.settings" },
] as const;

function hasRequiredPrivilege(domain: DomainDef, profile: Profile): boolean {
  if (domain.requiresPrivilege === undefined) return true;
  const required = Array.isArray(domain.requiresPrivilege)
    ? domain.requiresPrivilege
    : [domain.requiresPrivilege];
  return required.some((p) => profile.privileges.has(p));
}

export function domainState(domain: DomainDef, profile: Profile): DomainState {
  // Le privilège est évalué EN PREMIER : sinon quelqu'un qui ne l'a pas
  // apprendrait l'existence d'un domaine par le verrou qu'on lui montrerait.
  if (!hasRequiredPrivilege(domain, profile)) return "hidden";
  if (domain.requiresCapability && !profile.capabilities[domain.requiresCapability]) {
    return "locked";
  }
  return "visible";
}

export function navigableDomains(
  profile: Profile,
): { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] {
  const out: { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] = [];
  for (const domain of DOMAINS) {
    const state = domainState(domain, profile);
    if (state !== "hidden") out.push({ domain, state });
  }
  return out;
}
