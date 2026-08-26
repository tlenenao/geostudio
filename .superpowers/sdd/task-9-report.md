# Task 9 report — MapView reads `layer.symbology` at render

## What I found in the real file before editing

Ran `grep -n "kind === \"vector\"\|kind === \"feature\"" shell/src/map/MapView.tsx`
→ lines 222 and 271 (post-SP-24 line numbers, close to the brief's ~222-296
estimate). Read `applyLayers` (lines 190-324) in full plus its helpers
(`layerTypeFor`, `MIXED_GEOMETRY_SUBLAYERS`, `paintFor`, `addTypedLayer`)
before writing any code, per Step 1.

Key structural facts confirmed:
- `vector` branch (SP-24 I1 split): when `layer.geometryKind` is `undefined`
  (unknown/mixed geometry), it loops `MIXED_GEOMETRY_SUBLAYERS` and calls
  `addTypedLayer(..., paint: paintFor(layer.paint, sub.paintPrefix))` per
  sub-layer (point/line/polygon), filtering by paint-key prefix. When
  `geometryKind` is known, it adds a single layer with
  `paint: layer.paint ?? {}`.
- `feature` branch: a `switch (layer.renderAs ?? "fill")` picks MapLibre
  layer type `circle`/`line`/`fill`, each arm passing `paint: layer.paint ?? {}`
  independently (three call sites, not a shared variable).
- `MapLayer` (`shell/src/api/types.ts`) already carries
  `symbology?: LayerSymbology` on both the `vector` and `feature` variants
  (from an earlier task in this plan).
- `mapSymbology.ts`'s `symbologyToPaintInputs(symbology, themeColors)` →
  `{encodings, colorDomain, sizeDomain, palette}`, and
  `buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette)`
  → `{renderAs, paint}` where `geometryKind: "point"|"line"|"polygon"`
  determines both `renderAs` and which single paint key (`circle-color`/
  `line-color`/`fill-color`) is populated.

One deviation from the brief's literal sketch, made deliberately (see
"Deviations" below): for the `feature` kind, the brief's Step 4 sketch code
hard-codes `geometryKind = "polygon"` with a comment "feature layers:
renderAs already carries geometry choice, see below" — but the prose right
below it says explicitly: "pass the render-as-implied geometry kind
consistently with whatever `applyLayers` already does today for that layer
kind... do not invent a new geometryKind inference here." Passing a fixed
`"polygon"` regardless of `renderAs` would make `buildMapPaint` always
populate `fill-color`, even when the actual MapLibre layer being added is
`type: "circle"` or `type: "line"` — MapLibre would reject `fill-color` on a
circle/line layer, and the per-layer `try/catch` in `applyLayers` would then
silently swallow the *entire* layer (console.error only). I resolved this by
mapping `layer.renderAs` → `geometryKind` for `buildMapPaint`'s purposes
(`"circle"` → `"point"`, `"line"` → `"line"`, default/`"fill"` → `"polygon"`)
so the produced paint key always matches the MapLibre layer type actually
added, mirroring the existing switch one line below.

## What I implemented

`shell/src/map/MapView.tsx`:
- New import: `buildMapPaint`, `symbologyToPaintInputs` from
  `../builder/widgets/mapSymbology`; `MapLayer` type import added.
- New helper `effectivePaint(layer: Extract<MapLayer, {kind: "vector"|"feature"}>)`:
  returns `layer.paint ?? {}` unchanged when no `symbology`; otherwise
  resolves the geometryKind per the rule above and returns
  `buildMapPaint(...).paint`.
- `vector` branch: `vectorPaint = effectivePaint(layer)` computed once per
  layer; the mixed-geometry loop now does `paintFor(vectorPaint, sub.paintPrefix)`
  instead of `paintFor(layer.paint, sub.paintPrefix)`; the known-geometryKind
  single-layer path uses `paint: vectorPaint` instead of `layer.paint ?? {}`.
  No change to the sub-layer splitting/filtering logic itself.
- `feature` branch: `featurePaint = effectivePaint(layer)` computed once
  before the `switch`; all three switch arms (`circle`/`line`/default `fill`)
  now use `paint: featurePaint` instead of each independently reading
  `layer.paint ?? {}`.

`shell/src/map/MapView.test.tsx`:
- New test `"a layer with symbology renders paint compiled from its frozen
  domain, ignoring any stale raw paint"`, added right after the closest
  existing paint-assertion test (`"defaults a feature layer to fill when
  renderAs is not set"`). Copied that test's exact render/`toMatchObject`
  mechanics; used the brief's exact `feature`-kind layer literal (stale
  `paint: {"fill-color": "#000000"}` + a `sequential-blue` numeric `color`
  symbology, domain `[0, 100]`). Asserts the rendered layer's paint is
  `{"fill-color": ["interpolate", ["linear"], ["get", "pop"], 0, "#dbeafe",
  100, "#1e3a8a"]}` — not `"#000000"`.

## TDD evidence

