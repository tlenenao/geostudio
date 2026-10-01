// SPDX-License-Identifier: Apache-2.0
import { userKey } from "./userStorage";

export type CopilotHistoryEntry = {
  id: string;
  message: string;
  opsCount: number;
  status: "ok" | "error";
  executedAt: string;
};

const BASE_KEY = "geostudio.copilot.history";
const MAX_ENTRIES = 20;

export function readCopilotHistory(itemId = ""): CopilotHistoryEntry[] {
  try {
    const raw = localStorage.getItem(userKey(BASE_KEY, itemId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as CopilotHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function appendCopilotHistory(
  entry: Omit<CopilotHistoryEntry, "id" | "executedAt">,
  itemId = "",
): CopilotHistoryEntry[] {
  const withMeta: CopilotHistoryEntry = {
    ...entry,
    id: crypto.randomUUID(),
    executedAt: new Date().toISOString(),
  };
  const next = [withMeta, ...readCopilotHistory(itemId)].slice(0, MAX_ENTRIES);
  try {
    localStorage.setItem(userKey(BASE_KEY, itemId), JSON.stringify(next));
  } catch {
    // localStorage indisponible (navigation privée, quota dépassé) —
    // l'historique dégrade silencieusement, même patron que
    // sqlLabHistory.ts.
  }
  return next;
}
