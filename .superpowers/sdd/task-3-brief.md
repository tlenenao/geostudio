### Task 3: Shell — shared time-window mechanic (`comparisonWindow.ts`)

**Files:**
- Create: `shell/src/lib/comparisonWindow.ts`
- Test: `shell/src/lib/comparisonWindow.test.ts`

**Interfaces:**
- Consumes: `derivePatch` (`shell/src/lib/analyticsPatch.ts:10-43`), `AnalyticsContextState` (`shell/src/builder/AnalyticsContext.tsx:7-11`), `DataSource`/`DatasetConfig` (`shell/src/api/types.ts`).
- Produces (used by Task 4 and Task 5):
  - `type ReferenceMode = "previous" | "sameLastYear"`
  - `type BucketGranularity = "day" | "week" | "month"`
  - `referenceWindow(current: {from: string; to: string}, mode: ReferenceMode): {from: string; to: string}`
  - `bucketFor(current: {from: string; to: string}): BucketGranularity`
  - `windowedStatisticsSource(originSourceId: string, datasetId: string, dataset: DatasetConfig, analyticsCtx: AnalyticsContextState, window: {from: string; to: string}, query: {groupBy?: string; bucket?: BucketGranularity; agg: string; field?: string}): DataSource`

- [ ] **Step 1: Write the failing tests**

Create `shell/src/lib/comparisonWindow.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/lib/comparisonWindow.test.ts`
Expected: FAIL — `Cannot find module './comparisonWindow'`.

- [ ] **Step 3: Implement `shell/src/lib/comparisonWindow.ts`**

```ts
// SPDX-License-Identifier: Apache-2.0
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { derivePatch } from "./analyticsPatch";

export type ReferenceMode = "previous" | "sameLastYear";
export type BucketGranularity = "day" | "week" | "month";

const MS_PER_DAY = 86_400_000;

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
}

// `current.from`/`current.to` are "YYYY-MM-DD" strings, parsed by `new
// Date(...)` as UTC midnight (ISO date-only parsing rule) — every accessor
// here stays UTC too, so the computed calendar day never drifts depending on
// the runtime's local timezone offset.
function shiftYears(d: Date, years: number): Date {
  const year = d.getUTCFullYear() + years;
  const month = d.getUTCMonth();
  const day = d.getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(day, daysInMonth(year, month))));
}

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function referenceWindow(
  current: { from: string; to: string },
  mode: ReferenceMode,
): { from: string; to: string } {
  const from = new Date(current.from), to = new Date(current.to);
  if (mode === "sameLastYear") {
    return { from: toISODate(shiftYears(from, -1)), to: toISODate(shiftYears(to, -1)) };
  }
  const durationMs = to.getTime() - from.getTime();
  const refTo = new Date(from.getTime());
  const refFrom = new Date(from.getTime() - durationMs);
  return { from: toISODate(refFrom), to: toISODate(refTo) };
}

export function bucketFor(current: { from: string; to: string }): BucketGranularity {
  const days = (new Date(current.to).getTime() - new Date(current.from).getTime()) / MS_PER_DAY;
  return days <= 31 ? "day" : days <= 180 ? "week" : "month";
}

// Shared query-construction mechanic (spec §3), reused by indicator's KPI
// comparison (Task 4) and chart's period-comparison mode (Task 5): builds a
// synthetic `statistics` DataSource for one time window and merges it with
// the same ambient filters (extent, cross-filter) DataContext would apply
// for the widget's own flat value — only `timeRange` is substituted.
export function windowedStatisticsSource(
  originSourceId: string,
  datasetId: string,
  dataset: DatasetConfig,
  analyticsCtx: AnalyticsContextState,
  window: { from: string; to: string },
  query: { groupBy?: string; bucket?: BucketGranularity; agg: string; field?: string },
): DataSource {
  const synthetic: DataSource = { id: originSourceId, type: "statistics", service: "core", layer: "", datasetId, query: {} };
  const patch = derivePatch(synthetic, { ...analyticsCtx, timeRange: window }, { [datasetId]: dataset });
  return { ...synthetic, query: { ...query, ...patch } };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/lib/comparisonWindow.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/lib/comparisonWindow.ts shell/src/lib/comparisonWindow.test.ts
git commit -m "feat(shell): add comparisonWindow — reference windows, bucket sizing, windowed statistics source"
```

---

