// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useItemClient } from "../api/hooks";
import { t } from "../i18n";

export const WORKER_POLL_MS = 10_000;
// File « todo » plus ancienne que ça = personne ne la consomme (worker arrêté ou saturé).
export const WORKER_STALLED_AFTER_S = 60;
// REV-317 : seuil par file (une file peut être légitimement chargée un moment).
export const QUEUE_STALLED_AFTER_S = 120;

// t02-013 : état « traitement indisponible » d'un job en attente. S'appuie sur
// `GET /health` (jobsBacklog) via ItemClient ; n'interroge le cœur que tant que
// `active` (un job est réellement en attente). Un cœur récent ventile le backlog par file (`queues`) : une file > 120 s suffit.
// Sans ventilation (cœur ancien), repli sur le total global à 60 s, d'où un libellé
// volontairement hésitant (« peut-être »). Un échec de sonde ne dit rien.
export function WorkerStalledNotice({ active }: { active: boolean }) {
  const client = useItemClient();
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    if (!active) {
      setStalled(false);
      return;
    }
    let cancelled = false;
    const probe = async () => {
      try {
        const b = await client.getJobsBacklog?.();
        if (cancelled) return;
        const queues = b?.queues ? Object.values(b.queues) : null;
        setStalled(
          queues
            ? queues.some((q) => (q.oldestTodoAgeSeconds ?? 0) > QUEUE_STALLED_AFTER_S)
            : (b?.todo ?? 0) > 0 && (b?.oldestTodoAgeSeconds ?? 0) > WORKER_STALLED_AFTER_S,
        );
      } catch {
        // sonde best-effort : ne masque ni n'ajoute rien
      }
    };
    void probe();
    const id = setInterval(() => void probe(), WORKER_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [active, client]);
  if (!active || !stalled) return null;
  return (
    <p role="status" className="text-sm text-ink-muted">
      {t("common.workerStalled")}
    </p>
  );
}
