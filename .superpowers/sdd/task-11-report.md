# Task 11 report — Shell: wire `mapWidget.tsx` onto `LayerSymbology`

## What I found in the real files before editing

- `shell/src/builder/widgets/mapWidget.tsx` (307 lines pre-edit) matched the
  brief's assumptions closely: `PropsPanel` had three hand-rolled inputs
  (`Champ couleur`/`Type de couleur`/`Champ taille`) writing to
  `props.encodings`, plus the shared `PopupEditor`. `Component` had a local
  `useNumericDomain` hook and two `useQuery` calls (`categoricalQuery`,
  `numericColorQuery` via `useNumericDomain`, `sizeQuery` via
  `useNumericDomain`) hitting `client.queryDataSource` at every render when a
  color/size field was configured. `MapSymbologyLegend` only handled
  `"categorical"`/`"numeric"` legend kinds, not `"classed"`.
- `shell/src/map/MapSymbologyEditor.tsx` (Task 7, 259 lines pre-edit) matched
  the brief exactly: `recomputeColor`'s `try`/`finally` had no `catch`, so a
  rejected `computeColorDomain` (e.g. the widget's `sampleField` throwing on
  Jenks) would propagate as an unhandled rejection with no visible feedback,
  though `finally` did still reset `busy` (button re-enables, doesn't hang
  disabled).
- `shell/src/map/LayersPanel.tsx` confirmed the precedent for how the other
  host (map editor) wires `runStatistics`/`sampleField` through a direct
  `collectionId`, which is exactly the asymmetry the brief cites for why
  Jenks is out of scope on the widget's `datasetId`-based surface.
- `shell/src/builder/widgets/mapSymbology.ts` confirmed
  `symbologyToPaintInputs`/`buildMapPaint`/`buildLegend`/`detectGeometryKind`
  signatures, `LayerSymbology`/`LegendSpec` shapes (including the `"classed"`
  legend kind already defined there), and that `buildMapPaint`/`buildLegend`
  already accept an optional `ResolvedPalette` fifth argument.
- `shell/src/builder/widgets/palette.ts` confirmed `resolvePalette("theme-primary", {primary: "#2563eb"})` returns `{kind: "sequential", low: "#ffffff", high: "#2563eb"}` — the value the new theme test asserts on.
- `shell/src/builder/registry.ts` confirmed `theme?: Theme` is already present
  on both `PropsPanel`'s prop type and `WidgetContext` (Task 10's output),
  so no registry changes were needed.

Nothing diverged substantially from the brief's assumptions — no escalation
needed.

## What I implemented

