# Task 4 report — `MapView.tsx`: render `Tile3DLayer`, terrain, and persist camera

## Status: DONE

## Summary

Implemented Task 4 of the 3D Tiles + terrain plan exactly per the brief
(`.superpowers/sdd/task-4-brief.md`), with one necessary correction (see
"Deviation from the brief" below). Followed TDD: dependencies → test doubles
→ failing tests (RED) → full-file `MapView.tsx` replacement → passing tests
(GREEN) → type-check → commit.

## Steps executed

1. **Dependencies** (`shell/package.json`): added `@deck.gl/geo-layers` and
   `@loaders.gl/core` at `^9.0.0`/`^4.3.0` per the brief. Ran `npm ls
   @deck.gl/core` first — installed version is `9.3.5` (not `9.0.x`), but
   `npm install` with the brief's ranges resolved cleanly with no peer
   conflicts (`@deck.gl/geo-layers@9.3.10`, `@loaders.gl/core@4.4.3`).

2. **Test doubles**:
   - `shell/src/test/MockDeckgl.ts`: added `Tile3DLayer` mock class, verbatim.
   - `shell/src/test/MockLoadersGl.ts`: created, verbatim.
   - `shell/src/test/MockMaplibreMap.ts`: added `pitch?`/`bearing?` to
     `opts` type, added `terrain: unknown = null` field, added
     `getPitch()`/`getBearing()`/`setTerrain(spec)` methods — verbatim.

3. **Failing tests** (`shell/src/map/MapView.test.tsx`): added the two new
   `vi.mock` blocks (adjusted per the deviation below), replaced the two
   existing moveend tests with the three brief-specified versions
   (pitch/bearing in payload), and appended the 8 new tests (pitch/bearing
   init/default, tiles3d mount/hide/legend/no-native-layer, terrain
   enable/default-exaggeration/clear) — all verbatim from the brief.
   Confirmed RED: `npm run test -- src/map/MapView.test.tsx` → 9 failed, 26
   passed (the 26 were pre-existing tests unaffected by the new assertions).

4. **Implementation** (`shell/src/map/MapView.tsx`): replaced the full file
   with the brief's Step 5 content verbatim, with one import path fix (see
   deviation below). All existing functionality (highlight, onFeatureClick,
   onReady/hideLegend for export-render mode, layer isolation try/catch) was
   preserved as-is since the brief's replacement already contained it.

5. **GREEN**: `npm run test -- src/map/MapView.test.tsx` → 35/35 passed.

6. **Type-check**: `npx tsc --noEmit` → exit 0, no errors.

7. **Full suite regression check** (not in the brief's steps, done for
   safety given concurrent unrelated work in the tree): `npm run test` →
   137 test files, 1118 tests, all passed.

8. **Commit**: staged exactly the 7 files listed in the brief's Step 8 git
   add command, individually (never `-A`/`-a`), verified via `git status
   --short` before and after staging that no unrelated file (e.g.
   `shell/src/pages/VisualQueryWizardPage.tsx`, `core/app/pipelines/*`,
   `shell/src/builder/pipeline/PipelineNodeInspector.tsx`, the `.superpowers/sdd/*`
   docs) was included. Commit: `661383c` — "feat(shell): MapView rend les
   couches tiles3d et le terrain, persiste pitch/bearing".

## Deviation from the brief (and why)

The brief's Step 1/3/5 specify `@loaders.gl/tiles` as the package exporting
`Tiles3DLoader`. This is incorrect for the installed loaders.gl 4.4.x line:
`Tiles3DLoader` is exported by **`@loaders.gl/3d-tiles`**, not
`@loaders.gl/tiles`. Verified two ways:

- `grep -rl "Tiles3DLoader" node_modules/@loaders.gl/*/dist/*.d.ts` shows it
  only in `@loaders.gl/3d-tiles/dist/tiles-3d-loader.d.ts` (re-exported from
  `@loaders.gl/3d-tiles/dist/index.d.ts`), not in `@loaders.gl/tiles`.
- deck.gl's own `Tile3DLayer` type declaration
  (`node_modules/@deck.gl/geo-layers/dist/tile-3d-layer/tile-3d-layer.d.ts`)
  itself does `import { Tiles3DLoader } from '@loaders.gl/3d-tiles';` and
  types its `loader?` prop as `typeof Tiles3DLoader` from that package.

Using the brief's exact package name (`@loaders.gl/tiles`) would have
compiled the mocked test suite (since the vi.mock intercepts the import
before resolution) but failed `tsc --noEmit` with `TS2305: Module
"@loaders.gl/tiles" has no exported member 'Tiles3DLoader'` — confirmed this
by running tsc with the brief's exact wording first, saw the error, then
applied the fix.

**Fix applied** (three small edits, all other content unchanged):
- `shell/package.json`: dependency is `"@loaders.gl/3d-tiles": "^4.3.0"`
  instead of `"@loaders.gl/tiles": "^4.3.0"` (alphabetically before
  `@loaders.gl/core`, since `3` < `c`). `@loaders.gl/core` is unchanged.
