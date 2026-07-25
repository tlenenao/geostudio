// SPDX-License-Identifier: Apache-2.0
export const EXTENT_DEBOUNCE_MS = 500;

export type CrossFilterEntry = { field: string; value: string | string[]; originSourceId: string };

export type AnalyticsContextState = {
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, CrossFilterEntry | undefined>;
};

export const EMPTY_ANALYTICS_CONTEXT: AnalyticsContextState = { timeRange: null, extent: null, crossFilter: {} };
