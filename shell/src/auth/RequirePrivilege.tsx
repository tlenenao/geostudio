// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { useMe } from "../api/hooks";
import { holdsAnyPrivilege } from "./holdsAnyPrivilege";

/**
 * Porte de privilège au niveau route — pendant côté privilèges de rôle de
 * `Gate`/`hasPermission` côté permissions d'objet. Remplace `RequireRole`
 * (SP-30, design §6.5) : la comparaison de droits vit ici, testée une seule
 * fois.
 */
export function RequirePrivilege({
  privilege,
  deniedMessage,
  children,
}: {
  /** Un privilège, ou une liste dont UN SEUL suffit. */
  privilege: string | readonly string[];
  deniedMessage: string;
  children: ReactNode;
}): ReactNode {
  const meQuery = useMe();
  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  const allowed = holdsAnyPrivilege(meQuery.data?.privileges ?? [], privilege);
  if (!allowed) {
    return (
      <p role="alert" className="text-sm text-danger">
        {deniedMessage}
      </p>
    );
  }
  return children;
}
