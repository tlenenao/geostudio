// SPDX-License-Identifier: Apache-2.0
// L8 : « Mes saisies hors-ligne » : état de chaque saisie en file et ses actions (spec §5).
import { useState } from "react";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { formatDateTime } from "../lib/format";
import { t } from "../i18n";
import type { OutboxEntry } from "./db";
import type { OutboxApi } from "./useOutbox";
import "../i18n/domains/misc";

const STATE_LABEL: Record<OutboxEntry["state"], () => string> = {
  queued: () => t("outbox.stateQueued"),
  sending: () => t("outbox.stateSending"),
  needs_photos: () => t("outbox.stateNeedsPhotos"),
  sent: () => t("outbox.stateSent"),
  conflict: () => t("outbox.stateConflict"),
  failed_permanent: () => t("outbox.stateFailedPermanent"),
};

const REASON_LABEL: Record<string, () => string> = {
  network: () => t("outbox.reasonNetwork"),
  server: () => t("outbox.reasonServer"),
  rate_limited: () => t("outbox.reasonRateLimited"),
  pow: () => t("outbox.reasonPow"),
  busy: () => t("outbox.reasonBusy"),
  forbidden: () => t("outbox.reasonForbidden"),
  gone: () => t("outbox.reasonGone"),
  invalid: () => t("outbox.reasonInvalid"),
  unique: () => t("outbox.reasonUnique"),
  quota: () => t("outbox.reasonQuota"),
};

const BAD = new Set(["conflict", "failed_permanent"]);

function exportJson(entry: OutboxEntry) {
  const blob = new Blob([JSON.stringify(entry.payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `saisie-${entry.opId.slice(0, 8)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function OutboxList({
  api,
  collectionId,
  onEdit,
}: {
  api: OutboxApi;
  /** Limite l'affichage à une collection (formulaire d'app) ; absent : toutes. */
  collectionId?: string;
  /** Rouvre la saisie dans le formulaire (si elle n'a pas encore de fiche côté serveur). */
  onEdit?: (entry: OutboxEntry) => void;
}) {
  const [abandoning, setAbandoning] = useState<OutboxEntry | null>(null);
  const rows = api.entries
    .filter((e) => collectionId === undefined || e.collectionId === collectionId)
    .sort((a, b) => b.createdAt - a.createdAt);
  if (rows.length === 0) return null;
  const waiting = rows.some((e) => e.state === "queued" || e.state === "needs_photos");
  return (
    <section aria-label={t("outbox.title")} className="flex flex-col gap-2 text-sm">
      <h3 className="font-semibold">{t("outbox.title")}</h3>
      {api.paused === "auth" && (
        <p role="alert" className="text-xs text-danger">
          {t("outbox.pausedAuth")}{" "}
          <button type="button" className="underline" onClick={api.resume}>
            {t("outbox.resume")}
          </button>
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {rows.map((e) => {
          const bad = BAD.has(e.state);
          const reason = e.lastError ? (REASON_LABEL[e.lastError]?.() ?? e.lastError) : null;
          const editable = !e.serverFid && e.state !== "sent" && e.state !== "sending";
          return (
            <li key={e.opId} className="rounded border border-rule p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className={bad ? "font-medium text-danger" : "font-medium"}>
                  {STATE_LABEL[e.state]()}
                </span>
                <span className="text-xs text-ink-2">{formatDateTime(e.createdAt)}</span>
                {reason && e.state !== "sent" && (
                  <span className="text-xs text-ink-2">{reason}</span>
                )}
              </div>
              {e.fieldErrors && e.fieldErrors.length > 0 && (
                <ul className="mt-1 list-disc pl-4 text-xs text-danger">
                  {e.fieldErrors.map((f) => (
                    <li key={`${f.field}-${f.code}`}>{`${f.field} : ${f.message}`}</li>
                  ))}
                </ul>
              )}
              {e.lastDetail && (
                <details className="mt-1 text-xs">
                  <summary>{t("outbox.details")}</summary>
                  <pre className="whitespace-pre-wrap break-words">{e.lastDetail}</pre>
                </details>
              )}
              {e.state !== "sent" && (
                <div className="mt-1 flex flex-wrap gap-2 text-xs">
                  {editable && onEdit && (
                    <button type="button" className="underline" onClick={() => onEdit(e)}>
                      {t("outbox.edit")}
                    </button>
                  )}
                  {bad && (
                    <button type="button" className="underline" onClick={() => exportJson(e)}>
                      {t("outbox.export")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-danger underline"
                    onClick={() => setAbandoning(e)}
                  >
                    {t("outbox.abandon")}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {waiting && (
        <div>
          <button
            type="button"
            className="rounded border border-rule px-3 py-1.5 text-xs"
            onClick={api.syncNow}
          >
            {t("outbox.syncNow")}
          </button>
        </div>
      )}
      <ConfirmDialog
        open={abandoning !== null}
        title={t("outbox.abandonTitle")}
        message={t("outbox.abandonMessage")}
        confirmLabel={t("outbox.abandon")}
        onCancel={() => setAbandoning(null)}
        onConfirm={() => {
          const target = abandoning;
          setAbandoning(null);
          if (target) void api.remove(target.opId);
        }}
      />
    </section>
  );
}
