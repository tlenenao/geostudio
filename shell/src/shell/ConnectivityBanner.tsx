// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { t } from "../i18n";

// SP-B7 : bannière globale d'injoignabilité du cœur. S'appuie sur le
// QueryCache plutôt que sur navigator.onLine — un réseau local up avec un
// cœur down (ou simplement lent) n'est jamais détecté par l'événement
// navigateur, seulement par les erreurs CoreUnreachableError réellement
// vues par les queries (cf. base.ts:fetchWithTimeout).
export function ConnectivityBanner() {
  const queryClient = useQueryClient();
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const query = event.query;
      if (query.state.status === "error" && query.state.error instanceof CoreUnreachableError) {
        setUnreachable(true);
      } else if (query.state.status === "success") {
        setUnreachable(false);
      }
    });
    return unsubscribe;
  }, [queryClient]);

  if (!unreachable) return null;
  return (
    <div role="alert" className="w-full bg-danger-soft px-4 py-2 text-center text-sm text-danger">
      {t("connectivity.unreachable")}
    </div>
  );
}
