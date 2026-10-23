// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useActiveExtensions } from "../../api/hooks";
import type { ExtensionManifest } from "../../api/types";
import { getWidget, unregisterWidget } from "../registry";
import { registerExtensionWidget } from "./registerExtensionWidget";

// type -> signature du manifeste enregistré : permet de ne ré-enregistrer que ce qui a changé
// (pas de `console.warn` d'écrasement) et de retirer les types disparus (AUD-109 #9).
const registered = new Map<string, string>();

export function reconcileExtensions(manifests: ExtensionManifest[]): void {
  const active = new Set(manifests.map((m) => m.type));
  for (const type of [...registered.keys()]) {
    if (!active.has(type)) {
      unregisterWidget(type);
      registered.delete(type);
    }
  }
  for (const manifest of manifests) {
    const signature = JSON.stringify(manifest);
    if (registered.get(manifest.type) === signature && getWidget(manifest.type)) continue;
    // Mise à jour d'un manifeste déjà enregistré : on retire d'abord, sans avertissement.
    if (registered.has(manifest.type)) unregisterWidget(manifest.type);
    registerExtensionWidget(manifest);
    registered.set(manifest.type, signature);
  }
}

/** Enregistre les widgets d'extension actifs (AUD-107 : une seule logique pour toutes les
 *  surfaces, publiques comprises). Renvoie true une fois la liste résolue — ou en erreur
 *  (fail-open : un `/extensions` en échec ne bloque jamais la page). */
export function useRegisterExtensions(): boolean {
  const query = useActiveExtensions();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (query.isLoading) return;
    reconcileExtensions(query.data ?? []);
    setReady(true);
  }, [query.isLoading, query.data]);
  return ready;
}

export function _resetRegisteredExtensions(): void {
  registered.clear();
}
