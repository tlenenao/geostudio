// SPDX-License-Identifier: Apache-2.0
//
// La porte unique côté interface. Le cœur a la sienne — `can()` dans
// `core/app/sharing/authorization.py` — et calcule le verdict qu'on lit ici.
//
// Règle de la refonte (spec §6.5) : aucune comparaison de droits ailleurs dans
// le shell. Pas de `item.owner === me`, pas de `meQuery.data?.isAdmin === true`
// dans une page. Tout passe par `hasPermission`, `Gate` ou `capabilities.ts`.
//
// Ce n'est PAS une frontière de sécurité : le cœur refuse de toute façon. C'est
// la garantie qu'on n'affiche plus une commande qui produira un 403.

export type PermissionAction = "read" | "write" | "delete" | "share";

export type ItemPermissions = Record<PermissionAction, boolean>;

export type HasPermissions = { permissions: ItemPermissions };

/** Droits d'un objet qu'on vient de créer : on en est le propriétaire. */
export const OWNER_PERMISSIONS: ItemPermissions = {
  read: true,
  write: true,
  delete: true,
  share: true,
};

/** Droits servis par les chemins anonymes et par l'export statique. */
export const READ_ONLY_PERMISSIONS: ItemPermissions = {
  read: true,
  write: false,
  delete: false,
  share: false,
};

export function hasPermission(
  on: HasPermissions | null | undefined,
  action: PermissionAction,
): boolean {
  // Une charge utile sans permissions est un refus. Repli volontairement
  // visible : si un écran perd ses commandes, c'est que sa source n'a pas été
  // mise à jour — mieux vaut le constater que le masquer.
  return on?.permissions?.[action] === true;
}
