// SPDX-License-Identifier: Apache-2.0
import { useUrlSyncedState } from "./useUrlSyncedState";

// REV-323 (lot C) : onglet actif d'un TriptychLayout (étroit/medium) porté par
// `?tab=` — survit au rechargement et au lien partagé. Une valeur inconnue est
// ignorée par TriptychLayout (retombe sur l'onglet de travail).
// À étaler sur <TriptychLayout {...useUrlTab("canvas")} />.
export function useUrlTab(defaultTabId: string) {
  const [tab, setTab] = useUrlSyncedState<string>("tab", defaultTabId);
  return { activeTabId: tab ?? defaultTabId, onActiveTabChange: setTab };
}
