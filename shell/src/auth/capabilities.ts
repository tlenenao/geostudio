// SPDX-License-Identifier: Apache-2.0
//
// L'état des neuf domaines du produit, dérivé d'une source unique : le profil
// servi par `GET /me` (rôles + capacités du déploiement).
//
// Doctrine (spec §6.2) : un rôle manquant MASQUE, une capacité coupée
// VERROUILLE. Un rôle est une information sur la personne ; une capacité est
// une information sur le déploiement, qu'un administrateur doit pouvoir
// comprendre.
//
// La barre de domaines, la palette ⌘K et les onglets du volet gauche se
// calculent tous d'ici : retirer un rôle fait disparaître le domaine ET ses
// commandes, sans code supplémentaire.

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
  isAdmin: boolean;
  isAnalyst: boolean;
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
  /** Absent = ouvert à tous. Présent et non satisfait = domaine MASQUÉ. */
  requiresRole?: "admin" | "analyst";
  /** Absent = pas de dépendance. Présent et coupé = domaine VERROUILLÉ. */
  requiresCapability?: keyof InstanceCapabilities;
};

// L'ordre de ce tableau est l'ordre d'affichage de la barre de domaines.
export const DOMAINS: readonly DomainDef[] = [
  { id: "catalog", labelKey: "domain.catalog" },
  { id: "maps", labelKey: "domain.maps" },
  { id: "data", labelKey: "domain.data" },
  { id: "apps", labelKey: "domain.apps" },
  { id: "automation", labelKey: "domain.automation", requiresCapability: "etlEnabled" },
  { id: "analytics", labelKey: "domain.analytics", requiresRole: "analyst" },
  { id: "tasks", labelKey: "domain.tasks" },
  { id: "admin", labelKey: "domain.admin", requiresRole: "admin" },
  { id: "settings", labelKey: "domain.settings" },
] as const;

export function domainState(domain: DomainDef, profile: Profile): DomainState {
  // Le rôle est évalué EN PREMIER : sinon un non-admin/non-analyste
  // apprendrait l'existence d'un domaine par le verrou qu'on lui montrerait.
  if (domain.requiresRole === "admin" && !profile.isAdmin) return "hidden";
  if (domain.requiresRole === "analyst" && !profile.isAnalyst) return "hidden";
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
