# SP-14e — KPI riche & séries temporelles comparées — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional delta/sparkline/threshold enrichment to the `indicator` widget and an optional "compare periods" overlay mode to the `chart` widget (line/area), both driven by a new server-side `bucket` param on `/collections/{id}/aggregate` and a shared client-side time-window mechanic — with zero behavior change when the new props are absent.

**Architecture:** Core gains a `bucket: "day"|"week"|"month"|null` field on `AggregateRequestBody` that switches the group-by expression to `DATE_TRUNC`. The shell gets one new pure module (`comparisonWindow.ts`) computing reference windows, bucket granularity, and synthetic `statistics` `DataSource` queries by reusing the existing `derivePatch` mechanic with a substituted `timeRange`. `indicator.tsx` and `chart.tsx` each call this module from a small set of `useQuery` calls, gated so they only fire once the relevant new props are set AND `ctx.timeRange`/`dataset.timeField` are both active.

**Tech Stack:** FastAPI + DuckDB (core), React + TanStack Query + ECharts + cel-js (shell), pytest / Vitest / Playwright.

## Global Constraints

- Every new prop (`referencePeriod`, `sparkline`, `warningWhen`, `criticalWhen` on `indicator`; `compareEnabled`, `comparePeriod` on `chart`) is optional and absent by default — **zero behavior change** for existing apps that don't set them.
- `bucket` absent on `AggregateRequestBody` = current behavior byte-for-byte (existing `test_analytics_aggregate.py` suite stays green unmodified).
- No new modes beyond `"previous"` / `"sameLastYear"` for reference periods; no author-configurable bucket granularity; no CEL message text, only a 3-level pastille (none/warning/critical).
- Docs/commit messages in French (conventional commits, e.g. `feat(core): …`), code/identifiers in English. Small commits, one subject each.
- Working branch: `dev`.

---

### Task 1: Core — `bucket` param on `/collections/{id}/aggregate`

**Files:**
- Modify: `core/app/analytics/aggregate.py:24-31` (`AggregateRequestBody`), `core/app/analytics/aggregate.py:68-84` (`_validate_fields`), `core/app/analytics/aggregate.py:197-223` (`run_collection_aggregate`)
- Test: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Produces: `AggregateRequestBody.bucket: Literal["day", "week", "month"] | None = None`. When set, `run_collection_aggregate` groups by `DATE_TRUNC(bucket, TRY_CAST(groupBy AS TIMESTAMP))` instead of the raw `groupBy` column, using the same `category_key = request.groupBy` and the same `_pivot_measures`/`_pivot_split` shape as before. `bucket` without `groupBy` raises `UnknownAggregateField("bucket", ...)`.

- [ ] **Step 1: Write the failing core tests**

Append to `core/tests/test_analytics_aggregate.py` (uses the existing `TABLE_INFO`, `_write_partition`, `_row`, `conn` fixture already in the file — `_row`'s third positional arg is stored under the `annee` column, which we reuse to hold date-like strings for these tests since `TABLE_INFO` already declares it as a plain string column):

```python
def test_bucket_groups_rows_by_day(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
        _row(3, "Nord", "2026-01-06", 4, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="count")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "annee"
    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-05 00:00:00", "value": 2},
        {"annee": "2026-01-06 00:00:00", "value": 1},
    ]


def test_bucket_groups_rows_by_month(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2026-01-05", 10, lsn=1), _row(2, "Nord", "2026-01-20", 5, lsn=1),
        _row(3, "Nord", "2026-02-10", 7, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="month", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert sorted(rows, key=lambda r: r["annee"]) == [
        {"annee": "2026-01-01 00:00:00", "value": 15},
        {"annee": "2026-02-01 00:00:00", "value": 7},
    ]


def test_bucket_without_group_by_raises(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2026-01-05", 10, lsn=1)])
    request = AggregateRequestBody(bucket="day")

    with pytest.raises(UnknownAggregateField) as exc:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc.value.field == "bucket"


def test_bucket_on_non_castable_field_groups_under_a_null_bucket(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "pas-une-date", 10, lsn=1), _row(2, "Sud", "2026-01-05", 3, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="annee", bucket="day", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    by_key = {r["annee"]: r["value"] for r in rows}
    assert by_key["None"] == 10
    assert by_key["2026-01-05 00:00:00"] == 3
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bucket -v`
Expected: FAIL — `AggregateRequestBody` has no field `"bucket"` (pydantic `ValidationError` / `TypeError`).

- [ ] **Step 3: Implement `bucket` in `core/app/analytics/aggregate.py`**

Add the import and the new field (`core/app/analytics/aggregate.py:1-31`):

```python
from typing import Literal

from pydantic import BaseModel


class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None


class AggregateRequestBody(BaseModel):
    groupBy: str | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    bucket: Literal["day", "week", "month"] | None = None
```

Add the guard at the top of `_validate_fields` (`core/app/analytics/aggregate.py:68-84`):

```python
def _validate_fields(request: AggregateRequestBody, table_info) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    if request.bucket is not None and not request.groupBy:
        raise UnknownAggregateField("bucket", "bucket requires groupBy")

    check(request.groupBy, "groupBy")
    check(request.split, "split")
    check(request.field, "field")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
    for raw_name in request.filters:
        field_name, _ = _split_filter_key(raw_name)
        check(field_name, f"filters.{raw_name}")
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")
```

Switch `cat_expr` in `run_collection_aggregate` (`core/app/analytics/aggregate.py:197-208`, only the `cat_expr` line changes):

```python
def run_collection_aggregate(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info, request: AggregateRequestBody,
) -> tuple[str, list[dict]]:
    category_key = request.groupBy or "group"
    _validate_fields(request, table_info)

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)
    if request.bucket:
        cat_expr = f"DATE_TRUNC({_sql_lit(request.bucket)}, TRY_CAST({_qi(request.groupBy)} AS TIMESTAMP))"
    else:
        cat_expr = _qi(request.groupBy) if request.groupBy else "'Total'"
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py -k bucket -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full core test suite for non-regression**

Run: `cd core && uv run pytest tests/test_analytics_aggregate.py tests/test_features_aggregate_routes.py -v`
Expected: PASS — all pre-existing tests unaffected (`bucket` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): add optional bucket param to /collections/{id}/aggregate"
```

---

### Task 2: Shell — pass `bucket` through `itemClient.queryDataSource`

**Files:**
- Modify: `shell/src/api/itemClient.ts:40` (`STAT_KEYS`), `shell/src/api/itemClient.ts:49-71` (`buildAggregateBody`)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: nothing new (extends the existing `DataSource.query` vocabulary).
- Produces: a `statistics`-type `DataSource` with `query.bucket` set now posts `body.bucket` to `/collections/{id}/aggregate` instead of leaking into `body.filters`. Task 3/4/5 rely on this to make bucketed sparkline/compare queries reach the core.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/api/itemClient.test.ts`, right after the existing `"queryDataSource sends a bbox query key as body.bbox, not as a filter"` test:

```ts
test("queryDataSource sends a bucket query key as body.bucket, not as a filter", async () => {
  let posted: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/collections/villes/aggregate", async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ categoryKey: "annee", rows: [] });
    }),
  );
  await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "annee", bucket: "week", agg: "count" },
  });
  expect(posted!.bucket).toBe("week");
  expect(posted!.filters).toBeUndefined();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "sends a bucket query key"`
Expected: FAIL — `posted!.bucket` is `undefined` (it currently lands in `body.filters.bucket` instead).

- [ ] **Step 3: Implement the passthrough**

In `shell/src/api/itemClient.ts:40`:

```ts
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures", "bbox", "bucket"]);
```

In `shell/src/api/itemClient.ts:49-72` (`buildAggregateBody`), add the `bucket` line next to `field`:

```ts
function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (query.bucket) body.bucket = String(query.bucket);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const bbox = parseBboxQueryValue(query.bbox);
  if (bbox) body.bbox = bbox;
  const filters: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      filters[k] = String(v);
    }
  }
  if (Object.keys(filters).length) body.filters = filters;
  return body;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): pass bucket through to /collections/{id}/aggregate"
