// SPDX-License-Identifier: Apache-2.0
import { hasPermission, type HasPermissions } from "../auth/permissions";

/** Destination d'« Ouvrir » pour les types qui s'ouvrent dans un éditeur.
 * Sans droit d'écriture (lecteur), une app/un tableau de bord/un site s'ouvre
 * en mode usage `/apps/:pk`, pas dans le builder (P35.02). */
export function editorPath(pk: string, type: string, item?: HasPermissions | null): string {
  if (type === "map") return `/maps/${pk}`;
  if (type === "dataset") return `/datasets/${pk}/edit`;
  if (item && !hasPermission(item, "write")) return `/apps/${pk}`;
  return `/apps/${pk}/edit`;
}
