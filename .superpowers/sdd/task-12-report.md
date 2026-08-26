# Task 12 report — Shell E2E: the plan's acceptance proof

## Status: BLOCKED — genuine production bug found (not a test-authoring issue)

The E2E spec (`shell/e2e/map-symbology.spec.ts`) was written per the brief's
sketch, reusing `map-popup.spec.ts`'s scaffolding, and actually run against a
real Chromium/MapLibre canvas. It fails deterministically at the reload
assertion because **`symbology` is not round-tripped through the shell's
`getMapConfig()` read path** — a real bug in `shell/src/api/itemClient.ts`,
not in the new spec.

## What I reused from `map-popup.spec.ts` and why

- The exact MVT tile fixture (`shell/e2e/fixtures/world-tile.mvt`, read via
  `readFileSync(fileURLToPath(...))`) and the exact route mock pattern
  (`**/collections/communes/tiles/**` → `application/vnd.mapbox-vector-tile`)
  — same reasoning as SP-24: any tile request returns the same fixture body,
  so the spec doesn't need per-zoom-level tile math.
- The "Communes" collection identity (`communes`, from `mocks.ts`'s
  `ALL_COLLECTIONS`) as the tiled layer to add.

## Navigation flow (copied from `map-editor.spec.ts`, not invented)

`map-popup.spec.ts` navigates straight to a pre-published `/maps/map-1` (a
*read* scenario). This task needed the *editor* (`LayersPanel` +
`MapSymbologyEditor`), so I copied `map-editor.spec.ts`'s create-a-map flow
verbatim instead: `goto("/")` → "Nouveau" → dialog Type=map, Titre, "Créer" →
lands on `/maps/77` → `canvas.maplibregl-canvas` visible → click the
"Communes" button in `LayerPicker` (`getByRole("button", { name: /Communes/ })`,
confirmed against `LayerPicker.tsx:84-94` — the button text is
`{source.title}` plus kind/count spans, hence the regex match rather than
exact text) to add the tiled layer.

## Real selectors confirmed against source (not guessed)

All confirmed by reading `shell/src/map/MapSymbologyEditor.tsx` (merged,
Tasks 7/11):
- `aria-label="Champ couleur"` (text input, line 106)
- `aria-label="Palette"` (select, line 125) — options `Catégorielle A/B`,
  `Séquentielle bleue/chaude` (`sequential-blue` value confirmed at line 21)
- `aria-label="Type de couleur"` (select, only rendered once `color.field`
  is truthy, line 143) — options `categorical`/`numeric`
- `aria-label="Méthode de classification"` (select, only rendered when
  `color.mode === "numeric"`, line 163) — options `continuous`/`quantile`/
  `equalInterval`/`jenks`
