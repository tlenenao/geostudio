// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";

// Vocabulaire d'état de job partagé entre PipelineRunPanel (PipelineRunStatus
// = "queued"|"running"|"succeeded"|"failed", shell/src/api/types.ts:1150) et
// ReportRunPanel (ReportRunStatus.status = "pending"|"running"|"done"|
// "error"|"unknown", shell/src/api/types.ts:1101) : deux énumérations réelles
// distinctes, vérifiées contre le code plutôt que contre le brief de cette
// tâche, qui supposait un unique vocabulaire "pending/running/succeeded/
// failed/cancelled" absent du cœur tel quel (piège n°3, CLAUDE.md — le
// littéral d'un brief est régulièrement faux sur les interfaces réelles).
// "queued"/"pending" et "succeeded"/"done" et "failed"/"error" sont donc
// chacun des synonymes portés par deux API distinctes et reçoivent le même
// libellé ; "unknown" existe réellement côté rapports ; "cancelled" n'est
// émis par aucune API à ce jour mais reste gardé (le brief le demande
// explicitement et un futur statut d'annulation, ex. AlertRule ou un futur
// bouton d'annulation de run, pourra le réutiliser sans y retoucher).
const KNOWN_STATUSES = [
  "pending",
  "queued",
  "running",
  "succeeded",
  "done",
  "failed",
  "error",
  "cancelled",
  "unknown",
] as const;
type KnownStatus = (typeof KNOWN_STATUSES)[number];

function isKnownStatus(status: string): status is KnownStatus {
  return (KNOWN_STATUSES as readonly string[]).includes(status);
}

export function jobStatusLabel(status: string): string {
  if (!isKnownStatus(status)) return status;
  return t(`jobStatus.${status}`);
}