RED:
```
$ npx vitest run src/map/MapView.test.tsx -t symbology
FAIL  src/map/MapView.test.tsx > a layer with symbology renders paint compiled from its frozen domain, ignoring any stale raw paint
AssertionError: expected { id: 'l1', type: 'fill', …(2) } to match object { type: 'fill', source: 'l1', …(1) }
- Expected: "fill-color": ["interpolate", ["linear"], ["get", "pop"], 0, "#dbeafe", 100, "#1e3a8a"]
+ Received: "fill-color": "#000000"
Test Files  1 failed (1)
     Tests  1 failed | 79 skipped (80)
```

GREEN (after implementation):
```
$ npx vitest run src/map/MapView.test.tsx -t symbology
✓ src/map/MapView.test.tsx (80 tests | 79 skipped) 29ms
Test Files  1 passed (1)
     Tests  1 passed | 79 skipped (80)
```

Full file (no regression, including the SP-24 mixed-geometry paint-split
test and the "isolates a failing layer" try/catch test):
```
$ npx vitest run src/map/MapView.test.tsx
✓ src/map/MapView.test.tsx (80 tests) 378ms
Test Files  1 passed (1)
     Tests  80 passed (80)
```
(Two expected `console.error`/stderr lines from pre-existing
intentional-failure tests, unrelated to this change.)

## Full shell-gates output summary

- `npm run lint` → clean (`eslint .`, no output).
- `npm run format:check` → initially flagged `MapView.test.tsx` (array line
  wrapping); ran `npx prettier --write` on both touched files, then
  `format:check` passed clean.
- `npx vitest run` (full suite) → **161 files / 1421 tests passed** (0
  failed). Reference before this task was 161/1420 — the delta of +1 is
  exactly the new test added here; no regression anywhere else.
- `npm run build` → green (`tsc --noEmit && vite build`, only pre-existing
  chunk-size warnings, unrelated to this change).

## Files changed

- `shell/src/map/MapView.tsx` (modify)
- `shell/src/map/MapView.test.tsx` (modify)

No other files touched (no scope creep into `LayersPanel.tsx`/`mapWidget.tsx`).

## Deviations from the brief and why

1. **`geometryKind` for the `feature` branch**: as detailed above, used
   `renderAs`→`geometryKind` mapping (`circle`→`point`, `line`→`line`,
   default→`polygon`) instead of the brief sketch's literal `"polygon"`
   constant. This follows the brief's own prose instruction directly below
   the sketch ("pass the render-as-implied geometry kind consistently with
   whatever `applyLayers` already does today for that layer kind") rather
   than the sketch's placeholder value, which would have produced a paint-key/
   layer-type mismatch (e.g. `fill-color` posed on a `type: "circle"` layer)
   for any `feature` layer with `renderAs: "circle"` or `"line"` plus
   `symbology` — MapLibre would reject that and the layer would silently
   vanish via the outer `try/catch`.
2. **Commit subject rewording**: the brief's exact commit message
   (`feat(shell): MapView compile le paint depuis symbology quand elle est
   présente`) was rejected by the repo's `commitlint` hook
   (`subject-case`: the subject cannot start with a capitalized identifier
   like `MapView`). Reworded to `feat(shell): compile le paint de MapView
   depuis symbology quand elle est présente` (identical meaning, `MapView`
   moved out of the leading word), matching the existing precedent in this
   repo's history (e.g. `feat(shell): branche MapSymbologyEditor sur les
   couches vector...`, where the capitalized identifier is not the first
   word). Body unchanged.

## Self-review findings

- **Completeness**: both `vector` and `feature` branches route through
  `effectivePaint()`. Symbology-less layers are provably unaffected — the
  helper's first line returns `layer.paint ?? {}` verbatim when
  `!layer.symbology`, and the full pre-existing 80-test file (which is
  almost entirely symbology-less layers) is 100% green with no assertion
  changes needed elsewhere.
- **Quality**: no restructuring of the SP-24 sub-layer split — the mixed-
  geometry loop still calls `paintFor(..., sub.paintPrefix)` per sub-layer,
  now just fed `vectorPaint` (computed once) instead of `layer.paint`
  directly; same shape, same filtering.
- **Discipline**: only the two files named in the brief were touched;
  `LayersPanel.tsx` and `mapWidget.tsx` (or any other file) were not opened
  for editing.
- **Testing**: RED was genuinely observed (see command+output above) before
  any implementation code was written; GREEN observed after. No test files
  were pre-emptively "fixed" to pass — the failure was a real assertion
  mismatch against the stale `layer.paint`.

## Concerns

- The known non-goal called out explicitly by the brief: for a `vector`
  layer with `geometryKind === undefined` (mixed/unknown geometry) *and*
  `symbology` set, `effectivePaint` defaults to `"polygon"`, so
  `buildMapPaint` only populates `fill-color`. The point/line sub-layers
  then get an empty paint object after `paintFor(..., "circle-"/"line-")`
  filtering — i.e. a symbology-styled mixed-geometry layer with point/line
  features would render those features with MapLibre's paint defaults, not
  the compiled symbology colors. This is the brief's own literal
  specification ("do not invent a new geometryKind inference here" for the
  `vector` case), not an oversight on my part, and I did not add a test for
  it since the brief doesn't ask for one — flagging it here in case a later
  task (author-side symbology UI) needs to account for this when a
  `geometryKind` is unknown.
