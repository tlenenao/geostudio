// SPDX-License-Identifier: Apache-2.0
// L8 : table de décision pure du moteur de synchronisation (spec §4.3) — que faire d'une saisie
// dont l'envoi vient d'échouer. Aucune E/S : testée ligne par ligne.
import { ApiError } from "../api/ApiError";
import { FeatureValidationError } from "../api/base";
import type { FieldProblem } from "./db";

export const BACKOFF_BASE_MS = 5_000;
export const BACKOFF_MAX_MS = 15 * 60_000;

/** Raison affichée à l'utilisateur (traduite côté UI) ; `network`/`server`/`rate_limited` = retry. */
export type FailureReason =
  | "network"
  | "server"
  | "rate_limited"
  | "pow"
  | "busy"
  | "forbidden"
  | "gone"
  | "invalid"
  | "unique"
  | "quota"
  | "other";

export type Decision =
  | { action: "retry"; delayMs: number; reason: FailureReason; detail?: string }
  | { action: "pause_auth" }
  | {
      action: "conflict";
      reason: FailureReason;
      detail?: string;
      errors?: FieldProblem[];
    }
  | { action: "failed_permanent"; reason: FailureReason; detail?: string };

/** 5 s, 10 s, 20 s… plafonné à 15 min ; `Retry-After` (secondes) fait plancher le délai. */
export function backoffMs(attempts: number, retryAfterSec?: number): number {
  const exp = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** Math.max(0, attempts));
  const floor = retryAfterSec !== undefined ? retryAfterSec * 1000 : 0;
  return Math.min(Math.max(exp, floor), Math.max(BACKOFF_MAX_MS, floor));
}

export function decide(err: unknown, attempts: number): Decision {
  if (err instanceof FeatureValidationError) {
    return { action: "conflict", reason: "invalid", errors: err.errors };
  }
  if (!(err instanceof ApiError)) {
    // Réseau coupé (CoreUnreachableError, TypeError de fetch), PUT S3 refusé… : on réessaiera.
    return { action: "retry", delayMs: backoffMs(attempts), reason: "network" };
  }
  const { status, detail } = err;
  const retry = (reason: FailureReason, retryAfter?: number): Decision => ({
    action: "retry",
    delayMs: backoffMs(attempts, retryAfter),
    reason,
    detail,
  });
  if (status === 401) return { action: "pause_auth" };
  if (status === 403) {
    // Défi de preuve de travail périmé ou refusé (page publique) : un nouveau défi suffit.
    if (/proof of work/i.test(detail ?? "")) return retry("pow");
    return { action: "conflict", reason: "forbidden", detail };
  }
  if (status === 404 || status === 410) return { action: "conflict", reason: "gone", detail };
  if (status === 409) {
    // Même opération encore en cours côté serveur (course entre deux envois) : on réessaie.
    if (/in progress/i.test(detail ?? "")) return retry("busy");
    return { action: "conflict", reason: "unique", detail };
  }
  if (status === 429) {
    // Quota du jeton public épuisé : rejouer ne servirait à rien.
    if (/quota/i.test(detail ?? "")) return { action: "failed_permanent", reason: "quota", detail };
    return retry("rate_limited", err.retryAfter);
  }
  if (status === 408 || status >= 500) return retry("server", err.retryAfter);
  if (status === 400 || status === 413 || status === 415 || status === 422) {
    return { action: "conflict", reason: "invalid", detail, errors: err.errors };
  }
  return { action: "conflict", reason: "other", detail };
}