```

---

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

### Task 4: `indicator` — delta vs reference, sparkline, CEL threshold pastille

**Files:**
- Modify: `shell/src/builder/widgets/indicator.tsx`
- Modify (full rewrite): `shell/src/builder/widgets/indicator.test.tsx`

**Interfaces:**
- Consumes: `windowedStatisticsSource`, `referenceWindow`, `bucketFor`, `type ReferenceMode` (Task 3, `../../lib/comparisonWindow`); `useAnalyticsContext` (`../AnalyticsContext`); `useItemClient` (`../../api/ItemClientProvider`); `evaluateExpression` (`../expr`); `EChart` (`../EChart`, lazy).
- Produces: no new exports besides the widget registration — this is a leaf widget.

**Design note (not in the spec verbatim, filling a gap):** the enriched path fetches the dataset's `DatasetConfig` itself via `useQuery(["dataset", datasetId], () => client.getDatasetConfig(datasetId))` — the same query key `DataContext`/`ExplorerDrawer` already use, so when this indicator's own `dataSourceId` is dataset-bound, React Query dedups the fetch against the one `DataContext` already made for the widget's flat value; no *extra* network round-trip in the common case. This dataset lookup is a prerequisite (we need `dataset.timeField` to know if the enriched path is even eligible) and is **not** one of the "up to 3 additional requests" the spec's risk table counts — those are the value/reference/sparkline `statistics` queries, each independently gated.

- [ ] **Step 1: Write the failing tests (full rewrite of `indicator.test.tsx`)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ExplorerProvider } from "../ExplorerContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { AnalyticsContextProvider } from "../AnalyticsContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";

vi.mock("../EChart", () => ({
  EChart: ({ option }: { option: { series?: unknown } }) => {
    const s = option.series;
    const first = Array.isArray(s) ? s[0] : s;
    const data = (first as { data?: unknown[] } | undefined)?.data ?? [];
    return <div data-testid="kpi-sparkline" data-points={data.length} />;
  },
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });
const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });

function renderIndicator(
  props: Record<string, unknown>, ctx: Partial<WidgetContext>,
  client: Partial<ItemClient> = {}, timeRange: { from: string; to: string } | null = null,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const fullClient = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn(), ...client } as unknown as ItemClient;
  const Ind = getWidget("indicator")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={fullClient}>
        <AnalyticsContextProvider interactions="auto" initialState={{ timeRange, extent: null, crossFilter: {} }}>
          <Ind props={props} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client: fullClient };
}

test("indicator counts records by default (unchanged, no new props)", () => {
  const { client } = renderIndicator(
    { dataSourceId: "d", label: "Total", agg: "count" },
    { data: state({ records: [{ id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } }] }) },
  );
  expect(screen.getByText("Total")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(client.getDatasetConfig).not.toHaveBeenCalled();
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("indicator sums a field when agg=sum (unchanged, no new props)", () => {
  renderIndicator(
    { dataSourceId: "d", agg: "sum", field: "pop" },
    { data: state({ records: [{ id: 1, properties: { pop: 10 } }, { id: 2, properties: { pop: 30 } }] }) },
  );
  expect(screen.getByText("40")).toBeInTheDocument();
});

test("indicator uses the theme text/muted tokens", () => {
  renderIndicator({ label: "Total" }, { data: state({ records: [{ id: 1, properties: {} }] }) });
  expect(screen.getByText("1")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByText("Total")).toHaveClass("text-[var(--gs-color-muted)]");
});

test("shows an explorer menu when bound to a dataset and interactions are auto", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Ind = getWidget("indicator")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <ExplorerProvider enabled>
          <Ind props={{ dataSourceId: "src1", label: "Total" }}
            ctx={{ mode: "runtime", data: state({ datasetId: "ds1", records: [{ id: 1, properties: { pop: 10 } }] }) } as WidgetContext} />
        </ExplorerProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("does not show a delta badge without an active time range even if referencePeriod is set", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const { client } = renderIndicator(
    { dataSourceId: "src-1", label: "Total", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [{ id: 1, properties: {} }] }) },
    { getDatasetConfig },
  );
  expect(screen.getByText("1")).toBeInTheDocument();
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
  expect(screen.queryByText(/vs période/)).not.toBeInTheDocument();
});

test("does not show a delta badge when the dataset has no timeField, even with an active time range", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: null, reactsToExtent: false });
  const { client } = renderIndicator(
    { dataSourceId: "src-1", label: "Total", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [{ id: 1, properties: {} }] }) },
    { getDatasetConfig }, { from: "2026-01-01", to: "2026-01-31" },
  );
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
  expect(screen.queryByText(/vs période/)).not.toBeInTheDocument();
});

test("shows a delta badge computed from the server value/reference when referencePeriod + timeRange + timeField are all active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  // Content-aware, not call-order-aware: valueQuery and referenceQuery are
  // two independent useQuery calls in the same render — TanStack Query does
  // not guarantee which one's queryFn actually fires first, so the mock
  // must key its response off the request itself (window.from via
  // date__gte), not off invocation order.
  const queryDataSource = vi.fn().mockImplementation((source: { query: Record<string, unknown> }) => {
    if (source.query.date__gte === "2026-01-01") return Promise.resolve([{ id: "Total", properties: { value: 120 } }]);
    return Promise.resolve([{ id: "Total", properties: { value: 100 } }]);
  });
  renderIndicator(
    { dataSourceId: "src-1", label: "Total", agg: "count", referencePeriod: "previous" },
    { data: state({ datasetId: "ds-1", records: [] }) },
    { getDatasetConfig, queryDataSource }, { from: "2026-01-01", to: "2026-01-31" },
  );
  expect(await screen.findByText("120")).toBeInTheDocument();
  expect(await screen.findByText(/\+20 % vs période précédente/)).toBeInTheDocument();
});

test("shows a sparkline mini-chart when sparkline is true and time context is active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const queryDataSource = vi.fn().mockResolvedValue([
    { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 3 } },
    { id: "2026-01-02 00:00:00", properties: { date: "2026-01-02 00:00:00", value: 5 } },
  ]);
  renderIndicator(
    { dataSourceId: "src-1", label: "Total", sparkline: true },
    { data: state({ datasetId: "ds-1", records: [] }) },
    { getDatasetConfig, queryDataSource }, { from: "2026-01-01", to: "2026-01-02" },
  );
  const sparkline = await screen.findByTestId("kpi-sparkline");
  expect(sparkline).toHaveAttribute("data-points", "2");
});

test("shows a critical pastille when criticalWhen evaluates truthy against the displayed value", async () => {
  renderIndicator(
    { label: "Total", agg: "count", criticalWhen: "record.value > 1" },
    { variables: {}, user: { name: "u" }, data: state({ records: [{ id: 1, properties: {} }, { id: 2, properties: {} }] }) },
  );
  expect(await screen.findByLabelText("Seuil critique atteint")).toBeInTheDocument();
});

test("shows a warning pastille when only warningWhen evaluates truthy", async () => {
  renderIndicator(
    { label: "Total", agg: "count", warningWhen: "record.value > 1", criticalWhen: "record.value > 100" },
    { data: state({ records: [{ id: 1, properties: {} }, { id: 2, properties: {} }] }) },
  );
  expect(await screen.findByLabelText("Seuil d'alerte atteint")).toBeInTheDocument();
  expect(screen.queryByLabelText("Seuil critique atteint")).not.toBeInTheDocument();
});

test("shows no pastille when threshold expressions are absent", () => {
  renderIndicator({ label: "Total", agg: "count" }, { data: state({ records: [{ id: 1, properties: {} }] }) });
  expect(screen.queryByLabelText("Seuil critique atteint")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Seuil d'alerte atteint")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx`
