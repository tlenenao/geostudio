// SPDX-License-Identifier: Apache-2.0
// L8 : pastille de la barre du haut : saisies en attente d'envoi (annoncée aux lecteurs d'écran),
// et reprise de la synchro après un 401.
import { t, plural } from "../i18n";
import { useOutbox } from "./useOutbox";
import "../i18n/domains/misc";

export function SyncStatusPill() {
  const api = useOutbox();
  const pending = api?.pending ?? 0;
  const paused = api?.paused === "auth";
  const conflicts = api?.entries.filter((e) => e.state === "conflict").length ?? 0;
  // `aria-live` posé sur un conteneur toujours monté : l'annonce vient du changement de texte.
  return (
    <span aria-live="polite" className="text-xs text-ink-2">
      {pending > 0 && (
        <button
          type="button"
          className="rounded-md border border-rule px-2 py-1 hover:bg-sunken"
          onClick={paused ? api!.resume : api!.syncNow}
        >
          {t(plural(pending, "outbox.pillOne", "outbox.pillMany"), { count: pending })}
          {paused ? ` – ${t("outbox.resume")}` : ""}
        </button>
      )}
      {pending === 0 && conflicts > 0 && (
        <span className="text-danger">
          {t(plural(conflicts, "outbox.conflictOne", "outbox.conflictMany"), { count: conflicts })}
        </span>
      )}
    </span>
  );
}
