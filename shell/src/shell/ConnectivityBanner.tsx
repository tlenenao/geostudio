// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, useSyncExternalStore } from "react";
import { onlineManager, useQueryClient } from "@tanstack/react-query";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { t } from "../i18n";

// Période du sondage tant que des requêtes sont en échec d'injoignabilité.
export const CONNECTIVITY_POLL_MS = 5_000;

const subscribeOnline = (cb: () => void) => onlineManager.subscribe(cb);
const isOnline = () => onlineManager.isOnline();

// SP-B7 : bannière globale d'injoignabilité du cœur. S'appuie sur le
// QueryCache plutôt que sur navigator.onLine — un réseau local up avec un
// cœur down (ou simplement lent) n'est jamais détecté par l'événement
// navigateur, seulement par les erreurs CoreUnreachableError réellement
// vues par les queries (cf. base.ts:fetchWithTimeout).
// P22.06/08 : on suit l'ENSEMBLE des requêtes en échec d'injoignabilité (la
// bannière ne se lève que lorsqu'il est vide, pas au premier succès venu) et
// on les relance périodiquement. P22.07 : l'état hors ligne du navigateur
// (requêtes mises en pause par React Query, sans erreur) a son propre message.
export function ConnectivityBanner() {
  const queryClient = useQueryClient();
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());
  const online = useSyncExternalStore(subscribeOnline, isOnline, () => true);

  useEffect(() => {
    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" && event.type !== "removed") return;
      const { queryHash, state } = event.query;
      const down =
        event.type === "updated" &&
        state.status === "error" &&
        state.error instanceof CoreUnreachableError;
      setFailed((prev) => {
        if (down === prev.has(queryHash)) return prev;
        const next = new Set(prev);
        if (down) next.add(queryHash);
        else next.delete(queryHash);
        return next;
      });
    });
  }, [queryClient]);

  const unreachable = failed.size > 0;
  useEffect(() => {
    if (!unreachable) return;
    // Annulé dès que la bannière se lève ou au démontage.
    const id = setInterval(() => {
      void queryClient.refetchQueries({
        type: "active",
        predicate: (q) => q.state.error instanceof CoreUnreachableError,
      });
    }, CONNECTIVITY_POLL_MS);
    return () => clearInterval(id);
  }, [unreachable, queryClient]);

  if (!online) {
    return (
      <div role="alert" className="w-full bg-danger-soft px-4 py-2 text-center text-sm text-danger">
        {t("connectivity.offline")}
      </div>
    );
  }
  if (!unreachable) return null;
  return (
    <div role="alert" className="w-full bg-danger-soft px-4 py-2 text-center text-sm text-danger">
      {t("connectivity.unreachable")}
    </div>
  );
}