Expected: FAIL — `indicator.tsx` doesn't accept/use `referencePeriod`/`sparkline`/`criticalWhen`/`warningWhen`, and rendering without `QueryClientProvider`/`ItemClientProvider` in the old file would previously have worked, but the new tests import providers expecting the component to actually call `useQuery`/`useItemClient` — currently a no-op, so delta/sparkline/pastille assertions fail.

- [ ] **Step 3: Implement `shell/src/builder/widgets/indicator.tsx` (full rewrite)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { ExplorerMenu } from "./ExplorerMenu";
import { useAnalyticsContext } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { evaluateExpression } from "../expr";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import type { DatasetConfig } from "../../api/types";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

type KpiComparison = {
  active: boolean;
  loading: boolean;
  value: number | null;
  delta: number | null;
  deltaPct: number | null;
  sparklinePoints: { bucket: string; value: number }[];
};

// Shared mechanic (Task 3, spec §3): fetches the dataset config (needed to
// know `timeField`), then — only once referencePeriod/sparkline is actually
// requested AND ctx.timeRange + dataset.timeField are both active — issues
// up to 3 independent `statistics` queries (current value, reference value,
// bucketed sparkline series). Each `useQuery` call is unconditional (Rules
// of Hooks); `enabled` gates the network request, not the hook call.
function useKpiComparison(
  datasetId: string | undefined,
  originSourceId: string,
  referencePeriod: ReferenceMode | undefined,
  sparklineEnabled: boolean,
  agg: string,
  field: string,
): KpiComparison {
  const client = useItemClient();
  const analyticsCtx = useAnalyticsContext();
  const wantsComparison = Boolean(referencePeriod || sparklineEnabled);

  const datasetQuery = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => client.getDatasetConfig(datasetId as string),
    enabled: Boolean(wantsComparison && datasetId),
  });
  const dataset = datasetQuery.data;
  const timeRange = analyticsCtx.timeRange;
  const active = wantsComparison && Boolean(dataset?.timeField) && Boolean(timeRange);

  const valueQuery = useQuery({
    queryKey: ["kpi-value", datasetId, timeRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod),
  });

  const referenceRange = active && referencePeriod ? referenceWindow(timeRange as { from: string; to: string }, referencePeriod) : null;
  const referenceQuery = useQuery({
    queryKey: ["kpi-reference", datasetId, referenceRange, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange as { from: string; to: string }, { agg, field: field || undefined }),
    ),
    enabled: Boolean(active && referencePeriod && referenceRange),
  });

  const bucket = active && timeRange ? bucketFor(timeRange) : "day";
  const sparklineQuery = useQuery({
    queryKey: ["kpi-sparkline", datasetId, timeRange, bucket, agg, field],
    queryFn: () => client.queryDataSource(
      windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, {
        groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: field || undefined,
      }),
    ),
    enabled: Boolean(active && sparklineEnabled),
  });

  const value = referencePeriod && valueQuery.data ? Number(valueQuery.data[0]?.properties.value ?? 0) : null;
  const reference = referencePeriod && referenceQuery.data ? Number(referenceQuery.data[0]?.properties.value ?? 0) : null;
  const delta = value !== null && reference !== null ? value - reference : null;
  const deltaPct = delta !== null && reference !== null && reference !== 0 ? delta / reference : null;
  const sparklinePoints = sparklineEnabled && dataset?.timeField && sparklineQuery.data
    ? sparklineQuery.data.map((r) => ({ bucket: String(r.properties[dataset.timeField as string] ?? ""), value: Number(r.properties.value ?? 0) }))
    : [];

  const loading = active && (
    (Boolean(referencePeriod) && (valueQuery.isLoading || referenceQuery.isLoading)) ||
    (sparklineEnabled && sparklineQuery.isLoading)
  );

  return { active, loading, value, delta, deltaPct, sparklinePoints };
}

