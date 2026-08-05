# Task 5 Report: Shell — `bboxFromGeometry` util + `derivePatch` resolution

## What was implemented

Exactly per brief, transcribed literally:

1. **`shell/src/lib/geometryBbox.ts`** (new) — `bboxFromGeometry(geometry: unknown): [number, number, number, number] | null`, a pure recursive coordinate-array walker computing an enclosing `[minX, minY, maxX, maxY]` bbox for any GeoJSON geometry (Point/LineString/Polygon/Multi*), with no turf/geojson dependency. Returns `null` for `undefined`, `null`, or any non-geometry-shaped value (missing `coordinates`).

2. **`shell/src/lib/geometryBbox.test.ts`** (new) — 4 tests: Point (degenerate bbox), Polygon, MultiPolygon (bbox spans both parts), and the null/undefined/non-geometry guard.

3. **`shell/src/lib/analyticsPatch.ts`** (full rewrite) — `derivePatch` now has two cross-filter resolution passes:
   - **Direct/same-dataset path** (existing behavior, unchanged in effect): resolves `ctx.crossFilter[source.datasetId]` if the entry's `originSourceId` differs from the current source — extracted into a new `applyCrossFilterValue(patch, field, value)` helper (byte-for-byte extraction of the three existing branches: array → `field__in`, range object → `field__gte`/`field__lte`, scalar → `field`).
   - **Cross-dataset link path** (new): iterates every *other* dataset's active `ctx.crossFilter` entry, skips the current dataset (`originDatasetId === source.datasetId`), looks up whether that origin dataset declares a `crossFilterLinks` entry targeting the current dataset, and if so:
     - `mode: "attribute"` → applies `applyCrossFilterValue(patch, link.targetField, entry.value)`, but only if `entry.field === link.sourceField`.
     - `mode: "spatial", precision: "bbox"` → computes `bboxFromGeometry(entry.geometry)` and sets `patch.bbox` to the joined bbox string, only if `entry.geometry` is defined and a bbox was computed.
     - `mode: "spatial", precision: "exact"` → sets `patch.geomIntersects = entry.geometry` (raw geometry, only if `entry.geometry` is defined).

4. **`shell/src/lib/analyticsPatch.test.ts`** (append) — 7 new tests covering: attribute-link translation, field mismatch → ignored, wrong `targetDatasetId` → ignored, spatial/bbox translation, spatial/exact translation, missing geometry → ignored, and the no-self-link guard (same dataset's own cross-filter isn't double-resolved through the link loop).

## Testing

### TDD Evidence — geometryBbox

**RED** — `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
```
FAIL  src/lib/geometryBbox.test.ts [ src/lib/geometryBbox.test.ts ]
Error: Failed to resolve import "./geometryBbox" from "src/lib/geometryBbox.test.ts". Does the file exist?
Test Files  1 failed (1)
     Tests  no tests
```
Expected failure reason: module `./geometryBbox` didn't exist yet. Confirmed.

**GREEN** — same command after creating `geometryBbox.ts`:
```
✓ src/lib/geometryBbox.test.ts (4 tests) 11ms
Test Files  1 passed (1)
     Tests  4 passed (4)
```

### TDD Evidence — analyticsPatch (derivePatch)

**RED** — `cd shell && npx vitest run src/lib/analyticsPatch.test.ts` (after appending the 7 new tests, before rewriting `derivePatch`):
```
FAIL  src/lib/analyticsPatch.test.ts > translates a spatial/bbox link into a bbox patch derived from the entry's geometry
AssertionError: expected {} to deeply equal { bbox: '2,48,3,49' }
FAIL  src/lib/analyticsPatch.test.ts > translates a spatial/exact link into a geomIntersects patch carrying the raw geometry
AssertionError: expected {} to deeply equal { geomIntersects: {...} }
FAIL  src/lib/analyticsPatch.test.ts > translates an attribute link from another dataset's active cross-filter
AssertionError: expected {} to deeply equal { nom_commune: 'Brive' }
Test Files  1 failed (1)
     Tests  3 failed | 16 passed (19)
```
Expected failure reason: `derivePatch` didn't yet scan any dataset's `crossFilterLinks`, so the three "translates..." tests (which expect a non-empty patch) got `{}`. The four "ignores..." tests and the self-link guard test already passed trivially at this point (no resolution happening at all is indistinguishable from "correctly ignoring" for those cases), matching the brief's expectation that only the non-empty-patch tests fail.

**GREEN** — same command after the `derivePatch` rewrite:
```
✓ src/lib/analyticsPatch.test.ts (19 tests) 21ms
Test Files  1 passed (1)
     Tests  19 passed (19)
```
(12 pre-existing + 7 new = 19; all pre-existing tests unchanged and still passing, confirming `applyCrossFilterValue` is a pure extraction with no behavior change.)

### Type check

`cd shell && npx tsc --noEmit` — no output, exit clean (no type errors).

### Full shell unit suite

`cd shell && npm run test`:
```
Test Files  111 passed (111)
     Tests  867 passed (867)
Duration  40.68s
```
(Some stderr noise from an unrelated pre-existing CEL parse-error test — `exprBindings.test.ts` — is expected error-path logging, not a failure; that file shows `✓ src/builder/exprBindings.test.ts (7 tests)`.)

## Files changed

- `shell/src/lib/geometryBbox.ts` (new)
- `shell/src/lib/geometryBbox.test.ts` (new)
- `shell/src/lib/analyticsPatch.ts` (rewritten)
- `shell/src/lib/analyticsPatch.test.ts` (appended)

## Self-review

- **Completeness**: all brief steps implemented as literally specified, no deviation.
- **Quality**: `applyCrossFilterValue` extraction keeps the same three branches; new loop is a straightforward `Object.entries` scan with early `continue`s, matches existing style (comment in French per repo convention, mirroring the existing header comment).
- **Discipline**: no extra abstractions, no scope creep beyond the brief (e.g., no transitive/multi-hop link resolution — explicitly out of scope per the brief's own comment "un seul saut (pas de chaînage transitif)").
- **Double-fire check**: verified the "does not resolve a link declared on the same dataset as the target source" test passes — the link loop explicitly skips `originDatasetId === source.datasetId`, so the same-dataset direct path and the cross-dataset link path can't both act on `ds-1`'s own cross-filter entry.
- **Testing**: TDD followed exactly (RED confirmed for correct reason at each step, then GREEN). tsc clean. Full suite green with no regressions (867/867).

No issues or concerns found.

## Commit

`4debf7d` — `feat(shell): resolve cross-filter links (attribute + spatial) in derivePatch (SP-14n)`
