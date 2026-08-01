// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { bucketFor, referenceWindow, windowedStatisticsSource } from "./comparisonWindow";
import { EMPTY_ANALYTICS_CONTEXT } from "../builder/AnalyticsContext";
import type { DatasetConfig } from "../api/types";

const MS_PER_DAY = 86_400_000;
function addDays(iso: string, days: number): string {
  return new Date(new Date(iso).getTime() + days * MS_PER_DAY).toISOString().slice(0, 10);
}

test("referenceWindow(previous) shifts back by exactly the window's duration, contiguous with it", () => {
  expect(referenceWindow({ from: "2026-02-01", to: "2026-02-28" }, "previous"))
    .toEqual({ from: "2026-01-05", to: "2026-02-01" });
});

test("referenceWindow(sameLastYear) shifts both bounds back exactly one calendar year", () => {
  expect(referenceWindow({ from: "2026-03-10", to: "2026-03-20" }, "sameLastYear"))
    .toEqual({ from: "2025-03-10", to: "2025-03-20" });
});

test("referenceWindow(sameLastYear) clamps Feb 29 to Feb 28 in a non-leap reference year (documented repli, not a crash)", () => {
  expect(referenceWindow({ from: "2024-02-29", to: "2024-02-29" }, "sameLastYear"))
    .toEqual({ from: "2023-02-28", to: "2023-02-28" });
});

test("bucketFor picks day up to 31 days, week up to 180, month beyond", () => {
  expect(bucketFor({ from: "2026-01-01", to: addDays("2026-01-01", 31) })).toBe("day");
  expect(bucketFor({ from: "2026-01-01", to: addDays("2026-01-01", 32) })).toBe("week");
  expect(bucketFor({ from: "2026-01-01", to: addDays("2026-01-01", 180) })).toBe("week");
  expect(bucketFor({ from: "2026-01-01", to: addDays("2026-01-01", 181) })).toBe("month");
});

test("windowedStatisticsSource merges the window's time filter and reuses ambient extent", () => {
  const dataset: DatasetConfig = { source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: true };
  const ctx = { ...EMPTY_ANALYTICS_CONTEXT, extent: [1, 2, 3, 4] as [number, number, number, number] };
  const source = windowedStatisticsSource(
    "src-1", "ds-1", dataset, ctx, { from: "2026-01-01", to: "2026-01-31" }, { agg: "sum", field: "pop" },
  );
  expect(source).toMatchObject({
    id: "src-1", type: "statistics", service: "core", datasetId: "ds-1",
    query: { agg: "sum", field: "pop", date__gte: "2026-01-01", date__lte: "2026-01-31", bbox: "1,2,3,4" },
  });
});

test("windowedStatisticsSource carries groupBy/bucket through untouched", () => {
  const dataset: DatasetConfig = { source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false };
  const source = windowedStatisticsSource(
    "src-1", "ds-1", dataset, EMPTY_ANALYTICS_CONTEXT, { from: "2026-01-01", to: "2026-01-31" },
    { groupBy: "date", bucket: "day", agg: "count" },
  );
  expect(source.query).toMatchObject({ groupBy: "date", bucket: "day", agg: "count" });
});
