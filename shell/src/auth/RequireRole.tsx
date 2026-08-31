// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { useMe } from "../api/hooks";

/**
 * Porte de rôle au niveau route (spec design SP-30 §6.5 : « meQuery.data?.
 * isAdmin === true et consorts disparaissent des pages » — neuf occurrences
 * comptées dans cinq fichiers). La comparaison vit ici, testée une seule
 * fois — pendant côté rôles d'instance de `Gate`/`hasPermission` côté
 * permissions d'item.
 */
export function RequireRole({
  role,
  deniedMessage,
  children,
}: {
  role: "admin" | "analyst";
  deniedMessage: string;
  children: ReactNode;
}): ReactNode {
  const meQuery = useMe();
  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  const allowed =
    role === "admin" ? meQuery.data?.isAdmin === true : meQuery.data?.isAnalyst === true;
  if (!allowed) {
    return (
      <p role="alert" className="text-sm text-danger">
        {deniedMessage}
      </p>
    );
  }
  return children;
}