function deltaLabel(delta: number, deltaPct: number | null, mode: ReferenceMode): string {
  const refLabel = mode === "previous" ? "période précédente" : "même période l'an dernier";
  const sign = delta >= 0 ? "+" : "";
  const magnitude = deltaPct !== null ? `${sign}${Math.round(deltaPct * 100)} %` : `${sign}${delta}`;
  return `${magnitude} vs ${refLabel}`;
}

function thresholdLevel(
  criticalWhen: string, warningWhen: string,
  exprCtx: { vars: Record<string, unknown>; user: { name: string }; record: Record<string, unknown> },
): "critical" | "warning" | null {
  if (criticalWhen && evaluateExpression(criticalWhen, exprCtx)) return "critical";
  if (warningWhen && evaluateExpression(warningWhen, exprCtx)) return "warning";
  return null;
}

function sparklineOption(points: { bucket: string; value: number }[]): EChartsOption {
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: "category", show: false, data: points.map((p) => p.bucket) },
    yAxis: { type: "value", show: false },
    series: [{ type: "line", data: points.map((p) => p.value), showSymbol: false, lineStyle: { width: 1.5 } }],
  } as EChartsOption;
}

export function registerIndicatorWidget(): void {
  registerWidget({
    type: "indicator",
    label: "Indicateur",
    defaultProps: { dataSourceId: "", label: "Indicateur", agg: "count", field: "" },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })} />
        <label className="flex flex-col gap-1">Libellé
          <input aria-label="Libellé de l'indicateur" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")} onChange={(e) => onChange({ ...props, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Agrégation
          <select aria-label="Agrégation" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.agg ?? "count")} onChange={(e) => onChange({ ...props, agg: e.target.value })}>
            <option value="count">Nombre</option>
            <option value="sum">Somme</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">Champ (pour la somme)
          <input aria-label="Champ agrégé" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")} onChange={(e) => onChange({ ...props, field: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Comparer à
          <select aria-label="Comparer à" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.referencePeriod ?? "")}
            onChange={(e) => onChange({ ...props, referencePeriod: e.target.value || undefined })}>
            <option value="">Aucune</option>
            <option value="previous">Période précédente</option>
            <option value="sameLastYear">Même période l'an dernier</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label="Afficher un sparkline"
            checked={Boolean(props.sparkline)} onChange={(e) => onChange({ ...props, sparkline: e.target.checked })} />
          Afficher un sparkline
        </label>
        <label className="flex flex-col gap-1">Seuil critique (CEL)
          <input aria-label="Seuil critique (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.criticalWhen ?? "")} onChange={(e) => onChange({ ...props, criticalWhen: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">Seuil d'alerte (CEL)
          <input aria-label="Seuil d'alerte (CEL)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.warningWhen ?? "")} onChange={(e) => onChange({ ...props, warningWhen: e.target.value })} />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const data = ctx.data;
      const agg = String(props.agg ?? "count");
      const field = String(props.field ?? "");
      const referencePeriod = (props.referencePeriod as ReferenceMode | undefined) || undefined;
      const sparklineEnabled = Boolean(props.sparkline);
      const criticalWhen = String(props.criticalWhen ?? "");
      const warningWhen = String(props.warningWhen ?? "");

      const comparison = useKpiComparison(
        data?.datasetId, String(props.dataSourceId ?? ""), referencePeriod, sparklineEnabled, agg, field,
      );

      if (!data || data.loading || comparison.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;

      const flatValue =
        agg === "sum"
          ? data.records.reduce((acc, r) => acc + (Number(r.properties[field]) || 0), 0)
          : data.records.length;
      const value = comparison.active && referencePeriod && comparison.value !== null ? comparison.value : flatValue;

      const badge = comparison.active && referencePeriod && comparison.delta !== null
        ? deltaLabel(comparison.delta, comparison.deltaPct, referencePeriod)
        : null;

      const level = criticalWhen || warningWhen
        ? thresholdLevel(criticalWhen, warningWhen, {
            vars: ctx.variables ?? {}, user: ctx.user ?? { name: "" },
            record: { value, delta: comparison.delta, deltaPct: comparison.deltaPct },
          })
        : null;

      return (
        <div className="relative flex h-full flex-col items-center justify-center gap-1">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />
          <div className="flex items-center gap-1">
            <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
            {level && (
              <span
                aria-label={level === "critical" ? "Seuil critique atteint" : "Seuil d'alerte atteint"}
                className={`h-2.5 w-2.5 rounded-full ${level === "critical" ? "bg-red-600" : "bg-orange-500"}`}
              />
            )}
          </div>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
          {badge && <span className="text-xs text-[var(--gs-color-muted)]">{badge}</span>}
          {sparklineEnabled && comparison.active && comparison.sparklinePoints.length > 0 && (
            <div className="h-8 w-full">
              <Suspense fallback={null}>
                <EChart option={sparklineOption(comparison.sparklinePoints)} />
              </Suspense>
            </div>
          )}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full shell unit suite for non-regression**

Run: `cd shell && npm run test`
Expected: PASS — all 61+ files green (in particular anything importing/rendering `indicator`, e.g. `AppRenderer.test.tsx`).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx
git commit -m "feat(shell): indicator gets delta vs reference period, sparkline, CEL threshold pastille"
```

---

### Task 5: `chart` — "compare periods" mode for line/area

**Files:**
- Modify: `shell/src/builder/widgets/chartOption.ts`
- Modify: `shell/src/builder/widgets/chartOption.test.ts`
- Modify: `shell/src/builder/widgets/chart.tsx`
- Modify (full rewrite): `shell/src/builder/widgets/chart.test.tsx`

**Interfaces:**
- Consumes: `bucketFor`, `referenceWindow`, `windowedStatisticsSource`, `type ReferenceMode`, `type BucketGranularity` (Task 3, `../../lib/comparisonWindow`).
- Produces: `buildCompareOption(props: ChartProps, current: ComparePoint[], reference: ComparePoint[], bucket: BucketGranularity): EChartsOption` and `type ComparePoint = { bucket: string; value: number }`, exported from `chartOption.ts` alongside the existing `buildOption`.

**Design note (not in the spec verbatim, filling a gap):** compare mode needs a measure (agg + field) to aggregate over time buckets, but `chart.tsx` has no `agg` prop today. Rather than adding a redundant one, this reuses the existing `valueField` prop (currently only consumed by pie/gauge) as the measure field: `agg = valueField ? "sum" : "count"` — mirrors `indicator.tsx`'s own `agg`/`field` convention exactly and keeps the new-props surface to just `compareEnabled`/`comparePeriod`, as the spec states.

- [ ] **Step 1: Write the failing `chartOption.test.ts` additions**

Append to `shell/src/builder/widgets/chartOption.test.ts`:

```ts
import { buildCompareOption } from "./chartOption";

test("buildCompareOption renders two aligned series on a relative offset axis", () => {
  const current = [{ bucket: "2026-01-01 00:00:00", value: 10 }, { bucket: "2026-01-02 00:00:00", value: 12 }];
  const reference = [{ bucket: "2025-01-01 00:00:00", value: 8 }, { bucket: "2025-01-02 00:00:00", value: 9 }];
  const opt = buildCompareOption({ chartType: "line" }, current, reference, "day");
  expect(series(opt)).toHaveLength(2);
  expect(series(opt).map((s) => s.name)).toEqual(["Période courante", "Référence"]);
  expect(series(opt)[0].data).toEqual([10, 12]);
  expect(series(opt)[1].data).toEqual([8, 9]);
  expect((opt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Jour 1", "Jour 2"]);
  expect(series(opt)[1].lineStyle?.type).toBe("dashed");
});

test("buildCompareOption labels the offset axis by week/month depending on bucket", () => {
  const weekOpt = buildCompareOption({ chartType: "line" }, [{ bucket: "w", value: 1 }], [], "week");
  expect((weekOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Semaine 1"]);
  const monthOpt = buildCompareOption({ chartType: "area" }, [{ bucket: "m", value: 1 }], [], "month");
  expect((monthOpt as { xAxis?: { data?: string[] } }).xAxis?.data).toEqual(["Mois 1"]);
});

test("buildCompareOption applies the yAxisUnit/yAxisFormat formatter like buildOption", () => {
  const opt = buildCompareOption({ chartType: "line", yAxisUnit: "kg" }, [{ bucket: "d", value: 1 }], [], "day");
  const formatter = (opt as { yAxis?: { axisLabel?: { formatter?: (v: unknown) => string } } }).yAxis?.axisLabel?.formatter;
  expect(formatter?.(5)).toBe("5 kg");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts -t "buildCompareOption"`
Expected: FAIL — `buildCompareOption` is not exported from `./chartOption`.

- [ ] **Step 3: Implement `buildCompareOption` in `shell/src/builder/widgets/chartOption.ts`**

Add near the bottom of the file, before `finalize` (which it reuses), and add the import at the top:

```ts
import type { BucketGranularity } from "../../lib/comparisonWindow";
```

```ts
export type ComparePoint = { bucket: string; value: number };

function offsetLabel(bucket: BucketGranularity, index: number): string {
  const unit = bucket === "day" ? "Jour" : bucket === "week" ? "Semaine" : "Mois";
  return `${unit} ${index + 1}`;
}

// Compare-periods mode (SP-14e §5): two line series on a relative offset
// axis (index-based, not calendar dates) so the current window and its
// reference period overlay regardless of their absolute dates. Independent
// of buildOption — when compare mode is off, buildOption is untouched.
export function buildCompareOption(
  props: ChartProps, current: ComparePoint[], reference: ComparePoint[], bucket: BucketGranularity,
): EChartsOption {
  const length = Math.max(current.length, reference.length);
  const categories = Array.from({ length }, (_, i) => offsetLabel(bucket, i));
  const fmt = valueFormatter(props);
  const yAxis: Record<string, unknown> = { type: props.yAxisType ?? "value" };
  if (fmt) yAxis.axisLabel = { formatter: fmt };

  const built: Record<string, unknown> = {
    tooltip: { trigger: "axis" },
    legend: { show: props.legend ?? true },
    xAxis: { type: "category", data: categories },
    yAxis,
    series: [
      { type: "line", name: "Période courante", data: current.map((p) => p.value) },
      { type: "line", name: "Référence", data: reference.map((p) => p.value), lineStyle: { type: "dashed" }, itemStyle: { opacity: 0.6 } },
    ],
  };
  if (props.title) built.title = { text: props.title };
  return finalize(props, built);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chartOption.test.ts`
Expected: PASS (all tests in the file, including the 3 new ones)

- [ ] **Step 5: Write the failing `chart.test.tsx` (full rewrite)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { ActionBus } from "../ActionBus";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import type { WidgetContext } from "../registry";
import type { DataSourceState, ItemClient } from "../../api/types";
import { ExplorerProvider } from "../ExplorerContext";

vi.mock("../EChart", () => ({
  EChart: ({ option, onClick }: { option: { series?: unknown }; onClick?: (params: { name?: string }) => void }) => {
    const s = option.series;
    const n = Array.isArray(s) ? s.length : s ? 1 : 0;
    return (
      <div data-testid="echart" data-series={n} onClick={() => onClick?.({ name: "Nord" })} />
    );
  },
}));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const state = (over: Partial<DataSourceState> = {}): DataSourceState => ({ loading: false, error: false, records: [], ...over });
const wide = state({ records: [
  { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
  { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 7 } },
] });

function renderChart(
  props: Record<string, unknown>, ctx: Partial<WidgetContext>,
  client: Partial<ItemClient> = {}, timeRange: { from: string; to: string } | null = null,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const fullClient = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn(), ...client } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={fullClient}>
        <AnalyticsContextProvider interactions="auto" initialState={{ timeRange, extent: null, crossFilter: {} }}>
          <Chart props={props} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client: fullClient };
}

test("renders an ECharts panel with one series per column", async () => {
  renderChart({ chartType: "bar", categoryField: "region" }, { data: wide });
  const el = await screen.findByTestId("echart");
  expect(el).toHaveAttribute("data-series", "2");
});

test("shows loading, error and empty states", () => {
  const { rerender } = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ItemClientProvider client={{ queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient}>
        {(() => { const Chart = getWidget("chart")!.Component; return <Chart props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />; })()}
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/chargement/i)).toBeInTheDocument();
  const Chart = getWidget("chart")!.Component;
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Chart props={{}} ctx={{ mode: "runtime", data: state({ error: true }) } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/erreur/i)).toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Chart props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/aucune donnée/i)).toBeInTheDocument();
});

test("PropsPanel edits the chart type and exposes the advanced JSON escape hatch", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Option ECharts avancée (JSON)")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Type de graphique"), "line");
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ chartType: "line" }));
});

test("PropsPanel shows the compare-periods toggle only for line/area chart types", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("chart")!.PropsPanel;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "bar" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.queryByLabelText("Comparer les périodes")).not.toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{} as unknown as ItemClient}>
        <Panel props={{ chartType: "line" }} dataSources={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("Comparer les périodes")).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Comparer les périodes"));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ compareEnabled: true }));
});

test("loading and empty states use the theme muted token", () => {
  renderChart({}, { data: state({ loading: true }) });
  expect(screen.getByText(/chargement/i)).toHaveClass("text-[var(--gs-color-muted)]");
});

test("declares the categorySelected event", () => {
  expect(getWidget("chart")!.events).toEqual(["categorySelected"]);
});

test("clicking a category always emits categorySelected on the bus", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "chart1", event: "categorySelected", to: "sink", action: "log" }]);
  renderChart({ categoryField: "region", chartType: "bar" }, { data: wide, bus, widgetId: "chart1" });
  await userEvent.click(await screen.findByTestId("echart"));
  expect(handler).toHaveBeenCalledWith({ region: "Nord" });
});

test("sets the cross-filter when interactions is auto and the source is dataset-bound", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    const entry = ctx.crossFilter["dataset-1"];
    return <p>cf:{entry ? `${entry.field}=${entry.value}` : "none"}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart props={{ categoryField: "region", chartType: "bar", dataSourceId: "src-1" }}
            ctx={{ mode: "runtime", data: { ...wide, datasetId: "dataset-1" } } as WidgetContext} />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf:region=Nord")).toBeInTheDocument();
});

test("does not set a cross-filter when the source has no datasetId (manual wiring only)", async () => {
  function Probe() {
    const ctx = useAnalyticsContext();
    return <p>cf-count:{Object.keys(ctx.crossFilter).length}</p>;
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <AnalyticsContextProvider interactions="auto">
          <Chart props={{ categoryField: "region", chartType: "bar" }} ctx={{ mode: "runtime", data: wide } as WidgetContext} />
          <Probe />
        </AnalyticsContextProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByTestId("echart"));
  expect(await screen.findByText("cf-count:0")).toBeInTheDocument();
});

test("shows an explorer menu when the widget is bound to a dataset and interactions are auto", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { queryDataSource: vi.fn(), getDatasetConfig: vi.fn() } as unknown as ItemClient;
  const Chart = getWidget("chart")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <ExplorerProvider enabled>
          <Chart
            props={{ chartType: "bar", categoryField: "region", dataSourceId: "src1" }}
            ctx={{ mode: "runtime", data: { ...wide, datasetId: "ds1" } } as WidgetContext}
          />
        </ExplorerProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
});

test("compareEnabled has no visible effect without an active time range (falls back to the single-series chart)", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  const { client } = renderChart(
    { chartType: "line", categoryField: "region", compareEnabled: true },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig },
  );
  const el = await screen.findByTestId("echart");
  expect(el).toHaveAttribute("data-series", "2"); // normal per-column series, unaffected
  await waitFor(() => expect(getDatasetConfig).toHaveBeenCalled());
  expect(client.queryDataSource).not.toHaveBeenCalled();
});

test("compareEnabled builds a 2-series compare option once timeRange + timeField are both active", async () => {
  const getDatasetConfig = vi.fn().mockResolvedValue({ source: "collection", collectionId: "events", columns: {}, timeField: "date", reactsToExtent: false });
  // Content-aware, not call-order-aware — same reasoning as the indicator's
  // delta test: currentQuery/referenceQuery are independent useQuery calls,
  // so key the response off the request's date__gte instead of call order.
  const queryDataSource = vi.fn().mockImplementation((source: { query: Record<string, unknown> }) => {
    if (source.query.date__gte === "2026-01-01") {
      return Promise.resolve([
        { id: "2026-01-01 00:00:00", properties: { date: "2026-01-01 00:00:00", value: 5 } },
        { id: "2026-01-02 00:00:00", properties: { date: "2026-01-02 00:00:00", value: 7 } },
      ]);
    }
    return Promise.resolve([{ id: "2025-12-31 00:00:00", properties: { date: "2025-12-31 00:00:00", value: 3 } }]);
  });
  renderChart(
    { chartType: "line", categoryField: "region", compareEnabled: true, comparePeriod: "previous" },
    { data: { ...wide, datasetId: "ds-1" } },
    { getDatasetConfig, queryDataSource },
    { from: "2026-01-01", to: "2026-01-02" },
  );
  const el = await screen.findByTestId("echart");
  await waitFor(() => expect(el).toHaveAttribute("data-series", "2"));
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx`
Expected: FAIL — no `PropsPanel` toggle for compare, and existing Component tests likely also fail because `chart.tsx` doesn't yet call `useItemClient`/`useQuery` at all (the previous file rendered fine without providers; this rewritten test suite exercises the not-yet-implemented gating), plus the two new compare-mode tests fail outright.

- [ ] **Step 7: Implement compare mode in `shell/src/builder/widgets/chart.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useAnalyticsContext, useSetCrossFilter } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import { bucketFor, referenceWindow, windowedStatisticsSource, type ReferenceMode } from "../../lib/comparisonWindow";
import { buildOption, buildCompareOption, type ChartProps, type ComparePoint } from "./chartOption";
import { ExplorerMenu } from "./ExplorerMenu";
import type { DataRecord, DatasetConfig } from "../../api/types";

const EChart = lazy(() => import("../EChart").then((m) => ({ default: m.EChart })));

const CHART_TYPES: [string, string][] = [
  ["bar", "Barres"], ["line", "Lignes"], ["area", "Aires"], ["scatter", "Nuage de points"],
  ["pie", "Camembert"], ["doughnut", "Anneau"], ["radar", "Radar"], ["heatmap", "Carte de chaleur"],
  ["gauge", "Jauge"], ["boxplot", "Boîte à moustaches"],
];
const AXIS_TYPES: [string, string][] = [
  ["category", "Catégorie"], ["value", "Valeur"], ["time", "Temps"], ["log", "Logarithmique"],
];

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

function toComparePoints(records: DataRecord[] | undefined, timeField: string): ComparePoint[] {
  return (records ?? []).map((r) => ({ bucket: String(r.properties[timeField] ?? ""), value: Number(r.properties.value ?? 0) }));
}

export function registerChartWidget(): void {
  registerWidget({
    type: "chart",
    label: "Graphique",
    defaultProps: {
      dataSourceId: "", chartType: "bar", categoryField: "", valueField: "",
      stack: false, legend: true, zoom: false,
      xAxisType: "category", yAxisType: "value", yAxisFormat: "", yAxisUnit: "",
      title: "", advancedOption: "", compareEnabled: false, comparePeriod: "previous",
    },
    defaultSize: { w: 6, h: 4 },
    events: ["categorySelected"],
    PropsPanel: ({ props, onChange, dataSources }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      const chartType = String(props.chartType ?? "bar");
      const showCompare = chartType === "line" || chartType === "area";
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => set({ dataSourceId: id })} />
          <label className={labelCls}>Type de graphique
            <select aria-label="Type de graphique" className={inputCls}
              value={chartType} onChange={(e) => set({ chartType: e.target.value })}>
              {CHART_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Champ catégorie / X
            <input aria-label="Champ catégorie" className={inputCls}
              value={String(props.categoryField ?? "")} onChange={(e) => set({ categoryField: e.target.value })} />
          </label>
          <label className={labelCls}>Champ valeur (camembert / jauge / comparaison)
            <input aria-label="Champ valeur" className={inputCls}
              value={String(props.valueField ?? "")} onChange={(e) => set({ valueField: e.target.value })} />
          </label>
          {showCompare && (
            <>
              <label className="flex items-center gap-2">
                <input type="checkbox" aria-label="Comparer les périodes"
                  checked={Boolean(props.compareEnabled)} onChange={(e) => set({ compareEnabled: e.target.checked })} />
                Comparer les périodes
              </label>
              <label className={labelCls}>Période de référence
                <select aria-label="Période de référence" className={inputCls}
                  value={String(props.comparePeriod ?? "previous")} onChange={(e) => set({ comparePeriod: e.target.value })}>
                  <option value="previous">Période précédente</option>
                  <option value="sameLastYear">Même période l'an dernier</option>
                </select>
              </label>
            </>
          )}
          <label className={labelCls}>Type d'axe X
            <select aria-label="Type d'axe X" className={inputCls}
              value={String(props.xAxisType ?? "category")} onChange={(e) => set({ xAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Type d'axe Y
            <select aria-label="Type d'axe Y" className={inputCls}
              value={String(props.yAxisType ?? "value")} onChange={(e) => set({ yAxisType: e.target.value })}>
              {AXIS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className={labelCls}>Unité de l'axe Y
            <input aria-label="Unité de l'axe Y" className={inputCls}
              value={String(props.yAxisUnit ?? "")} onChange={(e) => set({ yAxisUnit: e.target.value })} />
          </label>
          <label className={labelCls}>Titre
            <input aria-label="Titre du graphique" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Empiler les séries"
              checked={Boolean(props.stack)} onChange={(e) => set({ stack: e.target.checked })} />
            Empiler les séries
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Afficher la légende"
              checked={props.legend !== false} onChange={(e) => set({ legend: e.target.checked })} />
            Afficher la légende
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Activer le zoom"
              checked={Boolean(props.zoom)} onChange={(e) => set({ zoom: e.target.checked })} />
            Activer le zoom
          </label>
          <label className={labelCls}>Option ECharts avancée (JSON)
            <textarea aria-label="Option ECharts avancée (JSON)"
              className="rounded-md border border-slate-300 p-2 font-mono text-xs" rows={4}
              placeholder='{"color":["#f00"]}'
              value={String(props.advancedOption ?? "")} onChange={(e) => set({ advancedOption: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const setCrossFilter = useSetCrossFilter();
      const analyticsCtx = useAnalyticsContext();
      const client = useItemClient();
      const data = ctx.data;
      const datasetId = data?.datasetId;
      const chartType = String(props.chartType ?? "bar");
      const originSourceId = String(props.dataSourceId ?? "");
      const compareRequested = Boolean(props.compareEnabled) && (chartType === "line" || chartType === "area");
      const comparePeriod = (props.comparePeriod as ReferenceMode | undefined) ?? "previous";
      const valueField = String(props.valueField ?? "");
      const agg = valueField ? "sum" : "count";

      const datasetQuery = useQuery({
        queryKey: ["dataset", datasetId],
        queryFn: () => client.getDatasetConfig(datasetId as string),
        enabled: Boolean(compareRequested && datasetId),
      });
      const dataset = datasetQuery.data;
      const timeRange = analyticsCtx.timeRange;
      const compareActive = compareRequested && Boolean(dataset?.timeField) && Boolean(timeRange);
      const bucket = compareActive && timeRange ? bucketFor(timeRange) : "day";
      const referenceRange = compareActive && timeRange ? referenceWindow(timeRange, comparePeriod) : null;

      const currentQuery = useQuery({
        queryKey: ["chart-compare-current", datasetId, timeRange, bucket, agg, valueField],
        queryFn: () => client.queryDataSource(
          windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, timeRange as { from: string; to: string }, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          }),
        ),
        enabled: Boolean(compareActive),
      });
      const referenceQuery = useQuery({
        queryKey: ["chart-compare-reference", datasetId, referenceRange, bucket, agg, valueField],
        queryFn: () => client.queryDataSource(
          windowedStatisticsSource(originSourceId, datasetId as string, dataset as DatasetConfig, analyticsCtx, referenceRange as { from: string; to: string }, {
            groupBy: (dataset as DatasetConfig).timeField as string, bucket, agg, field: valueField || undefined,
          }),
        ),
        enabled: Boolean(compareActive && referenceRange),
      });

      if (compareActive) {
        if (currentQuery.isLoading || referenceQuery.isLoading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
        if (currentQuery.isError || referenceQuery.isError) return <p className="text-xs text-red-600">Erreur de données</p>;
        const timeField = (dataset as DatasetConfig).timeField as string;
        const option = buildCompareOption(
          props as unknown as ChartProps, toComparePoints(currentQuery.data, timeField), toComparePoints(referenceQuery.data, timeField), bucket,
        );
        return (
          <div className="relative h-full">
            <ExplorerMenu datasetId={datasetId} dataSourceId={originSourceId} />
            <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
              <EChart option={option} />
            </Suspense>
          </div>
        );
      }

      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
      const option = buildOption(props as unknown as ChartProps, data.records);
      const categoryField = String(props.categoryField ?? "");
      function handleClick(params: { name?: string }) {
        if (!categoryField) return;
        const value = params.name != null ? String(params.name) : "";
        ctx.bus?.emit(ctx.widgetId ?? "", "categorySelected", { [categoryField]: value });
        if (data?.datasetId) setCrossFilter(data.datasetId, categoryField, value, originSourceId);
      }
      return (
        <div className="relative h-full">
          <ExplorerMenu datasetId={data.datasetId} dataSourceId={originSourceId} />
          <Suspense fallback={<div className="text-xs text-slate-400">Graphique…</div>}>
            <EChart option={option} onClick={handleClick} />
          </Suspense>
        </div>
      );
    },
  });
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/chartOption.test.ts`
Expected: PASS (all tests)

- [ ] **Step 9: Run the full shell unit suite for non-regression**

Run: `cd shell && npm run test`
Expected: PASS — all files green, in particular `AppRenderer.test.tsx` and anything else rendering `chart`/`indicator` widgets.

- [ ] **Step 10: Typecheck**

Run: `cd shell && npm run build`
Expected: PASS — `tsc --noEmit` clean, then `vite build` succeeds.

- [ ] **Step 11: Commit**

```bash
git add shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx shell/src/builder/widgets/chartOption.ts shell/src/builder/widgets/chartOption.test.ts
git commit -m "feat(shell): chart gets a compare-periods mode for line/area (2 aligned series on a relative axis)"
```

---

### Task 6: E2E — extend `analytics-context.spec.ts`

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), the existing `createApp`/`addFeaturesSource`/`promoteLastSource` helpers already in the file (unchanged).
- Produces: no new exports — pure E2E coverage addition.

- [ ] **Step 1: Write the new E2E scenarios**

Append to `shell/e2e/analytics-context.spec.ts` (after the last existing test, scenario 11):

```ts
// -------------------------------------------------------------------------
// Scénario 12 (SP-14e) — KPI riche : delta affiché contre la période de
// référence quand referencePeriod + plage temporelle + dataset.timeField
// sont tous actifs.
// -------------------------------------------------------------------------
test("a KPI shows a delta badge against the reference period", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-10" } }, { id: 2, properties: { nom: "B", date: "2026-01-20" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    const body = await route.request().postDataJSON();
    const gte = body.filters?.date__gte;
    if (gte === "2026-01-01") return route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 120 }] } });
    if (gte === "2025-12-01") return route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 100 }] } });
    await route.fulfill({ json: { categoryKey: "group", rows: [] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "KPI delta");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Comparer à").selectOption("previous");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");

  await expect(page.getByText("120")).toBeVisible();
  await expect(page.getByText(/\+20 % vs période précédente/)).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 13 (SP-14e) — seuil CEL : une pastille critique apparaît quand
// criticalWhen dépasse le seuil, absente sinon (indicateur à plat, sans
// contexte temporel).
// -------------------------------------------------------------------------
test("a KPI shows a critical pastille when criticalWhen is exceeded, none otherwise", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({ json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "valeur", type: "number" }] } });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { valeur: 1 } }, { id: 2, properties: { valeur: 1 } }, { id: 3, properties: { valeur: 1 } },
    ] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Seuil CEL");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Seuil critique (CEL)").fill("record.value > 2");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByText("3")).toBeVisible();
  await expect(page.getByLabelText("Seuil critique atteint")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 14 (SP-14e) — chart en mode comparaison : 2 séries visibles
// (attribut data-chart-series du wrapper EChart, seul signal DOM fiable
// pour une légende rendue en canvas).
// -------------------------------------------------------------------------
test("chart compare-periods mode renders two aligned series", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-01" } }, { id: 2, properties: { nom: "B", date: "2026-01-02" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    const body = await route.request().postDataJSON();
    const gte = body.filters?.date__gte;
    if (gte === "2026-01-01") {
      return route.fulfill({ json: { categoryKey: "date", rows: [
        { date: "2026-01-01 00:00:00", value: 5 }, { date: "2026-01-02 00:00:00", value: 7 },
      ] } });
    }
    if (gte === "2025-12-31") {
      return route.fulfill({ json: { categoryKey: "date", rows: [{ date: "2025-12-31 00:00:00", value: 3 }] } });
    }
    await route.fulfill({ json: { categoryKey: "date", rows: [] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "Chart compare");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("line");
  await page.getByLabel("Comparer les périodes").check();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-01-02");

  await expect(page.getByTestId("echart")).toHaveAttribute("data-chart-series", "2", { timeout: 10000 });
});

// -------------------------------------------------------------------------
// Scénario 15 (SP-14e) — non-régression explicite : indicateur/graphique
// sans les nouvelles props se comportent exactement comme avant, y compris
// avec une plage temporelle active.
// -------------------------------------------------------------------------
test("indicator and chart behave exactly as before without the new SP-14e props, even with an active time range", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-05" } }, { id: 2, properties: { nom: "B", date: "2026-01-20" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 2 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "Non-régression KPI/Chart");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("line");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");

  await expect(page.getByText("2")).toBeVisible();
  await expect(page.getByTestId("echart")).toHaveAttribute("data-chart-series", "1");
});
```

- [ ] **Step 2: Run the new scenarios**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/analytics-context.spec.ts -g "SP-14e|KPI|compare-periods|behave exactly as before without the new SP-14e"`
Expected: PASS (scenarios 12-15)

- [ ] **Step 3: Run the full E2E suite for non-regression**

Run: `cd shell && npm run e2e`
Expected: PASS — all 18+ specs (including the full `analytics-context.spec.ts`, now 15 scenarios) stay green.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover KPI delta, CEL threshold pastille, chart compare-periods, non-regression (SP-14e)"
```

---

## Final verification

- [ ] Run the complete cross-stack suite one more time before declaring the branch done:

```bash
cd core && uv run pytest
cd ../shell && npm run test && npm run build && npm run e2e
```

Expected: all green — 606+4 core tests, 61+ shell unit test files, `tsc --noEmit` + `vite build` clean, 18+ E2E specs (15 scenarios in `analytics-context.spec.ts`).
