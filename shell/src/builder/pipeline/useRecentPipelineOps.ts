// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";

const STORAGE_KEY = "geostudio.pipeline.recentOps";
const MAX_RECENT = 5;

function readStored(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function writeStored(recent: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recent));
  } catch {
    // Quota exceeded or storage disabled (private browsing) — a convenience
    // feature, never worth surfacing an error for.
  }
}

export function useRecentPipelineOps(): { recent: string[]; recordUse: (op: string) => void } {
  const [recent, setRecent] = useState<string[]>(readStored);

  const recordUse = useCallback((op: string) => {
    setRecent((prev) => {
      const next = [op, ...prev.filter((o) => o !== op)].slice(0, MAX_RECENT);
      writeStored(next);
      return next;
    });
  }, []);

  return { recent, recordUse };
}
