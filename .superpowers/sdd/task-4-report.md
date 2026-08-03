# Task 4 report — E2E: map symbology legends, cross-filter regression, unconfigured no-op (SP-14h)

## What was implemented

Appended four Playwright E2E scenarios to the end of `shell/e2e/analytics-context.spec.ts`
(after the SP-14g unconfigured-pivot test), exactly as given in the task brief, plus one
necessary robustness fix in scenario 24 (see "Concerns" below):

1. **Scénario 22 (SP-14h)** — categorical color: a polygon layer colored by `region`
   shows a legend built from a `groupBy` statistics query, distinct from the `features`
   DataSource feeding the geometry.
2. **Scénario 23 (SP-14h)** — numeric color + size: a point layer sized/colored by two
   numeric fields (`valeur`, `montant`) shows a legend with both domains' min–max bounds,
   fetched via two separate statistics (`measures`) queries.
3. **Scénario 24 (SP-14h)** — regression: a click on a styled map feature still
   cross-filters a sibling table by pk, unchanged by the new symbology.
4. **Scénario 25 (SP-14h)** — regression: a map with no encodings configured issues zero
   domain (aggregate) queries — behaves exactly as before Task 1–3.

## Test evidence

### Targeted E2E (the 4 new SP-14h scenarios)

```
$ cd shell && npm run e2e -- analytics-context.spec.ts -g "SP-14h"
Running 4 tests using 1 worker
  ✓ a map with a categorical color encoding shows a legend built from a groupBy domain query (SP-14h)
  ✓ a map with numeric color and size encodings shows a legend with both domains' bounds (SP-14h)
  ✓ a click on a styled map feature still cross-filters a sibling table by pk (SP-14h)
  ✓ a map with no encodings configured issues no domain query (SP-14h)
4 passed (34.3s)
```

Also verified with `--repeat-each=5 --workers=3` (20 runs total): 20 passed, no flakes,
after the retry-loop fix described below.

### Full E2E suite

```
$ cd shell && npm run e2e
Running 76 tests using 8 workers
...
76 passed (1.4m)
```

First run showed 1 unrelated failure in `publication.spec.ts` (thumbnail-capture flake
under 8-way worker contention — confirmed pre-existing: passes standalone, file last
touched in an old commit unrelated to this task, `git log -1 -- e2e/publication.spec.ts`
→ `a1499a2`). A second full run passed all 76/76 clean.

### Full unit suite + build

```
$ cd shell && npm run test
Test Files  104 passed (104)
     Tests  792 passed (792)

$ cd shell && npm run build
tsc --noEmit && vite build
✓ 2714 modules transformed.
✓ built in 13.13s
```

## Files changed

- `shell/e2e/analytics-context.spec.ts` — append-only: `git diff --stat` shows
  `237 insertions(+), 0 deletions(-)`. No existing test or helper (`mockCore`, `createApp`,
  `addFeaturesSource`, `promoteLastSource`) was modified.

## Self-review

- Completeness: all 4 new scenarios pass individually and under repeated/parallel
  stress; full E2E suite (76/76) green; full unit suite (792/792) green; build clean.
- Quality: diff is strictly additive (confirmed via `git diff` — zero `-` lines besides
  the `---` diff header). No existing test's assertions or helpers were touched.
- Discipline: no scope creep — only this one file was modified; the widget
  implementation (`mapWidget.tsx`, `mapSymbology.ts`, `MapView.tsx` from Tasks 1–3) was
  read for verification but never edited.
- Testing: pristine final run (76/76, no Playwright-level retries reported); the one
  retry mechanism that exists is inside the test body itself (see below), not a
  Playwright-level retry/flake.

## Concerns (selector/timing adjustment made, and why)

Scenario 24 ("a click on a styled map feature still cross-filters a sibling table by
pk") as literally specified in the brief used a single `page.mouse.click(...)` guarded
by a fixed assumption that the polygon would already be painted on the WebGL canvas.
In practice this raced against MapLibre's async pipeline: `ctx.data.url` is a real
network URL fetched by MapLibre itself (a GeoJSON source), and the layer's `click`
handler (`map.on("click", layer.id, handler)` in `src/map/MapView.tsx`) only fires
when a feature is actually painted under the cursor — so a click sent before the first
paint completes silently produces no cross-filter effect and the test hung until the
30s Playwright timeout.

This is not a wrong selector or an incorrect assertion about the widget's contract
(confirmed by reading `mapWidget.tsx`'s `onFeatureClick` wiring and `MapView.tsx`'s
click-handler registration — both behave exactly as documented in the SP-14h spec,
untouched by Tasks 1–3). It is inherent test flakiness from asserting on real WebGL
paint timing, which varies with machine load — a fixed `page.waitForTimeout(500)`
worked once but still failed under `--workers=3` parallel load.

Fix applied (in the test only): replaced the single click with a bounded retry loop
(up to 10 attempts, 1s each) that re-clicks the same canvas center until the expected
`id=1` request is observed. This is safe specifically because a "missed" click (no
feature under cursor) produces zero side effects — no cross-filter is set, no toggle
state changes (`AnalyticsContext.tsx`'s `setCrossFilter` only toggles when the handler
actually fires with a matching value) — so retrying is idempotent right up until the
one click that actually lands on the painted polygon, at which point the loop stops.
Verified with 20 repeated runs under parallel workers with zero failures after the fix
(vs. 2 timeouts out of 16 runs before it, both isolated to this scenario).

No other test in the brief required adjustment; scenarios 22, 23, 25 passed as
literally specified on the first try, matching the actual DOM/legend text
(`buildLegend` in `mapSymbology.ts` produces `"{min} – {max}"` with an en dash, which
matched the brief's `"10 – 90"` / `"2 – 18"` assertions exactly).
