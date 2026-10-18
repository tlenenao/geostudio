// SPDX-License-Identifier: Apache-2.0
// AUD-119 : derniers items ouverts, proposés par la palette ⌘K quand la saisie est vide.
// Simple confort par navigateur : stockage local, jamais bloquant.
import type { ResourceType } from "../api/types";

const KEY = "geostudio.recentItems";
const MAX = 5;

export type RecentItem = { pk: string; type: ResourceType; title: string };

export function readRecentItems(): RecentItem[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed)
      ? parsed
          .filter(
            (r): r is RecentItem =>
              !!r && typeof r.pk === "string" && typeof r.type === "string" && !!r.title,
          )
          .slice(0, MAX)
      : [];
  } catch {
    return [];
  }
}

export function recordRecentItem(item: RecentItem): void {
  try {
    const next = [item, ...readRecentItems().filter((r) => r.pk !== item.pk)].slice(0, MAX);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // stockage indisponible (navigation privée, quota) : fonction de confort.
  }
}