- `shell/src/map/MapView.tsx`: `import { Tiles3DLoader } from
  "@loaders.gl/3d-tiles";` instead of `"@loaders.gl/tiles"`.
- `shell/src/map/MapView.test.tsx`: `vi.mock("@loaders.gl/3d-tiles", ...)`
  instead of `vi.mock("@loaders.gl/tiles", ...)`.

`shell/src/test/MockLoadersGl.ts` content is unchanged (still exports the
same `Tiles3DLoader` mock object) — only which real module path it's mocked
under changed. `@loaders.gl/tiles` remains present in the dependency tree
as a transitive dependency of `@deck.gl/geo-layers` (used for tileset
traversal, not directly imported by this file), so nothing regresses; it's
just not a direct `package.json` dependency since `MapView.tsx` doesn't
import anything from it directly.

## Verification evidence

- `npm ls @deck.gl/geo-layers @loaders.gl/core @loaders.gl/3d-tiles` →
  `@deck.gl/geo-layers@9.3.10`, `@loaders.gl/core@4.4.3` (deduped),
  `@loaders.gl/3d-tiles@4.4.4` (both direct and deduped-under-geo-layers).
- RED: `npm run test -- src/map/MapView.test.tsx` → 9 failed / 26 passed
  (before implementation).
- GREEN: `npm run test -- src/map/MapView.test.tsx` → 35/35 passed (after
  implementation and the `@loaders.gl/3d-tiles` fix).
- `npx tsc --noEmit` → exit 0.
- `npm run test` (full shell suite) → 137 files / 1118 tests, all passed.
- `git status --short` reviewed before and after `git add` — confirmed only
  the 7 target files moved to staged; all pre-existing unrelated
  modifications (`core/app/pipelines/*`, `core/tests/test_pipeline_*`,
  `shell/src/api/types.ts`, `shell/src/builder/pipeline/
  PipelineNodeInspector.*`, `shell/src/pages/VisualQueryWizardPage.*`, the
  `.superpowers/sdd/*` docs) remained untouched/unstaged.

## Files changed (this task's commit `661383c`)

- `shell/package.json` — added `@deck.gl/geo-layers`, `@loaders.gl/3d-tiles`
  (not `@loaders.gl/tiles` — see deviation), `@loaders.gl/core`.
- `shell/package-lock.json` — regenerated by `npm install`.
- `shell/src/map/MapView.tsx` — full-file replacement per brief Step 5
  (with the one import-path fix), adds `tiles3d` layer rendering via the
  deck.gl overlay, `applyTerrain()` (MapLibre native `setTerrain`/raster-dem
  source), pitch/bearing on map init, `onViewChange` payload gains
  `pitch`/`bearing`, `MapViewHandle.flyTo` accepts optional
  `pitch`/`bearing`.
- `shell/src/map/MapView.test.tsx` — two new `vi.mock` blocks (one for
  `@deck.gl/geo-layers`, one for `@loaders.gl/3d-tiles`), rewritten moveend
  tests, 8 new tests appended.
- `shell/src/test/MockDeckgl.ts` — added `Tile3DLayer` mock class.
- `shell/src/test/MockLoadersGl.ts` — new file, `Tiles3DLoader` mock const.
- `shell/src/test/MockMaplibreMap.ts` — `opts.pitch`/`opts.bearing`,
  `terrain` field, `getPitch()`/`getBearing()`/`setTerrain()`.

## Interfaces produced (for Task 7 consumption)

- `MapView` renders `tiles3d`-kind `MapLayer`s via the existing deck.gl
  `MapboxOverlay` (alongside `deck`-kind layers), skipping them in the
  MapLibre-native `applyLayers` path.
- `MapView` applies/clears `map.setTerrain(...)` + a `raster-dem` source
  (`__terrain__`) from `MapConfig.terrain` (`MapTerrainConfig | null`),
  reactively on `config.terrain` changes.
- `MapViewHandle.flyTo` now accepts optional `pitch`/`bearing`.
- `onViewChange` payload now includes `pitch: number; bearing: number`
  (read live from `map.getPitch()`/`map.getBearing()`).
- Map is initialized with `pitch: config.view.pitch ?? 0` and
  `bearing: config.view.bearing ?? 0`.

## Concerns for downstream tasks

- None functional. The one thing worth flagging explicitly to whoever
  reviews the branch as a whole: `@loaders.gl/tiles` (brief's originally
  named package) is **not** a direct dependency of `shell/package.json` in
  the final state — `@loaders.gl/3d-tiles` is. If any later task's brief
  text also references `@loaders.gl/tiles` by name expecting `Tiles3DLoader`
  from it, that reference has the same error and should be read as meaning
  `@loaders.gl/3d-tiles`.
