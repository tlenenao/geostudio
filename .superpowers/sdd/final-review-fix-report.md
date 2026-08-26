# SP-25 final whole-branch review — fix report (C1 + I1..I6)

Status: **DONE**

Commit: `014bd04b0f8bb11cd5743c5a04d78690be891e9b`
(`fix(shell): ferme C1/I1-I6 de la revue finale SP-25`, on `dev`, single
commit)

## Summary

All 7 findings from the brief (`.superpowers/sdd/final-review-fix-brief.md`)
fixed in one commit, TDD (tests written alongside/before the fix for each
finding, RED→GREEN evidence captured for C1 as required). No Minor findings
touched.

## Per-finding fix + test mapping

### C1 (Critical) — degenerate/never-recomputed symbology domain silently vanished the layer

- **Fix**: new pure `normalizeDomain(domain: ColorDomain | null): ColorDomain | null`
  in `shell/src/builder/widgets/mapSymbology.ts`. Rejects (`null`) an empty
  categorical domain, a numeric-classed domain with < 2 breaks, any
  non-finite break, or breaks that (after deduping adjacent equal values)
  have < 2 distinct values or aren't strictly ascending. Adjacent duplicate
  breaks are collapsed rather than rejected outright (e.g.
  `[0,10,10,20]` → usable 2-class `[0,10,20]`), so a partial tie in
  quantile/jenks output degrades gracefully to fewer classes instead of
  being thrown away. `buildMapPaint` and `buildLegend` both call
  `normalizeDomain` on their `colorDomain` argument before branching, and
  fall back to their pre-existing "no domain configured" behavior (no
  color paint key / no legend.color) when it returns `null` — no new
  fallback path invented.
