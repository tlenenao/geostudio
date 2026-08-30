// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { hasPermission, type HasPermissions, type PermissionAction } from "./permissions";

export function Gate({
  on,
  can,
  children,
  fallback = null,
}: {
  on: HasPermissions | null | undefined;
  can: PermissionAction;
  children: ReactNode;
  /**
   * Rendu quand le droit est refusé. `null` (défaut) = traitement « absent ».
   * Passer un `<Locked reason="…">` = traitement « verrouillé et expliqué ».
   * Les deux traitements de la doctrine (spec §6.2) sont donc exprimés ici,
   * et le choix est fait par l'appelant, qui seul sait si l'utilisateur peut
   * légitimement se demander pourquoi.
   */
  fallback?: ReactNode;
}): ReactNode {
  return hasPermission(on, can) ? children : fallback;
}
