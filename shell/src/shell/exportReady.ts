// SPDX-License-Identifier: Apache-2.0
import { useEffect, useSyncExternalStore } from "react";
import { useIsFetching } from "@tanstack/react-query";

// DOM signal the Playwright export worker (core/app/export/jobs.py) waits
// for via page.wait_for_selector('[data-export-ready="true"]', state="attached")
// before capturing a screenshot/PDF. Setting `document.body.dataset.exportReady`
// to the string "true" is what produces the HTML attribute
// data-export-ready="true" that selector matches — do not change the target
// element, attribute name, or value without updating Task 6's worker too.
// Idempotent: safe to call more than once (e.g. a MapView "idle" firing
// again after the first capture-ready moment).
export function markExportReady(): void {
  document.body.dataset.exportReady = "true";
}

// AUD-001 : fenêtre de stabilité avant de lever le signal (laisse les widgets
// montés par le rendu suivant démarrer leurs requêtes) et garde-fou de
// durée, inférieur au budget de rendu du worker (RENDER_TIMEOUT_MS = 120 s).
export const EXPORT_SETTLE_MS = 300;
export const EXPORT_TIMEOUT_MS = 90_000;

// Tâches de rendu hors React Query (ex. MapLibre « idle » d'un widget carte).
let pendingTasks = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function trackExportTask(): () => void {
  pendingTasks += 1;
  emit();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    pendingTasks -= 1;
    emit();
  };
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};
const getPending = () => pendingTasks;

// Lève `data-export-ready` quand l'app est chargée (`baseReady`), qu'aucune
// requête React Query n'est en vol et qu'aucune tâche suivie n'est ouverte,
// de façon stable pendant EXPORT_SETTLE_MS. Au-delà d'EXPORT_TIMEOUT_MS,
// capture quand même (mieux qu'un export qui expire) mais marque
// `data-export-incomplete="true"` au lieu de masquer le vide en silence.
export function useExportReadiness(baseReady: boolean): void {
  const fetching = useIsFetching();
  const tasks = useSyncExternalStore(subscribe, getPending, getPending);
  const settled = baseReady && fetching === 0 && tasks === 0;

  useEffect(() => {
    if (!settled) return;
    const id = setTimeout(markExportReady, EXPORT_SETTLE_MS);
    return () => clearTimeout(id);
  }, [settled]);

  useEffect(() => {
    if (!baseReady) return;
    const id = setTimeout(() => {
      document.body.dataset.exportIncomplete = "true";
      markExportReady();
    }, EXPORT_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, [baseReady]);
}