- **Authoring gaps closed** in `shell/src/map/MapSymbologyEditor.tsx`:
  - Visible hint text ("Classes non calculées — cliquez sur « Recalculer
    les classes »." / "Taille non calculée — …") whenever a field is
    configured but `computedAt === ""`.
  - "Retirer la couleur" / "Retirer la taille" buttons, the first real
    `onChange` call sites that remove `color`/`size` from `LayerSymbology`
    (falling back to `onChange(undefined)` when nothing remains active).
- **Tests**:
  - `mapSymbology.test.ts`: 9 new `normalizeDomain` unit tests (empty
    categorical, non-empty categorical pass-through, continuous numeric
    pass-through, single break, fully collapsed `equalIntervalBreaks(10,10,3)`,
    non-finite break incl. `undefined`, non-ascending-after-dedup, adjacent
    duplicate collapse, `null` input) + 4 integration tests
    (`buildMapPaint`/`buildLegend` render unstyled/no-legend instead of
    throwing on an empty categorical or collapsed-breaks domain).
  - `MapSymbologyEditor.test.tsx`: hint-text tests for color and size,
    "clear color keeps size" test, "clear only encoding → `onChange(undefined)`"
    test.
  - **RED→GREEN evidence**: `git stash push -- shell/src/builder/widgets/mapSymbology.ts`,
    ran `npx vitest run src/builder/widgets/mapSymbology.test.ts` against
    the pre-fix file → **17 failing** (the new `normalizeDomain` tests fail
    on missing export; the 4 `quantileBreaksFromRow`/`jenksBreaks` I1 tests
    also fail, since they share the same file/stash). `git stash pop`
    restored the fix → all 48 tests pass. Confirms the new tests are load-bearing
    against the pre-fix behavior, not vacuously true.

### I1 (Important) — `jenksBreaks`/`quantileBreaksFromRow` produced NaN/undefined on empty/small input

- **Fix**: `quantileBreaksFromRow` now guards every field read with `?? 0`
  (mirroring the sibling min/max path), never emitting `NaN`. `jenksBreaks`
  now returns `[]` immediately when `data.length === 0 || data.length < classes`,
  before the out-of-bounds matrix reads that used to produce a run of
  `undefined`. Both changes are defended a second time downstream by C1's
  `normalizeDomain` (degenerate `[0,0,…]` or `[]` breaks are rejected/collapsed
  there too) — both layers of defense present per the brief.
- **Tests** (`mapSymbology.test.ts`): `quantileBreaksFromRow({}, 4)` → all
  zeros; `quantileBreaksFromRow` with a partial row; `jenksBreaks([], 3)` → `[]`;
  `jenksBreaks([1,2], 5)` (k > data.length) → `[]`.

### I2 (Important) — global `datalist` id broke autocomplete with 2+ styled layers

- **Fix**: `MapSymbologyEditor.tsx` now uses `const listId = useId();` and a
  single `${listId}-fields` datalist shared by both the "Champ couleur" and
  "Champ taille" inputs (same field-name universe, same precedent as
  `PopupEditor.tsx`), instead of the hardcoded `map-symbology-fields` id.
- **Test**: new `MapSymbologyEditor.test.tsx` test rendering two instances
  side by side, asserting their `list=` attributes differ and each resolves
  to a real `<datalist>` element.

### I3 (Important) — `recomputeSize` had no error handling

- **Fix**: `recomputeSize` now mirrors `recomputeColor` exactly — `try { … }
  catch (e) { setSizeError(...) } finally { setBusy(null) }`, with its own
  `role="alert"` error paragraph (split into `colorError`/`sizeError` state
  since the two recomputes are independent operations).
- **Test**: new "a failing size recompute surfaces an error instead of an
  unhandled rejection" test in `MapSymbologyEditor.test.tsx`, mirroring the
  existing color-failure test.

### I4 (Important) — mixed-geometry tiled layer only styled its polygon sublayer

- **Fix**: `effectivePaint` in `MapView.tsx` now takes an explicit
  `geometryKind: GeometryKind` parameter instead of deriving one internally
  (which always fell back to `"polygon"` for a mixed/unknown-geometry
  layer). `applyLayers` now calls `effectivePaint(layer, sub.suffix)` once
  per `MIXED_GEOMETRY_SUBLAYERS` entry (point/line/polygon), so each
  sublayer gets `buildMapPaint` output compiled for its own real geometry
  kind, not a single polygon-scoped paint object filtered by prefix. The
  `feature`-kind branch was updated the same way (explicit `renderAs`-derived
  `geometryKind` passed in, same behavior as before, no regression). The
  `paintFor` prefix filter is kept on the mixed-geometry path because the
  manual (non-symbology) `layer.paint` object can still legitimately carry
  keys for multiple prefixes at once (existing test covers this).
- **Test**: new `MapView.test.tsx` test "a mixed-geometry symbologized
  layer compiles distinct paint per sub-layer geometry, not just polygon" —
  asserts `circle-color`/`line-color`/`fill-color` are all populated with
  the compiled `match` expression on their respective sublayers.

### I5 (Important) — map widget: recompute broken without `datasetId`; Jenks offered where it can't work

- **Fix 1**: `mapWidget.tsx`'s `runStatistics` now passes
  `layer: dataSource?.layer ?? ""` instead of a hardcoded `""`. Per
  `itemClient.ts`'s `queryDataSource`, `source.layer` is exactly what's
  used for `/collections/{layer}/aggregate` when `datasetId` is absent
  (and is ignored in favor of the resolved dataset's `collectionId` when
  `datasetId` is present), so this one-line change fixes the plain
  collection-backed (`type: "features"`, no `datasetId`) source case
  without touching the `datasetId` path.
- **Fix 2**: `MapSymbologyEditor` gained an optional `jenksAvailable?: boolean`
  prop (default `true`); the "Seuils naturels (Jenks)" `<option>` is
  rendered only when it's not explicitly `false`. `mapWidget.tsx` passes
  `jenksAvailable={false}` (this host's `sampleField` unconditionally
  throws — scope intentionally not widened to wire up collectionId
  resolution, per the brief). `LayersPanel.tsx`'s usage is untouched
  (defaults to `true`, real `sampleField` there).
- **Tests**:
  - `mapWidget.test.tsx`: "Jenks option is absent from the widget's
    PropsPanel classification select"; "recompute works for a plain
    collection-backed source (no datasetId), via dataSource.layer" —
    asserts `queryDataSource` is called with `layer: "communes"` and that
    the resulting domain reaches `onChange`.
  - Existing "choosing Jenks from the widget's PropsPanel surfaces an
    error instead of hanging" test still passes unchanged (it exercises an
    already-jenks-classified value directly, not the `<select>`, so hiding
    the option doesn't affect it).

### I6 (Important) — flaky `MapEditorPage.test.tsx` (~25% red)

- **Fix**: `await waitFor(() => expect(mapInstances[0]).toBeDefined());`
  inserted before `mapInstances[0].fire("idle")` in the
  `exportRender=1 renders a nude chrome …` test.
- **Verification**: ran `npx vitest run src/pages/MapEditorPage.test.tsx`
  10x in a loop — **10/10 green**, no flakes observed (previously ~1 in 4
  failed with `TypeError: Cannot read properties of undefined (reading
  'fire')`).

## Verification contract results

- **Shell unit suite**: `npx vitest run` → **161 files / 1454 tests passed**
  (baseline 161/1427; +27 tests from this fix pass, no regressions, no
  skips).
- **`npx tsc --noEmit`**: clean.
- **`npx eslint .`**: clean.
- **`npx prettier --check .`**: clean (two new/edited test files needed
  `prettier --write` after initial edits — applied, tests re-run green
  after reformatting).
- **`npm run build`**: succeeds (pre-existing chunk-size warnings and the
  `MapView.tsx` dynamic-vs-static-import note are unrelated to this
  change, present before it too).
- **Full E2E suite**: `npm run e2e` → **108 passed, 4 skipped, 0 failed**
  — exactly matches the baseline. Specifically checked:
  `map-symbology.spec.ts` (1/1 passed, still clicks "Recalculer les
  classes" as before — unaffected by the new hint/clear UI),
  `analytics-context.spec.ts` (all ~35 sub-specs passed, including the
  SP-14h map-symbology-legend ones), `map-popup.spec.ts` (2/2 passed),
  `map-editor.spec.ts` (2/2 passed).

## Concerns / notes

- None blocking. One judgment call worth flagging: for C1's
  `normalizeDomain`, a duplicate break that is *not* at the very start/end
  (e.g. a mid-range tie from `quantile`) is collapsed into fewer usable
  classes rather than rejected outright — the brief's wording ("dedupe
  adjacent equal breaks first; if fewer than 2 distinct breaks remain after
  dedup, treat as unusable") supports this reading (a step expression
  literally cannot be fed raw duplicate/non-ascending breaks, so the
  "usable" result must already be the deduped array), but it's a
  degrade-gracefully choice rather than an all-or-nothing reject — flagging
  it explicitly in case a stricter "any duplicate at all ⇒ null" reading was
  intended.
- Per-task Minor findings (M1–M11) were left untouched as instructed.
- Pre-existing unrelated changes in the working tree
  (`.superpowers/sdd/*.md`, untracked `deploy/postgis/pg_hba.conf`) were
  left alone — not part of this fix pass and not committed.

## Round 2 (C-new)

Status: **DONE**

Commit: `cacddb98573304d492247b2b0f03a2a691cb6020`
(`fix(shell): ferme le trou de degat C1 (2 breaks -> step invalide)`, on
`dev`, single commit)

### Finding

Re-review of `014bd04` found a boundary hole in round 1's own C1 fix:
`normalizeDomain` only rejected a numeric-classed domain with **< 2**
distinct breaks after dedup. A domain that dedups to **exactly 2** breaks
(1 class) was accepted, and `buildMapPaint` turned it into a MapLibre
`step` expression with only 2 arguments (`["step", ["get","pop"],
"#2563eb"]`) — MapLibre rejects this at parse time ("Expected at least 4
arguments, but found only 2."), so `map.addLayer` throws, and the existing
`try/catch` in `MapView.tsx` silently drops the source+layer. Same original
symptom as C1 (layer vanishes, no signal), reached through a realistic
tied-data column (e.g. `quantileBreaksFromRow({min:0,q1:0,q2:0,q3:0,max:10},
4)` → `[0,0,0,0,10]` → dedups to `[0,10]`; same for `jenksBreaks([0,0,0,0,10],
3)` → `[0,0,0,10]` → dedups to `[0,10]`).

### Fix — Option A (tighten `normalizeDomain`)

Changed the dedup-length gate in `normalizeDomain`
(`shell/src/builder/widgets/mapSymbology.ts`) from `deduped.length < 2` to
`deduped.length < 3`: a numeric-classed domain now needs at least 3 distinct
breaks (≥ 2 classes) to be considered usable. Below that it's rejected the
same way a domain with 0/1 raw breaks already was — `buildMapPaint`/
`buildLegend` both fall back to their pre-existing "no domain configured"
behavior (no color paint key / no legend section).

**Why Option A over Option B** (brief left the choice open): `normalizeDomain`
is already the single shared gate both `buildMapPaint` and `buildLegend`
call before branching on `colorDomain.kind`. Tightening it by one line keeps
that symmetry for free — no new branch needed in either function, no new
"1-class constant paint" concept to keep behaviorally consistent between
paint and legend. Option B (emit a constant-color paint + single-class
legend entry for a 1-class domain) is more informative in principle, but
would have required mirroring new logic in both `buildMapPaint` and
`buildLegend` for a real but narrow case (tied data collapsing to exactly 1
class), for a fix pass explicitly scoped to closing the hole safely. Went
with the smaller, safer, already-symmetric change.

Updated the block comment above `normalizeDomain` to document the new
threshold and cite the C-new repro directly (so a future reader doesn't
re-introduce the same off-by-one).

### Test

Added to `shell/src/builder/widgets/mapSymbology.test.ts` (7 new tests,
all in a new block after the existing C1 test section):

- `quantileBreaksFromRow on tied data dedups to exactly 2 breaks (the
  re-review's repro)` — reproduces the exact input from the brief.
- `jenksBreaks on the same tied-data shape also dedups to exactly 2
  breaks` — reproduces the brief's second repro path.
- `normalizeDomain now rejects a numeric-classed domain that dedups to
  exactly 2 breaks (1 class)` — both repro shapes → `null`.
- `normalizeDomain still accepts a domain that dedups to exactly 3 breaks
  (2 classes)` — regression guard at the new boundary.
- `buildMapPaint never emits a MapLibre-invalid step for tied-data breaks
  that dedup to 1 class` — asserts `paint["fill-color"]` is `undefined`
  (not a broken `step`), **and** validates the pre-fix shape
  (`["step", ["get","pop"], "#2563eb"]`) against the real
  `@maplibre/maplibre-gl-style-spec` package's `createExpression`,
  confirming `result.result === "error"` — i.e. proves the shape the old
  code would have produced really is invalid per the real library, the
  same way the re-reviewer found the bug, not just an assumption about the
  spec.
- `buildLegend shows no color section for a domain that dedups to exactly
  2 breaks` — symmetry check on the legend side (comes for free from the
  shared gate, verified explicitly anyway).
- `buildMapPaint's step expression for a usable (>= 2 classes) domain
  validates against the real MapLibre style spec` — positive-path check:
  a genuinely usable 3-break domain still produces a `step` expression
  `createExpression` accepts (`result.result === "success"`).

`@maplibre/maplibre-gl-style-spec` (v20.4.0) is present in `node_modules`
as a transitive dependency of `maplibre-gl` (not a direct `shell/package.json`
dependency) — used only in this test file, imported directly, no
`package.json` change needed. Confirmed interactively before writing the
test (`node -e 'import("@maplibre/maplibre-gl-style-spec").then(...)'`)
that `createExpression(["step", ["get","pop"], "#2563eb"])` really does
return `{result: "error", value: [{message: "Expected at least 4
arguments, but found only 2."}]}` against the real library — matches the
re-reviewer's empirical finding exactly.

### Verification

- `cd shell && npx vitest run` → **161 files / 1461 tests, 0 failed**
  (baseline after round 1 was 161/1454 — +7 tests from this fix, 0
  regressions).
- `npx tsc --noEmit` → clean.
- `npx eslint .` → clean.
- `npm run build` → clean (`tsc --noEmit && vite build`, same pre-existing
  chunk-size warnings as before, unrelated to this change).
- `npm run e2e` — **not re-run**, per the brief's explicit permission to
  skip when the change doesn't touch anything E2E specs depend on. This
  fix only tightens a pure function's rejection threshold
  (`normalizeDomain`) inside `mapSymbology.ts`; no component, prop, or
  DOM-visible behavior touched, and no E2E spec exercises the specific
  tied-data threshold this closes.
- Confirmed no unrelated files were staged: `git status --porcelain
  shell/` before commit showed only the two touched files
  (`mapSymbology.ts`, `mapSymbology.test.ts`).

### Not in scope (per brief)

N2 and N3 (Minor findings from the re-review) were left untouched, as
instructed — noted here for the progress ledger:

- **N2**: a domain that recomputes successfully but yields something
  unusable (e.g. jenks on too-short a sample) still sets `computedAt` and
  clears the "not yet computed" hint from round 1, even though the result
  is unusable — no signal to the author in that case either.
- **N3**: continuous `numeric` domains bypass `normalizeDomain` entirely;
  a `NaN` min/max (same root cause as I1, but on the continuous-domain path)
  produces an `interpolate` expression MapLibre *accepts* but that
  serializes as `null` via `JSON.stringify` — same silent-corruption class
  as I1, different code path.

### Concerns

- None. The fix is a single-line threshold change plus a comment update;
  behavior for every domain shape already covered by the round-1 test
  suite is unchanged (verified: all pre-existing tests still pass
  unmodified, including the round-1 "collapses to fewer, still-usable
  classes" test at exactly the new 3-break boundary).
- N2/N3 remain open, as scoped.