1. **`mapWidget.test.tsx`** — rewrote/added tests per the brief's Step 2:
   - Removed `"PropsPanel edits the color and size encodings"` (old UI gone).
   - Added `"PropsPanel mounts MapSymbologyEditor with theme from props"`.
   - Added `"choosing Jenks from the widget's PropsPanel surfaces an error
     instead of hanging"` (asserts the `role="alert"` message text and that
     the button re-enables afterwards).
   - Replaced `"colors features by a categorical field once the domain query
     resolves"` with `"Component renders paint from frozen props.symbology,
     without querying any domain"` (uses `props.symbology`, asserts
     `queryDataSource` never called).
   - Replaced `"colors and sizes point features by numeric fields once both
     domain queries resolve"` with `"colors and sizes point features from
     frozen size/color symbology, without querying any domain"` (same
     pattern, color+size together).
   - Added `"Component resolves the theme-primary palette from ctx.theme at
     render time"` — palette `"theme-primary"`, `ctx.theme.colors.primary =
     "#2563eb"`, asserts the interpolate expression's high stop is
     `"#2563eb"` and explicitly asserts it does **not** contain `"#1e3a8a"`
     (the hardcoded `sequential-blue`/default numeric-high color that would
     render if `ctx.theme` weren't threaded through).
   - Replaced `"shows a categorical symbology legend once the color domain
     resolves"` with `"shows a categorical symbology legend from frozen
     props.symbology"`.
   - `renderPropsPanel` helper extended with an optional `theme` param
     (typed `Theme`, imported from `../../api/types`).
   - Removed the now-unused `waitFor` import (no async domain-query waiting
     remains).

2. **`mapWidget.tsx`** — rewrote `PropsPanel` and `Component` verbatim per
   the brief's given code:
   - `PropsPanel` now mounts `DataSourceSelect` → `MapSymbologyEditor`
     (`value={props.symbology}`, `availableFields={[]}`,
     `themeColors={theme?.colors}`, `runStatistics` resolving through
     `datasetId` exactly as the old domain queries did, `sampleField`
     throwing `"Jenks sur le widget carte nécessite un collectionId résolu
     — non câblé"`) → `PopupEditor`, unchanged from before.
   - `Component` now reads `props.symbology` (cast to `LayerSymbology |
     undefined`), calls `symbologyToPaintInputs(symbology, ctx.theme?.colors)`
     once, feeds the result straight into `buildMapPaint`/`buildLegend`
     alongside `detectGeometryKind`. Zero `useQuery`/`client.queryDataSource`
     calls in `Component`.
   - Removed: `useNumericDomain`, both domain `useQuery`s, the `useQuery`
     import, `MapEncodings`/`ColorDomain`/`SizeDomain` type imports (verified
     unused elsewhere in the file — see grep below), the `ItemClient` type
     import (was only used as `useNumericDomain`'s parameter type; nothing
     else in the file references it since `client` now comes from
     `useItemClient()` with an inferred type), and the now-dead
     `labelCls`/`inputCls` constants (only used by the removed hand-rolled
     inputs).
   - `MapSymbologyLegend` gained the `"classed"` branch (bullet list of
     `from`–`to` ranges with a color swatch), exactly as given in the brief.

3. **`MapSymbologyEditor.tsx`** — added `error` state, `setError(null)` at
   the top of `recomputeColor`'s `try`, a `catch` block setting the error
   message, and `{error && <p role="alert" ...>{error}</p>}` rendered right
   after the "Recalculer les classes" button (prettier reformatted this to a
   multi-line JSX block — functionally identical to the brief's inline
   form).

4. **`MapSymbologyEditor.test.tsx`** — added the retroactive
   `"a failing recompute surfaces an error instead of hanging silently"`
   test exactly as given in the brief (rejecting `runStatistics`, asserting
   `role="alert"` with text "boom").

## TDD evidence

**Baseline** (before any test edits), to establish the reference count:
```
$ npx vitest run src/builder/widgets/mapWidget.test.tsx src/map/MapSymbologyEditor.test.tsx
✓ src/map/MapSymbologyEditor.test.tsx (8 tests) 204ms
✓ src/builder/widgets/mapWidget.test.tsx (19 tests) 730ms
Test Files  2 passed (2)
     Tests  27 passed (27)
```

**RED** (tests updated, implementation NOT yet touched):
```
$ npx vitest run src/builder/widgets/mapWidget.test.tsx
 FAIL  src/builder/widgets/mapWidget.test.tsx > PropsPanel mounts MapSymbologyEditor with theme from props
 FAIL  src/builder/widgets/mapWidget.test.tsx > choosing Jenks from the widget's PropsPanel surfaces an error instead of hanging
 FAIL  src/builder/widgets/mapWidget.test.tsx > Component renders paint from frozen props.symbology, without querying any domain
 FAIL  src/builder/widgets/mapWidget.test.tsx > colors and sizes point features from frozen size/color symbology, without querying any domain
 FAIL  src/builder/widgets/mapWidget.test.tsx > Component resolves the theme-primary palette from ctx.theme at render time
 FAIL  src/builder/widgets/mapWidget.test.tsx > shows a categorical symbology legend from frozen props.symbology
 Test Files  1 failed (1)
      Tests  6 failed | 15 passed (21)
```
All 15 pre-existing/untouched tests still passed at this point (proves the
test-file rewrite didn't collaterally break anything); exactly the 6
new/rewritten tests failed against the not-yet-updated implementation, as
expected.

**GREEN** (after implementing `PropsPanel`/`Component`/`MapSymbologyEditor`):
```
$ npx vitest run src/builder/widgets/mapWidget.test.tsx src/map/MapSymbologyEditor.test.tsx
✓ src/map/MapSymbologyEditor.test.tsx (9 tests) 234ms
✓ src/builder/widgets/mapWidget.test.tsx (21 tests) 677ms
Test Files  2 passed (2)
     Tests  30 passed (30)
```

## Confirmation: Task 7's 8 pre-existing `MapSymbologyEditor` tests still pass

All 8 original tests (`no color field selected...`, `theme-primary palette
option is absent...`/`...is present...`, `classification method selector is
hidden.../shown...`, `class count selector is hidden...`, `recompute button
calls runStatistics...`, `recompute button for the size field...`, `computed
breaks are shown as text`) are present unmodified in the file and are part
of the 9 passing in the GREEN run above (9 = 8 original + 1 new retroactive
error test).

## Confirmation: `Component` makes zero domain-fetch network calls at render

- `grep -n "useQuery\|queryDataSource" src/builder/widgets/mapWidget.tsx`
  returns exactly one hit: `client.queryDataSource(` inside `PropsPanel`'s
  `runStatistics` closure (the author-time recompute path, invoked only when
  an author clicks "Recalculer les classes"/"Recalculer la taille" in the
  editor) — zero occurrences inside `Component`.
- Every new/rewritten `Component` test that sets `props.symbology` asserts
  `expect(queryDataSource).not.toHaveBeenCalled()` (or passes a bare
  `vi.fn()` that is never invoked) after the render settles.

## Full shell gates output summary

- `npm run lint` → clean (no output, exit 0).
- `npm run format:check` → one file needed reformatting after my edit
  (`MapSymbologyEditor.tsx`, prettier wrapped the new `<p role="alert">`
  JSX onto multiple lines); ran `npx prettier --write` on it, then
  `format:check` passed clean.
- `npx vitest run` (full suite) → **161 files passed, 1426 tests passed**
  (reference was 161 files / 1423 tests after Task 10 — net +3 matches
  exactly: +2 `mapWidget.test.tsx`, +1 `MapSymbologyEditor.test.tsx`).
- `npm run build` → green (`tsc --noEmit && vite build` succeeded; only
  pre-existing chunk-size warnings, unrelated to this change).

## Files changed

- `/home/lenen/projets/geostudio/shell/src/builder/widgets/mapWidget.tsx`
- `/home/lenen/projets/geostudio/shell/src/builder/widgets/mapWidget.test.tsx`
- `/home/lenen/projets/geostudio/shell/src/map/MapSymbologyEditor.tsx`
- `/home/lenen/projets/geostudio/shell/src/map/MapSymbologyEditor.test.tsx`

Commit: `e2a0a74 feat(shell): le widget carte utilise LayerSymbology au lieu d'encodings` (4 files changed, 223 insertions, 201 deletions).

## Deviations from the brief

None substantive. The only difference from the brief's literal code
snippets is cosmetic: prettier reformatted the `{error && <p role="alert"
...>{error}</p>}` line in `MapSymbologyEditor.tsx` onto three lines instead
of one — functionally identical, required to pass `format:check`.

## Self-review findings

- **Completeness**: `props.encodings` fully gone (grep confirms zero
  references in `mapWidget.tsx`); `useNumericDomain` and both old `useQuery`
  domain calls removed; `Component` makes zero `queryDataSource` calls at
  render (confirmed by grep + tests); `theme-primary` resolves correctly
  from `ctx.theme` at render (dedicated test, asserts both the correct color
  present and the wrong hardcoded default absent); Jenks throws a visible
  error via `role="alert"` and the button re-enables rather than hanging
  (dedicated test covers both).
- **Quality**: Implementation matches the brief's given code for
  `PropsPanel`, `Component`, and `MapSymbologyEditor`'s error handling
  essentially verbatim (only prettier's own line-wrapping differs).
  `MapSymbologyLegend`'s new `"classed"` branch renders correctly — not
  independently unit-tested in `mapWidget.test.tsx` (no test exercises a
  `numeric-classed` domain end-to-end through the widget), but it is a
  direct copy of the brief's given JSX driven by the same `legend.color`
  union already covered structurally by `mapSymbology.ts`'s own tests
  (`buildLegend` producing `"classed"` legends) — noted as a minor gap
  rather than silently omitted.
- **Discipline**: Exactly the 4 named files touched (`git status --porcelain
  -- shell/` confirmed before commit); no scope creep into
  `mapSymbology.ts`, `palette.ts`, `LayersPanel.tsx`, or registry files.
- **Testing**: RED then GREEN genuinely observed and captured above (not
  simulated); Task 7's 8 pre-existing tests still pass; full suite count
  matches the expected net delta exactly; output pristine (lint/format/build
  all clean after one prettier auto-fix).

## Concerns

- Minor, noted above: no dedicated `mapWidget.test.tsx` test exercises the
  new `"classed"` legend branch end-to-end (only `mapSymbology.test.ts`
  covers `buildLegend`'s `"classed"` output directly, and
  `MapSymbologyEditor.test.tsx`'s `"computed breaks are shown as text"`
  covers the *editor's* display of a classed domain, not the widget's
  rendered legend). Not blocking — the brief didn't explicitly ask for this
  additional test, and the branch is a direct copy of brief-given JSX over
  an already-tested data shape — but worth flagging for the final review
  pass.
