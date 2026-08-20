# Task 7 Report — Shell: `registry.ts` gains `configSchema`, backfill 22 builtin widgets

## What was implemented

1. New shared type `shell/src/builder/widgetPropSchema.ts` exporting
   `WidgetPropDescriptor` (`{ name, type: "string"|"number"|"boolean"|"dataSource", label, default }`).
2. `WidgetDefinition` in `shell/src/builder/registry.ts` gains an optional
   `configSchema?: WidgetPropDescriptor[]` field (with the doc comment from
   the brief explaining scope: scalar props only, array/object props out of
   scope for v1).
3. Backfilled `configSchema` on all 22 builtin widget definitions across 19
   widget files, exactly per the brief's per-file snippets:
   - `dateRangeFilter.tsx` (dateRangeFilter)
   - `datasetCard.tsx` (datasetCard)
   - `chart.tsx` (chart — 15 scalar props)
   - `data.tsx` (list, table — two widgets)
   - `drawer.tsx` (drawer)
   - `indicator.tsx` (indicator)
   - `index.tsx` (text, image, button — three widgets)
   - `gallery.tsx` (gallery)
   - `hero.tsx` (hero)
   - `richSection.tsx` (richSection)
   - `filter.tsx` (filter)
   - `selectFilter.tsx` (selectFilter)
   - `mapWidget.tsx` (map)
   - `navigation.tsx` (nav)
   - `modal.tsx` (modal)
   - `tabs.tsx` (tabs — empty `configSchema: []`, only prop `tabs` is array-shaped)
   - `sliderFilter.tsx` (sliderFilter)
   - `form.tsx` (form — only `dataSourceId`/`submitLabel`, `fields` array and
     `geometryType` nullable enum excluded per brief)
   - `pivot.tsx` (pivot — `encodings` object excluded per brief)
4. New test file `shell/src/builder/widgetPropSchema.test.ts`, verbatim from
   the brief.

No widget runtime behavior changed — purely additive static metadata.

## Pre-flight check

Before editing, verified every one of the brief's "Change:"/"to:" snippets
against the actual current file contents (`registry.ts` imports/type, and
every `defaultProps`/`defaultSize` block in all 19 widget files) via `grep`
and targeted `Read`. All matched exactly — no deviations, no need to escalate.

## TDD evidence

### RED

Command: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts`

Result: 4/4 tests failed. (Note: the failure was "expected undefined" for
`configSchema`, not literally "Cannot find module" as the brief's Step 2
predicted — because the test file itself doesn't import from
`./widgetPropSchema` directly, only `registry`/`widgets`. The failure reason
is correct either way: the feature doesn't exist yet.)

```
FAIL  src/builder/widgetPropSchema.test.ts > configSchema > tabs widget has an empty configSchema...
AssertionError: expected undefined to deeply equal []
 Test Files  1 failed (1)
      Tests  4 failed (4)
```

### GREEN

Command: `cd shell && npx vitest run src/builder/widgetPropSchema.test.ts src/builder/registry.test.tsx`

```
✓ src/builder/widgetPropSchema.test.ts (4 tests) 17ms
✓ src/builder/registry.test.tsx (4 tests) 134ms

 Test Files  2 passed (2)
      Tests  8 passed (8)
```

## Full verification

- `cd shell && npm run build` → `tsc --noEmit && vite build` — PASS (build
  succeeded, only pre-existing chunk-size warnings, unrelated to this change).
- `cd shell && npm run test` → **147 test files passed, 1215 tests passed**,
  0 failed. (Stderr showed some `CelParseError` output during the run — this
  is expected console noise from `exprBindings.test.ts`'s own error-path
  test, which itself passed.)

## Confirmation: all 22 widgets covered

Verified programmatically (not just by eye):
- `grep -rc "defaultProps:" *.tsx` sums to **22** across the widget files.
- `grep -rc "configSchema:" *.tsx` sums to **22** — one `configSchema` per
  `defaultProps`, no widget skipped.
- The test `"every builtin widget declares a configSchema (possibly empty)"`
  iterates `listWidgets()` (the full runtime registry after
  `registerBuiltinWidgets()`) and asserts each has a defined `configSchema` —
  this passed, which is the strongest form of confirmation since it goes
  through actual widget registration rather than static grep.

All 22 widget types: dateRangeFilter, datasetCard, chart, list, table,
drawer, indicator, text, image, button, gallery, hero, richSection, filter,
selectFilter, map, nav, modal, tabs, sliderFilter, form, pivot.

## Files changed

- `shell/src/builder/widgetPropSchema.ts` (new)
- `shell/src/builder/widgetPropSchema.test.ts` (new)
- `shell/src/builder/registry.ts`
- `shell/src/builder/widgets/chart.tsx`
- `shell/src/builder/widgets/data.tsx`
- `shell/src/builder/widgets/datasetCard.tsx`
- `shell/src/builder/widgets/dateRangeFilter.tsx`
- `shell/src/builder/widgets/drawer.tsx`
- `shell/src/builder/widgets/filter.tsx`
- `shell/src/builder/widgets/form.tsx`
- `shell/src/builder/widgets/gallery.tsx`
- `shell/src/builder/widgets/hero.tsx`
- `shell/src/builder/widgets/index.tsx`
- `shell/src/builder/widgets/indicator.tsx`
- `shell/src/builder/widgets/mapWidget.tsx`
- `shell/src/builder/widgets/modal.tsx`
- `shell/src/builder/widgets/navigation.tsx`
- `shell/src/builder/widgets/pivot.tsx`
- `shell/src/builder/widgets/richSection.tsx`
- `shell/src/builder/widgets/selectFilter.tsx`
- `shell/src/builder/widgets/sliderFilter.tsx`
- `shell/src/builder/widgets/tabs.tsx`

22 files total (matches `git commit` output: "22 files changed, 157
insertions(+)").

## Self-review findings

No deviations from the brief were needed. All snippets matched the live
files exactly on first read. No issues found in self-review:
- Every `configSchema` array's entries match the corresponding
  `defaultProps` key/value for `default`, in the same declared order as the
  brief.
- `tabs.tsx` correctly gets `configSchema: []` (not omitted), matching the
  explicit test for it.
- `form.tsx` and `pivot.tsx` correctly exclude their array/object-shaped
  props (`fields`/`geometryType`, `encodings`) with the exact explanatory
  comments from the brief.
- Commit only staged the intended files (`widgetPropSchema.ts`,
  `registry.ts`, `widgets/`, `widgetPropSchema.test.ts`) — pre-existing
  unrelated unstaged changes in the working tree (`.superpowers/sdd/*`,
  `deploy/postgis/*`) were left untouched, not part of this task.

## Issues or concerns

None. Task complete as specified, no scope creep, no ambiguity encountered.
