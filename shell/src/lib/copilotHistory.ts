// SPDX-License-Identifier: Apache-2.0
export type CopilotHistoryEntry = {
  id: string;
  message: string;
  opsCount: number;
  status: "ok" | "error";
  executedAt: string;
};

const STORAGE_KEY = "geostudio.copilot.history";
const MAX_ENTRIES = 20;

export function readCopilotHistory(): CopilotHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as CopilotHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function appendCopilotHistory(
  entry: Omit<CopilotHistoryEntry, "id" | "executedAt">,
): CopilotHistoryEntry[] {
  const withMeta: CopilotHistoryEntry = {
    ...entry,
    id: crypto.randomUUID(),
    executedAt: new Date().toISOString(),
  };
  const next = [withMeta, ...readCopilotHistory()].slice(0, MAX_ENTRIES);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // localStorage indisponible (navigation privée, quota dépassé) —
    // l'historique dégrade silencieusement, même patron que
    // sqlLabHistory.ts.
  }
  return next;
}
