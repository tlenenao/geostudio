## Task 3 report: Wire `ExplorerMenu` into the 5 eligible widgets

### What I implemented

Wired the existing `<ExplorerMenu>` component (from Task 2) into all 5 data-bound
widget render paths, exactly as described in the brief — no deviations. The
actual current file contents matched the brief's line ranges almost exactly
(off by 1-2 lines at most, e.g. the `data.tsx` type import was on line 9, the
`table` return block started at line 190 as described), so all edits are
verbatim from the brief:

- `shell/src/builder/widgets/chart.tsx` — import `ExplorerMenu` after the
  `chartOption` import; wrapped the `Suspense` in `<div className="relative h-full">`
  with `<ExplorerMenu datasetId={data.datasetId} dataSourceId={String(props.dataSourceId ?? "")} />`
  as first child.
- `shell/src/builder/widgets/data.tsx` — import after the `DataRecord` type
  import; same wrap pattern for both the `list` widget's `<ul>` return and the
  `table` widget's return (added `relative` to the existing
  `flex h-full flex-col text-xs` wrapper div and inserted the menu as first
  child, right before the `<table>`).
- `shell/src/builder/widgets/mapWidget.tsx` — import after the `MapViewHandle`
  type import; wrapped the `Suspense`/`MapView` in a `relative h-full` div,
  using `ctx.data?.datasetId` (map's component reads `ctx.data` directly, not a
  destructured `data` local, matching the brief).
- `shell/src/builder/widgets/indicator.tsx` — import after `DataSourceSelect`;
  added `relative` to the existing centered flex wrapper and inserted the menu
  as first child.

### What I tested

Added the 4 new tests exactly as specified in the brief (1 in chart.test.tsx,
2 in data.test.tsx for `list` and `table`, 1 in mapWidget.test.tsx, 1 in
indicator.test.tsx), each rendering the widget inside `<ExplorerProvider enabled>`
with a dataset-bound `ctx.data` and asserting `screen.findByLabelText("Explorer")`
resolves.

### TDD Evidence

**RED** — `cd shell && npx vitest run src/builder/widgets/chart.test.tsx src/builder/widgets/data.test.tsx src/builder/widgets/mapWidget.test.tsx src/builder/widgets/indicator.test.tsx`
```
Test Files  4 failed (4)
     Tests  5 failed | 36 passed (41)
```
All 5 new tests failed with `TestingLibraryElementError: Unable to find a label
with the text of: Explorer`; all 36 pre-existing tests in these 4 files passed
unchanged.

**GREEN** — same command after implementation:
```
✓ src/builder/widgets/indicator.test.tsx (4 tests) 67ms
✓ src/builder/widgets/data.test.tsx (19 tests) 438ms
✓ src/builder/widgets/mapWidget.test.tsx (9 tests) 481ms
✓ src/builder/widgets/chart.test.tsx (9 tests) 516ms
Test Files  4 passed (4)
     Tests  41 passed (41)
```

Full suite — `cd shell && npm run test`:
```
Test Files  98 passed (98)
     Tests  693 passed (693)
```
(The stderr output visible during the run is expected console noise from an
existing CEL-parse-error test in `exprBindings.test.ts`, unrelated to this
change — no failures.)

Typecheck — `cd shell && npx tsc --noEmit` — clean, no output.

### Files changed

- `shell/src/builder/widgets/chart.tsx`
- `shell/src/builder/widgets/chart.test.tsx`
- `shell/src/builder/widgets/data.tsx`
- `shell/src/builder/widgets/data.test.tsx`
- `shell/src/builder/widgets/mapWidget.tsx`
- `shell/src/builder/widgets/mapWidget.test.tsx`
- `shell/src/builder/widgets/indicator.tsx`
- `shell/src/builder/widgets/indicator.test.tsx`

Commit: `c048d6c` — `feat(shell): wire the explorer menu into chart/table/list/map/indicator (SP-14d)`

### Self-review

- Completeness: all 5 widget render paths (chart, list, table, map, indicator)
  now render `<ExplorerMenu>` as the first child of a `relative`-positioned
  wrapper; confirmed via the diff and via the passing tests for each.
- Quality: matches repo conventions (import grouping, className patterns,
  `String(props.dataSourceId ?? "")` idiom already used elsewhere in these
  files for cross-filter calls). `aria-label="Explorer"` comes from
  `ExplorerMenu` itself (Task 2), verified present via `findByLabelText`.
- Discipline: no refactors beyond adding the import + wrapping div + menu
  element in each file; no changes to unrelated widgets, no changes to
  `ExplorerContext.tsx` or `ExplorerMenu.tsx`.
- Testing: 4 new tests (5 assertions across list+table) pass; full suite
  (98 files / 693 tests) has zero regressions; `git status --short` confirmed
  only the 8 intended files were touched by this task before committing.

### Issues or concerns

None. The brief's line numbers matched the actual files closely enough that no
judgment calls were needed beyond straightforward whitespace/line-number
drift.
