// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, useSyncExternalStore } from "react";
import { onlineManager, useQueryClient } from "@tanstack/react-query";
import { CoreUnreachableError } from "../api/CoreUnreachableError";
import { t } from "../i18n";

// Période du sondage tant que des requêtes sont en échec d'injoignabilité.
export const CONNECTIVITY_POLL_MS = 5_000;

const subscribeOnline = (cb: () => void) => onlineManager.subscribe(cb);
const isOnline = () => onlineManager.isOnline();

// REV-254 : les mutations en échec d'injoignabilité partagent l'ensemble
// `failed`, préfixées pour ne jamais collisionner un queryHash (JSON).
const MUTATION_KEY_PREFIX = "mutation:";

// `reachable` : un succès réseau réel vient d'être observé — il prouve le
// retour du cœur pour TOUTES les mutations en échec (une mutation échouée
// n'est jamais rejouée par le sondage, elle ne peut pas se rétablir seule).
function nextFailed(
  prev: ReadonlySet<string>,
  key: string,
  down: boolean,
  reachable: boolean,
): ReadonlySet<string> {
  const cleared = reachable ? [...prev].filter((k) => k.startsWith(MUTATION_KEY_PREFIX)) : [];
  if (down === prev.has(key) && cleared.length === 0) return prev;
  const next = new Set(prev);
  for (const k of cleared) next.delete(k);
  if (down) next.add(key);
  else next.delete(key);
  return next;
}

// SP-B7 : bannière globale d'injoignabilité du cœur. S'appuie sur le
// QueryCache plutôt que sur navigator.onLine — un réseau local up avec un
// cœur down (ou simplement lent) n'est jamais détecté par l'événement
// navigateur, seulement par les erreurs CoreUnreachableError réellement
// vues par les queries (cf. base.ts:fetchWithTimeout).
// P22.06/08 : on suit l'ENSEMBLE des requêtes en échec d'injoignabilité (la
// bannière ne se lève que lorsqu'il est vide, pas au premier succès venu) et
// on les relance périodiquement. P22.07 : l'état hors ligne du navigateur
// (requêtes mises en pause par React Query, sans erreur) a son propre message.
// REV-254 : les mutations sont suivies aussi (MutationCache) — un POST/PUT/DELETE vers un cœur injoignable lève la bannière.
export function ConnectivityBanner() {
  const queryClient = useQueryClient();
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());
  const online = useSyncExternalStore(subscribeOnline, isOnline, () => true);

  useEffect(() => {
    const unsubscribeQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" && event.type !== "removed") return;
      const { queryHash, state } = event.query;
      const down =
        event.type === "updated" &&
        state.status === "error" &&
        state.error instanceof CoreUnreachableError;
      // Un `setQueryData` (succès `manual`) n'a touché aucun réseau.
      const reachable =
        event.type === "updated" && event.action.type === "success" && !event.action.manual;
      setFailed((prev) => nextFailed(prev, queryHash, down, reachable));
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated" && event.type !== "removed") return;
      const key = `${MUTATION_KEY_PREFIX}${event.mutation.mutationId}`;
      const down =
        event.type === "updated" &&
        event.mutation.state.status === "error" &&
        event.mutation.state.error instanceof CoreUnreachableError;
      const reachable = event.type === "updated" && event.action.type === "success";
      setFailed((prev) => nextFailed(prev, key, down, reachable));
    });
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [queryClient]);

  const unreachable = failed.size > 0;
  const mutationDown = [...failed].some((k) => k.startsWith(MUTATION_KEY_PREFIX));
  useEffect(() => {
    if (!unreachable) return;
    // Annulé dès que la bannière se lève ou au démontage. Une mutation en
    // échec n'a pas de requête à relancer : on relance alors toute requête
    // active, dont le succès prouve le retour du cœur (cf. nextFailed).
    // ponytail: sans requête active, la bannière d'une mutation attend le
    // prochain succès réseau ; ajouter une sonde /health si ça gêne.
    const id = setInterval(() => {
      void queryClient.refetchQueries({
        type: "active",
        predicate: (q) => mutationDown || q.state.error instanceof CoreUnreachableError,
      });
    }, CONNECTIVITY_POLL_MS);
    return () => clearInterval(id);
  }, [unreachable, mutationDown, queryClient]);

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
