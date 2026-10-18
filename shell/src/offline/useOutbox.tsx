// SPDX-License-Identifier: Apache-2.0
// L8 : la file de saisies côté React. `useOutboxEngine` pilote un moteur de synchro pour un
// propriétaire ; `OutboxProvider` le monte pour l'utilisateur connecté (transport privé).
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useItemClient } from "../api/ItemClientProvider";
import { useMe } from "../api/domains/identity.hooks";
import type { OutboxEntry } from "./db";
import { deleteEntry, enqueue, listEntries, type NewEntry } from "./outbox";
import { createSyncEngine, type SyncEngine, type SyncTransport } from "./sync";
import { privateTransport } from "./transport";

const ACTIVE = new Set(["queued", "sending", "needs_photos"]);

/** Saisies non envoyées (hors `sent`) : lisible hors du provider (bannière de connectivité). */
let unsent = 0;
const listeners = new Set<() => void>();
function setUnsent(n: number) {
  if (n === unsent) return;
  unsent = n;
  listeners.forEach((l) => l());
}
/** Réservé aux tests (le décompte vient normalement du moteur). */
export const setUnsentForTests = setUnsent;
export function useUnsentCount(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => unsent,
    () => 0,
  );
}

export type OutboxApi = {
  ownerKey: string;
  entries: OutboxEntry[];
  /** Saisies encore à envoyer (en file, en cours, photos à finir). */
  pending: number;
  /** `auth` : un 401 a suspendu la synchro ; `resume()` la relance après renouvellement du jeton. */
  paused: "auth" | null;
  /** Met en file ; rejette `OutboxLimitError`/`OutboxStorageError` (rien n'est alors écrit). */
  enqueue(entry: NewEntry, now?: number): Promise<void>;
  syncNow(): void;
  resume(): void;
  /** Abandon d'une saisie (et de ses fichiers). */
  remove(opId: string): Promise<void>;
};

export function useOutboxEngine(
  ownerKey: string | null,
  transport: SyncTransport | null,
  onAuthRequired?: () => void,
): OutboxApi | null {
  const [entries, setEntries] = useState<OutboxEntry[]>([]);
  const [paused, setPaused] = useState<"auth" | null>(null);
  const engine = useRef<SyncEngine | null>(null);
  const authCb = useRef(onAuthRequired);
  authCb.current = onAuthRequired;

  const refresh = useCallback(async () => {
    if (!ownerKey) return;
    try {
      const rows = await listEntries(ownerKey);
      setEntries(rows);
      setUnsent(rows.filter((e) => e.state !== "sent").length);
    } catch {
      // IndexedDB indisponible : la file est vide du point de vue de l'écran.
    }
  }, [ownerKey]);

  useEffect(() => {
    if (!ownerKey || !transport) return;
    const e = createSyncEngine({
      ownerKey,
      transport,
      onChange: (s) => {
        setPaused(s.paused);
        void refresh();
      },
      onAuthRequired: () => authCb.current?.(),
    });
    engine.current = e;
    void refresh();
    e.start();
    return () => {
      e.stop();
      engine.current = null;
    };
  }, [ownerKey, transport, refresh]);

  return useMemo(() => {
    if (!ownerKey) return null;
    return {
      ownerKey,
      entries,
      pending: entries.filter((e) => ACTIVE.has(e.state)).length,
      paused,
      async enqueue(entry, now) {
        await enqueue(ownerKey, entry, now);
        await refresh();
        void engine.current?.syncNow();
      },
      syncNow: () => void engine.current?.syncNow(),
      resume: () => void engine.current?.resume(),
      async remove(opId) {
        await deleteEntry(ownerKey, opId);
        await refresh();
      },
    };
  }, [ownerKey, entries, paused, refresh]);
}

const OutboxContext = createContext<OutboxApi | null>(null);

/** `null` hors provider ou sans utilisateur identifié : aucune mise en file (comportement d'avant). */
export function useOutbox(): OutboxApi | null {
  return useContext(OutboxContext);
}

const LAST_KEY = "gs-collect-owner";
function lastOwnerKey(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

export function OutboxProvider({
  children,
  onAuthRequired,
}: {
  children: ReactNode;
  onAuthRequired?: () => void;
}) {
  const client = useItemClient();
  const me = useMe();
  const fresh = me.data ? `${me.data.tenantId}:${me.data.id}` : null;
  useEffect(() => {
    if (!fresh) return;
    try {
      localStorage.setItem(LAST_KEY, fresh);
    } catch {
      // stockage refusé : on perd seulement le rechargement hors-ligne.
    }
  }, [fresh]);
  // Hors-ligne au rechargement, `me` échoue : on garde le dernier propriétaire connu pour que la
  // file reste visible. ponytail: le dernier propriétaire d'un poste partagé ; le serveur reste
  // juge à l'envoi (jeton), et `me` rétablit la bonne clé dès que le réseau revient.
  const ownerKey = fresh ?? (me.isError ? lastOwnerKey() : null);
  const transport = useMemo(() => privateTransport(client), [client]);
  const api = useOutboxEngine(ownerKey, transport, onAuthRequired);
  return <OutboxContext.Provider value={api}>{children}</OutboxContext.Provider>;
}

export { OutboxContext };