- `aria-label="Nombre de classes"` (number input, line 189, clamped 2–9;
  selecting "quantile" already defaults `classes` to 5, so the explicit
  `.fill("5")` is redundant but harmless and kept per the brief's sketch)
- button "Recalculer les classes" (line 214)
- The rendered domain text: `Classes calculées le {date} : {formatDomain(...)}`
  (lines 221–226). For quantile classification with 5 classes,
  `quantileBreaksFromRow` (`mapSymbology.ts:115-120`) builds
  `[min, q1, q2, q3, q4, max]` from the aggregate row
  `{min:0, q1:20, q2:40, q3:60, q4:80, max:100}` given by the brief's mock
  → breaks `[0,20,40,60,80,100]` → `formatDomain` (`.toFixed(1).join(" – ")`)
  → `"0.0 – 20.0 – 40.0 – 60.0 – 80.0 – 100.0"`, matching the brief's regex
  `/0\.0.*100\.0/`.
- "Enregistrer" save button: confirmed identical to `map-editor.spec.ts`'s
  usage (`MapEditorPage.tsx:124-130`).

I confirmed `MapSymbologyEditor` is reachable unconditionally (no extra
"open symbology" click needed): `LayersPanel.tsx`'s `LayerSymbologyEditor`
wrapper is rendered inline for every `vector`/`feature` layer (line 146-151),
right below `LayerPopupEditor` — same precedent as popup editing in SP-24.

I also confirmed `runStatistics` for a `vector` layer with a `collectionId`
posts to `POST /collections/{collectionId}/aggregate`
(`LayersPanel.tsx:63-71` → `itemClient.ts`'s `queryDataSource` → line ~1306:
`` `/collections/${resolved.layer}/aggregate` ``), so the brief's
`**/collections/*/aggregate` mock is the right route to intercept.

## The bug

`shell/src/api/itemClient.ts`:
- `RawMapLayer` (lines 64-81, the type for the raw JSON payload read back
  from `GET /configs/by-item/{pk}`) has **no `symbology` field**.
- `toFrontLayer()` (lines 83-125) explicitly lists which fields survive the
  read: for `kind: "vector"` it conditionally carries over `paint`,
  `collectionId`, `geometryKind`, `pkColumn`, `popup` — but never
  `symbology`. Same gap in the `"feature"` branch.

Meanwhile:
- `MapLayer` (`shell/src/api/types.ts:121,140`) **does** declare
  `symbology?: LayerSymbology` on both the `"vector"` and `"feature"`
  variants.
- The OpenAPI-generated schema (`shell/src/api/generated/core-schema.d.ts:1887`)
  confirms the **core already supports and stores `symbology`** on a
  `MapLayer` — this is a shell-only, read-path-only gap, not a backend bug.
- The **write path is fine**: `saveMapConfig()` (`itemClient.ts:870-878`)
  spreads the whole in-memory `MapConfig` (built by `LayersPanel`'s
  `onChange={(symbology) => onChangeLayer({ ...layer, symbology })}`) as-is
  into the PUT body — `symbology` genuinely reaches the server on save.

Net effect: an author configures color/size encoding on a layer, saves
successfully (the server accepts and stores it), but the **very next load of
that map — a reload, or simply someone else opening it — silently drops the
entire symbology configuration**, because `getMapConfig()`'s
`(map.layers ?? []).map(toFrontLayer)` (line 856) throws it away on the way
back into the app. This is the exact class of bug CLAUDE.md documents as
fixed for `popup`/`collectionId`/`geometryKind`/`pkColumn` in SP-24 Task 16
("the READ path... never re-read popup/collectionId/... every reloaded map
with a popup configured could never display it") — except `symbology`,
added later in SP-25 (Tasks 8/9), was never added to that same allowlist.

## Empirical proof (real Playwright run, not just static reading)

Ran `cd shell && npm run e2e -- map-symbology`. Real Chromium, real
MapLibre WebGL canvas, real navigation through the create-map → add-layer →
configure-symbology → save flow. Everything up to and including "Enregistrer"
passes (no "échec de l'enregistrement" error — the server round-trip of the
PUT genuinely succeeds). It fails exactly at the post-reload assertion:

```
1) e2e/map-symbology.spec.ts:16:1 › author 5 quantile classes on a tiled
   layer, save, reload, and the rendered colors survive with no new
   aggregate call

  Error: expect(locator).toBeVisible() failed
  Locator: getByText(/0\.0.*100\.0/)
  Expected: visible
  Timeout: 5000ms
  Error: element(s) not found

      72 |   await page.reload();
      73 |   await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    > 74 |   await expect(page.getByText(/0\.0.*100\.0/)).toBeVisible();
         |                                                ^
      75 |   expect(aggregateCallsAfterSave).toBe(0);

  1 failed
```

The captured accessibility snapshot at failure time
(`test-results/.../error-context.md`) shows, after reload:
- `combobox "Champ couleur"` — **empty**, no value set
- `combobox "Palette"` — reset to `option "Catégorielle A" [selected]`
  (the component's default when `symbology` is `undefined`)
- No "Type de couleur" / "Méthode de classification" / "Nombre de classes"
  controls at all (they only render when `color.field` is truthy —
  `MapSymbologyEditor.tsx:138,158`)

This is conclusive: `layer.symbology` came back `undefined` from
`getMapConfig()` after reload, exactly as the code reading above predicts.

## Files changed

- Created (uncommitted, per the brief's own gate — "Run it... Expected:
  PASS" precedes "Commit"): `shell/e2e/map-symbology.spec.ts`
- No production code touched, as instructed.

## Suggested fix (not applied — reported per the brief's explicit instruction
not to patch production code from an E2E task)

In `shell/src/api/itemClient.ts`:
1. Add `symbology?: LayerSymbology | null;` to `RawMapLayer` (import
   `LayerSymbology` from `../builder/widgets/mapSymbology`, already imported
   by `types.ts` the same way).
2. In `toFrontLayer()`, add `...(l.symbology ? { symbology: l.symbology } : {})`
   to both the `"vector"` and `"feature"` branches, mirroring the existing
   `...(l.popup ? { popup: l.popup } : {})` pattern immediately above each.

This is a same-shape, same-file fix to the identical bug class SP-24 Task 16
already fixed once for `popup`/`collectionId`/`geometryKind`/`pkColumn` — it
was simply never extended to `symbology` when that field was introduced.

## Recommendation

Once `toFrontLayer` is fixed, re-run `cd shell && npm run e2e -- map-symbology`
— I expect it to pass unchanged (no spec edits anticipated), then run the
full suite (`npm run e2e`) to confirm no regression on
`map-popup.spec.ts`/`map-editor.spec.ts`, then commit both the fix and this
spec together (or the fix first, spec second — whichever the controller
prefers for commit hygiene).

## Self-review

- Completeness: the spec, as written, proves the full acceptance chain
  end-to-end (5 quantile classes via the real UI → save succeeds → reload →
  colors/domain persist → zero new `/aggregate` calls) — it is currently
  blocked by production code, not by an incomplete test.
- Quality: no invented selectors — every `aria-label`/button name was
  confirmed against the merged `MapSymbologyEditor.tsx`/`LayersPanel.tsx`/
  `LayerPicker.tsx`/`MapEditorPage.tsx` source, and all navigation/route-mock
  mechanics are copied verbatim from `map-popup.spec.ts` (tile fixture) and
  `map-editor.spec.ts` (create-map/add-layer flow).
  `page.on("request", ...)` for `aggregateCallsAfterSave` is registered
  *after* the save click, matching the brief's own comment ("stop counting
  real aggregate calls from here").
- Testing: genuinely run, not just written — full failure output above is
  real, from a real headless Chromium run against the built preview server.
  The full suite (`npm run e2e`) was **not** run, since the new spec fails
  and running the full ~110-spec suite would not add information beyond
  confirming this one file's failure — will run it once this is unblocked.

## Concerns

None beyond the blocking bug itself. The bug is narrowly scoped (one
function, one file, mirrors an established fix pattern) and does not
implicate the spec's design.

---

## Follow-up (2026-08-23) — fix applied, unblocked, task closed

Picked up from the BLOCKED report above. Fixed the production bug, added a
regression unit test with real RED→GREEN evidence, confirmed the E2E spec
now passes, ran the full E2E + unit + build suites, and committed both
pieces separately per the repo's established convention (SP-23 Task 18).

### The fix

`shell/src/api/itemClient.ts`, exactly as the blocked implementer's
"Suggested fix" predicted — no surprises:

1. `RawMapLayer` (line ~64-82) gains:
   ```ts
   symbology?: import("../builder/widgets/mapSymbology").LayerSymbology | null;
   ```
   Used the inline type-only `import(...)` form (mirroring `types.ts`'s
   `MapLayer.symbology` exactly), not a plain `Record<string, unknown>` —
   there was no reason to weaken the type when the real one is already
   imported the same way one file over, and this way a shape mismatch
   between the raw JSON contract and the front-end type would show up as a
   type error, not silently.

2. `toFrontLayer()`'s `"vector"` branch gains
   `...(l.symbology ? { symbology: l.symbology } : {})` immediately after
   the existing `...(l.popup ? { popup: l.popup } : {})` line.

3. The `"feature"` branch gains the identical line after its own `popup`
   spread.

No other files needed changes. The write path (`saveMapConfig`) was
already correct, as the blocked report established.

### Regression test — RED→GREEN evidence

Added to `shell/src/api/itemClient.test.ts`, immediately before the
existing `"getMapConfig reads popup on a feature (GeoJSON) layer"` test —
same shape as the sibling popup/collectionId/geometryKind/pkColumn
regression test added in SP-24 Task 16, but for `symbology`: mocks
`GET /configs/by-item/77` returning a vector layer whose raw JSON carries a
full `LayerSymbology` object (numeric color encoding, quantile
classification, 5 classes, `sequential-blue` palette, computed breaks),
calls `getMapConfig("77")`, and asserts the returned layer's `symbology`
deep-equals the input via `toEqual`.

**RED** (confirmed empirically, not assumed): temporarily reverted only
`itemClient.ts` (`git stash push -- shell/src/api/itemClient.ts`, keeping
the new test in place) and ran
`npx vitest run src/api/itemClient.test.ts -t "reads symbology on a vector layer"`:

```
FAIL  src/api/itemClient.test.ts > getMapConfig reads symbology on a vector layer
AssertionError: expected { id: 'communes', …(8) } to deeply equal { id: 'communes', …(9) }
- Expected
+ Received
@@ -3,31 +3,9 @@
    "geometryKind": "polygon",
    "id": "communes",
    "kind": "vector",
    "pkColumn": "id",
    "sourceLayer": "communes",
-   "symbology": { ... full object elided ... },
    "tilesUrl": "...",
    "title": "Communes",
    "visible": true,
  }
 Tests  1 failed | 153 skipped (154)
```

Confirms the test would have caught the original bug — the raw
`symbology` value is simply absent from what `toFrontLayer` produces
without the fix.

**GREEN**: restored the fix (`git stash pop`), re-ran the same targeted
test:

```
✓ src/api/itemClient.test.ts (154 tests | 153 skipped) 35ms
Tests  1 passed | 153 skipped (154)
```

Then ran the whole file to confirm no collateral damage:

```
✓ src/api/itemClient.test.ts (154 tests) 377ms
Test Files  1 passed (1)
Tests  154 passed (154)
```

### E2E spec — now passes

`cd shell && npm run e2e -- map-symbology`:

```
Running 1 test using 1 worker
  ✓  1 e2e/map-symbology.spec.ts:16:1 › author 5 quantile classes on a
     tiled layer, save, reload, and the rendered colors survive with no
     new aggregate call (3.2s)
1 passed (32.0s)
```

Exactly as the blocked implementer predicted: the spec itself needed no
edits, only the production fix.

### Full E2E suite

`cd shell && npm run e2e`: **105 passed, 4 skipped (static-export, unrelated
to this task), 3 failed** — `map-popup.spec.ts` and `map-editor.spec.ts`
(the two files the brief explicitly asked to watch) are both green.

The 3 failures are all in `analytics-context.spec.ts`, all tagged
`(SP-14h)` (map color/size encoding legends + click cross-filter on a
styled map feature in the *app widget* runtime, not the map editor):
- `a map with a categorical color encoding shows a legend built from a
  groupBy domain query (SP-14h)`
- `a map with numeric color and size encodings shows a legend with both
  domains' bounds (SP-14h)`
- `a click on a styled map feature still cross-filters a sibling table by
  pk (SP-14h)`

**Verified these are NOT a regression from this task's fix or from the new
spec** — not assumed, checked empirically: added a disposable git worktree
at `e2a0a74` (`feat(shell): le widget carte utilise LayerSymbology au lieu
d'encodings` — the commit immediately preceding this task's work, with no
`package.json`/`package-lock.json` diff against HEAD, so `node_modules` was
symlinked rather than reinstalled) and ran
`npx playwright test --grep "SP-14h"` there. Same 3 tests fail, identically,
with `itemClient.ts` in its pre-fix state and `map-symbology.spec.ts` not
present at all. These three failures pre-date this task entirely — they're
a pre-existing regression from the widget's earlier SP-25 switch from
`encodings` to `LayerSymbology` (mapWidget/app-runtime legend rendering, a
different code path from the map-editor `toFrontLayer` fix this task made),
not something introduced or fixable within Task 12's scope. Flagging for
the controller/next task rather than silently absorbing scope creep.

### Full shell unit-test suite + build

`cd shell && npx vitest run`: **161 files / 1427 tests passed**, 0 failed.

`cd shell && npm run build` (`tsc --noEmit && vite build`): clean, 0 type
errors, build succeeded (only the two pre-existing chunk-size/dynamic-import
warnings already present before this task).

### Commits

- `52bd33e` — `fix(shell): relit symbology depuis la config carte
  sauvegardée` (`itemClient.ts` + `itemClient.test.ts`)
- `ffaf0ac` — `test(shell): prouve le round-trip de la symbologie sur une
  couche tuilée` (`e2e/map-symbology.spec.ts`)

### Status: DONE_WITH_CONCERNS

Task 12 itself is fully closed: fix applied, regression test proven
RED→GREEN, E2E spec passes, no regression on the two named files
(`map-popup.spec.ts`/`map-editor.spec.ts`), full unit suite + build clean.
The one concern is out of this task's scope but worth surfacing loudly: 3
pre-existing `analytics-context.spec.ts` (SP-14h) failures in the app-widget
map-legend/cross-filter path, introduced by an earlier SP-25 task
(`e2a0a74`) before Task 12 started, confirmed independent of both this
task's fix and its new spec.
