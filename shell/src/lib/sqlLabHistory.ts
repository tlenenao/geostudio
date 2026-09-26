// SPDX-License-Identifier: Apache-2.0
export type SqlHistoryEntry = {
  id: string;
  sql: string;
  executedAt: string;
  status: "ok" | "error";
  rowCount?: number;
};

const STORAGE_KEY = "geostudio.sqlLab.history";
const MAX_ENTRIES = 20;

export function readSqlHistory(): SqlHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SqlHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function appendSqlHistory(entry: Omit<SqlHistoryEntry, "id">): SqlHistoryEntry[] {
  const withId: SqlHistoryEntry = { ...entry, id: crypto.randomUUID() };
  const next = [withId, ...readSqlHistory()].slice(0, MAX_ENTRIES);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // localStorage indisponible (navigation privée, quota dépassé) —
    // l'historique dégrade silencieusement, l'exécution de la requête
    // elle-même n'est pas affectée.
  }
  return next;
}

export function findSqlHistoryEntry(id: string): SqlHistoryEntry | undefined {
  return readSqlHistory().find((entry) => entry.id === id);
}
