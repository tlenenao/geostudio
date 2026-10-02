// SPDX-License-Identifier: Apache-2.0
// Clés localStorage cloisonnées par compte (P07.07/P07.08) : deux comptes
// sur le même navigateur ne partagent plus leurs historiques.
let userId = "anonymous";

export function setStorageUser(sub: string | undefined | null): void {
  userId = sub || "anonymous";
}

export function userKey(base: string, ...extra: string[]): string {
  return [base, userId, ...extra].filter(Boolean).join(".");
}

const HISTORY_PREFIXES = ["geostudio.sqlLab.history", "geostudio.copilot.history"];

/** Purge tous les historiques locaux (déconnexion), y compris l'ancienne clé non scopée. */
export function purgeLocalHistories(): void {
  try {
    for (const k of Object.keys(localStorage)) {
      if (HISTORY_PREFIXES.some((p) => k === p || k.startsWith(`${p}.`))) {
        localStorage.removeItem(k);
      }
    }
  } catch {
    // localStorage indisponible : rien à purger.
  }
}
