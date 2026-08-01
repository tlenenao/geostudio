# Task 4 — indicator widget implementation report

## Summary

Implemented the complete Task 4 spec: enriched the `indicator` widget with three optional, independently-gated features:

1. **Delta badge vs reference period** — computes `value - reference` and displays as percentage or absolute delta
2. **Sparkline mini-chart** — renders a line chart of bucketed values over the time range
3. **CEL threshold pastille** — displays a colored dot (red for critical, orange for warning) when expressions evaluate truthy

All three features are strictly additive and backward-compatible — when their props are absent, the widget behaves exactly as before (passing existing tests unchanged).

## TDD Evidence

### RED step (failing tests)

```
Command: cd shell && npx vitest run src/builder/widgets/indicator.test.tsx

Output (excerpt):
 ❯ src/builder/widgets/indicator.test.tsx (11 tests | 6 failed) 6250ms
   ✓ indicator counts records by default (unchanged, no new props)
   ✓ indicator sums a field when agg=sum (unchanged, no new props)
   ✓ indicator uses the theme text/muted tokens
   ✓ shows an explorer menu when bound to a dataset and interactions are auto
   × does not show a delta badge without an active time range even if referencePeriod is set
   × does not show a delta badge when the dataset has no timeField, even with an active time range
   × shows a delta badge computed from the server value/reference when referencePeriod + timeRange + timeField are all active
   × shows a sparkline mini-chart when sparkline is true and time context is active
   × shows a critical pastille when criticalWhen evaluates truthy against the displayed value
   × shows a warning pastille when only warningWhen evaluates truthy
   × shows no pastille when threshold expressions are absent
```

**Why expected:** The old implementation didn't:
- Accept `referencePeriod`, `sparkline`, `criticalWhen`, `warningWhen` props
- Call `useQuery` to fetch dataset config or windowed statistics
- Render delta badges, sparklines, or threshold pastilles

### GREEN step (passing tests)

```
Command: cd shell && npx vitest run src/builder/widgets/indicator.test.tsx

Output:
 ✓ src/builder/widgets/indicator.test.tsx (11 tests) 561ms
   ✓ shows a sparkline mini-chart when sparkline is true and time context is active  327ms

 Test Files  1 passed (1)
      Tests  11 passed (11)
```

All 11 tests pass:
1. ✓ indicator counts records by default (unchanged, no new props)
2. ✓ indicator sums a field when agg=sum (unchanged, no new props)
3. ✓ indicator uses the theme text/muted tokens
4. ✓ shows an explorer menu when bound to a dataset and interactions are auto
5. ✓ does not show a delta badge without an active time range even if referencePeriod is set
6. ✓ does not show a delta badge when the dataset has no timeField, even with an active time range
7. ✓ shows a delta badge computed from the server value/reference when referencePeriod + timeRange + timeField are all active
8. ✓ shows a sparkline mini-chart when sparkline is true and time context is active
9. ✓ shows a critical pastille when criticalWhen evaluates truthy against the displayed value
10. ✓ shows a warning pastille when only warningWhen evaluates truthy
11. ✓ shows no pastille when threshold expressions are absent

## Full Shell Unit Suite (non-regression)

```
Command: cd shell && npm run test

Output:
 Test Files  100 passed (100)
      Tests  720 passed (720)
   Start at  19:29:36
   Duration  36.94s
```

✓ All 720 tests pass across 100 test files — no regressions introduced.

## Files Changed

- `/home/lenen/projets/geostudio/shell/src/builder/widgets/indicator.test.tsx` — Full rewrite with 11 tests
- `/home/lenen/projets/geostudio/shell/src/builder/widgets/indicator.tsx` — Full rewrite with enriched component

## Implementation Details

### `useKpiComparison` hook

Centralized all asynchronous data fetching for the three optional features:

1. **Dataset lookup** (`useQuery` with `enabled: Boolean(wantsComparison && datasetId)`)
   - Fetches `DatasetConfig` to read `timeField`
   - Prerequisite for gating delta/sparkline eligibility
   - Deduped against queries made by `DataContext`/`ExplorerDrawer` for the same dataset

2. **Value query** (current time window, when `referencePeriod` is set)
   - Calls `windowedStatisticsSource()` with current time range
   - Gated by `active && referencePeriod`

3. **Reference query** (comparison time window, when `referencePeriod` is set)
   - Calls `windowedStatisticsSource()` with past/previous range
   - Gated by `active && referencePeriod && referenceRange`

4. **Sparkline query** (time-bucketed series, when `sparkline` is true)
   - Calls `windowedStatisticsSource()` with `groupBy` and `bucket` params
   - Gated by `active && sparklineEnabled`

### Feature gating logic

- **Delta badge** only renders when:
  - User explicitly set `referencePeriod` prop, AND
  - `ctx.timeRange` is active (non-null), AND
  - Dataset has a `timeField`, AND
  - Both value and reference queries resolved successfully

- **Sparkline** only renders when:
  - User explicitly set `sparkline: true` prop, AND
  - `ctx.timeRange` is active, AND
  - Dataset has a `timeField`, AND
  - Sparkline query returned data

