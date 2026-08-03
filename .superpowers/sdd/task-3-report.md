# Task 3 report — `map` widget: color/size encodings, domain queries, legend overlay (SP-14h)

## What was implemented

Replaced the full contents of both target files with the literal code given in the brief, no deviations required:

- `shell/src/builder/widgets/mapWidget.test.tsx` — rewritten with `QueryClient`/`ItemClientProvider` wiring in every Component-rendering test (via a `withClient` helper), plus 4 new tests: PropsPanel color/size encoding edits, categorical color domain resolving to a `fill-color` match expression + legend, numeric color+size domains resolving to `circle-color`/`circle-radius` on point geometry, and the "no legend when unconfigured" case.
- `shell/src/builder/widgets/mapWidget.tsx` — the `PropsPanel` gained "Champ couleur" / "Type de couleur" / "Champ taille" fields backed by a `MapEncodings` merge helper; the `Component` now calls `useItemClient()` and three `useQuery` calls (one categorical `groupBy` domain query, and two numeric min/max domain queries via a shared `useNumericDomain` helper — one for color, one for size), feeds the resolved domains into `buildMapPaint`/`buildLegend`/`detectGeometryKind` from `mapSymbology.ts` (Task 1), passes `renderAs`/`paint` through to the `MapLayer` (Task 2's `renderAs` field), and renders a `MapSymbologyLegend` overlay in the bottom-right corner when a legend spec is produced.

No changes to `mapSymbology.ts`, `MapView.tsx`, `types.ts`, or `index.tsx` — those were already correct from Tasks 1 and 2.

## TDD Evidence

### RED — `cd shell && npm run test -- mapWidget.test.tsx` (before Step 3)

```
Test Files  1 failed (1)
     Tests  4 failed | 11 passed (15)
```

The 4 failures were exactly the ones the brief predicted: the categorical-color-domain test, the numeric-color+size test, the "no legend" negative assertion not yet meaningful, and the categorical-legend test — all failing because `PropsPanel` had no color/size fields yet and `Component` never queried a domain or rendered `renderAs`/`paint`/a legend. (The other 11 pre-existing behavior tests — bus events, flyTo/highlight, explorer, cross-filter — already passed since `ItemClientProvider`/`QueryClientProvider` wrapping alone doesn't break unrelated behavior.)

### GREEN — `cd shell && npm run test -- mapWidget.test.tsx` (after Step 3)

```
 ✓ src/builder/widgets/mapWidget.test.tsx (15 tests) 723ms
 Test Files  1 passed (1)
      Tests  15 passed (15)
```

### Full suite — `cd shell && npm run test`

```
 Test Files  104 passed (104)
      Tests  792 passed (792)
```

All existing suites remain green, including `mapSymbology.test.ts` (14 tests, Task 1) and the rewritten `mapWidget.test.tsx` (15 tests). No regressions. (Some unrelated pre-existing tests print expected `stderr` noise from exercising CEL error paths and a throwing ActionBus handler — this is pre-existing, intentional test behavior, not new warnings from this change.)

### tsc — `cd shell && npx tsc --noEmit -p tsconfig.json`

No output — clean, zero type errors. Unlike Task 2, the brief's literal code for this task type-checked cleanly with no fixes needed.

## Files changed

- `shell/src/builder/widgets/mapWidget.tsx` (modified)
- `shell/src/builder/widgets/mapWidget.test.tsx` (modified)

Commit: `e05744e` — `feat(shell): map widget colors and sizes features from dataset encodings, with a legend (SP-14h)`

Verified via `git show e05744e --stat` that exactly these two files changed (159/126 lines respectively), and confirmed via `git status` before committing that no other pending working-tree changes (`.superpowers/sdd/*`, the untracked plan doc) got swept into the commit — those belong to other in-flight work and were left untouched.

## Self-review

- **Completeness**: all 15 tests from the brief implemented verbatim and passing; full suite green (792/792); tsc clean.
- **Quality**: widget follows existing conventions — `PropsPanel`/`Component` split, `labelCls`/`inputCls` shared style constants matching other widgets (e.g. `sliderFilter.tsx`), `useNumericDomain` factored out to avoid duplicating the color/size min-max query boilerplate, domain queries follow the exact `statistics`/`DataSource` pattern already used by `sliderFilter.tsx`.
- **Discipline**: only the two files named in the brief were touched; no edits to `mapSymbology.ts`, `MapView.tsx`, `types.ts`, or `index.tsx`.
- **Testing**: test run output is pristine for this file (no warnings); the only stderr in the full-suite run comes from pre-existing, unrelated tests intentionally exercising error paths (CEL evaluation errors, a throwing ActionBus handler) — not introduced by this change.

## Concerns

None. The brief's literal code for both files worked as given — no bugs found, no deviations needed.
