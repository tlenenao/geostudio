// SPDX-License-Identifier: Apache-2.0
import { EMPTY_ANALYTICS_CONTEXT, type AnalyticsContextState } from "../builder/AnalyticsContext";

// Unicode-safe base64url: JSON can contain accented labels/values (field
// names, cross-filter values), so a plain btoa(json) would throw on any
// non-Latin1 character.
export function encodeAnalyticsContext(state: AnalyticsContextState): string {
  const json = JSON.stringify(state);
  const base64 = btoa(unescape(encodeURIComponent(json)));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeAnalyticsContext(raw: string | null): AnalyticsContextState {
  if (!raw) return EMPTY_ANALYTICS_CONTEXT;
  try {
    const base64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const json = decodeURIComponent(escape(atob(padded)));
    const parsed = JSON.parse(json) as Partial<AnalyticsContextState>;
    return {
      timeRange: parsed.timeRange ?? null,
      extent: parsed.extent ?? null,
      crossFilter: parsed.crossFilter ?? {},
    };
  } catch {
    return EMPTY_ANALYTICS_CONTEXT;
  }
}