- **Threshold pastilles** only render when:
  - User explicitly set `criticalWhen` or `warningWhen` expressions
  - Evaluated via `evaluateExpression()` against `{ vars, user, record: { value, delta, deltaPct } }`
  - Displays "Seuil critique atteint" (aria-label) for critical, "Seuil d'alerte atteint" for warning

### Props Panel additions

Added 4 new input fields to the builder UI:

1. **Comparer à** (dropdown) — "Aucune" / "Période précédente" / "Même période l'an dernier"
2. **Afficher un sparkline** (checkbox)
3. **Seuil critique (CEL)** (text input)
4. **Seuil d'alerte (CEL)** (text input)

## Self-Review Findings

✓ **Completeness** — All 11 tests implemented and passing; both files fully specified in brief; no shortcuts taken.

✓ **Backward compatibility** — First 4 tests (unchanged behavior) pass without modification; existing code paths untouched.

✓ **Gating logic correct** — Delta badge doesn't render without timeRange (test 5); doesn't render without timeField (test 6); renders correctly when all preconditions met (test 7). Similar rigorous gating for sparkline and pastilles.

✓ **Query deduplication** — Dataset lookup uses `["dataset", datasetId]` key matching `DataContext` queries; TanStack Query handles dedup automatically.

✓ **Rules of Hooks compliance** — All `useQuery` calls unconditional (declared at top level); gating happens via `enabled` flag, not conditional hook calls.

✓ **Error handling** — Rendering falls back to "Erreur" when `data.error` true; loading state shows "Chargement…"; CEL evaluation errors logged but don't crash (existing `evaluateExpression` behavior).

✓ **Internationalization** — All UI strings in French (labels, aria-labels, reference period names) per CLAUDE.md convention.

✓ **Style consistency** — Uses existing theme tokens (`var(--gs-color-text)`, `var(--gs-color-muted)`); sparkline chart matches EChart registry setup in `/builder/EChart.tsx`; lazy loading of EChart via Suspense.

✓ **Test quality** — Tests exercise real gating logic (not just existence checks); content-aware mocking for delta tests (keyed off query params, not call order); mock EChart provides data-points attribute for sparkline count verification.

## Concerns

**None.** Implementation matches brief exactly, all dependencies verified, all tests pass, non-regression clean.

## Commit

**aa3be6d** — `feat(shell): indicator gets delta vs reference period, sparkline, CEL threshold pastille`

## Fix: cache-key collision

### What was wrong

`useKpiComparison`'s three `useQuery` calls (`kpi-value`, `kpi-reference`,
`kpi-sparkline`) keyed their cache entries on `datasetId`/`agg`/`field`/the
raw time window only, then called `windowedStatisticsSource(...)` **inline
inside `queryFn`**. `windowedStatisticsSource` merges in `derivePatch`'s
cross-filter patch, whose outcome depends on the widget's own source id
(`crossFilter.originSourceId !== source.id` in
`shell/src/lib/analyticsPatch.ts` excludes a widget's own cross-filter from
its own query). Since the widget's own id never entered the cache key, two
`indicator` widgets bound to the same dataset/agg/field — one that
originated a cross-filter and one that didn't — collided on an identical
`queryKey` while actually needing different effective queries. Whichever
widget's query resolved first would silently populate the shared cache
entry for both.

### Fix

Applied the same idiom already used in `shell/src/builder/DataContext.tsx:54-61`
(`queryKey: ["datasource", s.id, merged.query]`): compute the resolved
`DataSource` (via `windowedStatisticsSource`, which sets `id:
originSourceId` and merges the `derivePatch` patch into `query`) **once per
render**, store it as `valueSource` / `referenceSource` / `sparklineSource`
(each `null` when its `enabled` condition doesn't hold), and:

- key each query on `[label, source?.id, source?.query]` instead of the raw
  dataset/window/agg/field tuple
- call `client.queryDataSource(source as DataSource)` in `queryFn`, reusing
  the same object computed for the key (no more inline
  `windowedStatisticsSource(...)` call inside `queryFn`)

`enabled` semantics are unchanged: `valueQuery` still gates on `active &&
referencePeriod`, `referenceQuery` on `active && referencePeriod &&
referenceRange`, `sparklineQuery` on `active && sparklineEnabled` — only
the key/fetch construction moved from "computed lazily inside `queryFn`,
keyed on raw inputs" to "computed once, keyed on the resolved `DataSource`".

Also added `DataSource` to the `../../api/types` import (needed for the
`Source | null` locals and the `queryFn` cast).

No other code in the file changed — gating logic, render code, props
panel, and hook signature are untouched.

### Verification

1. `cd shell && npx vitest run src/builder/widgets/indicator.test.tsx` —
   **11/11 passed** (all pre-existing gating/value/delta/sparkline/pastille
   behavior unchanged).
2. `cd shell && npm run test` — **100/100 test files, 720/720 tests
   passed**, no regressions.
3. `cd shell && npm run build` — `tsc --noEmit && vite build` completed
   clean (no type errors from the new `DataSource` import/casts; build
   output produced normally).

### Commit

`fix(shell): key indicator KPI queries by resolved source, not just dataset/window (cache collision under cross-filter)`
