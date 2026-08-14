# Task 7 report — CameraControls + wire terrain/camera into MapEditorPage

## Summary

Implemented Task 7 of the 3D tiles + terrain plan in two TDD cycles, each with its
own commit, exactly as specified in `.superpowers/sdd/task-7-brief.md`.

1. **`CameraControls`** — new component with two range sliders (pitch 0–60°,
   bearing 0–360°) and a "Réinitialiser en 2D" button. Commit `7429760`.
2. **`MapEditorPage` wiring** — full-file replacement adding `TerrainPanel` +
   `CameraControls` to the editor aside, plus a `setCamera` handler that both
   patches `draft.view` and calls `mapViewRef.current?.flyTo(...)` for live
   camera feedback. Commit `ec95f11`.

Both commits are scoped to exactly the files named in the brief; `git status
--short` was checked before each `git add`/`git commit` and only the intended
files were staged (confirmed via `A`/`M` status lines). The unrelated
concurrent-work files (`shell/src/pages/VisualQueryWizardPage.tsx`/`.test.tsx`,
`CLAUDE.md`, the `.superpowers/sdd/*` docs) were never touched, added, or
committed.

## Files

- Created: `shell/src/map/CameraControls.tsx`
- Created: `shell/src/map/CameraControls.test.tsx`
- Modified: `shell/src/pages/MapEditorPage.tsx` (full-file replacement per brief)
- Modified: `shell/src/pages/MapEditorPage.test.tsx`

## TDD cycle 1 — CameraControls

- RED (Step 2): `npm run test -- src/map/CameraControls.test.tsx` failed with
  "Failed to resolve import './CameraControls'" — file didn't exist yet, as
  expected.
- Implemented `CameraControls.tsx` verbatim from the brief (Step 3).
- GREEN attempt (Step 4) surfaced a **test-file bug in the brief**, not an
  implementation defect: `toHaveValue(30)` (a JS number) against a
  `type="range"` input fails under the installed `@testing-library/jest-dom`
  (`6.9.1`). Its `getInputValue()` only special-cases `type="number"` inputs
  by coercing to `Number(...)`; for `type="range"` it falls through to the
  `default` branch and returns the raw string `inputElement.value`. A range
  input's DOM `.value` is always a string, so `toHaveValue(30)` can never pass
  for a range input on this jest-dom version — this is independent of how
  `CameraControls` itself is written (confirmed by reading
  `node_modules/@testing-library/jest-dom/dist/matchers-98b869c1.js`, function
  `getInputValue`, lines ~194–203). **Deviation applied**: changed the two
  assertions in `CameraControls.test.tsx` from `.toHaveValue(30)` /
  `.toHaveValue(120)` to `.toHaveValue("30")` / `.toHaveValue("120")` — this is
  the factually correct assertion for the real DOM state and preserves the
  test's intent (verify the rendered value) without touching production code
  or the component's public interface.
- GREEN (Step 4, re-run): all 4 tests pass.
- Step 5: committed `shell/src/map/CameraControls.tsx` +
  `shell/src/map/CameraControls.test.tsx` only. Commit `7429760`.

## TDD cycle 2 — MapEditorPage wiring

- Step 6: added the two new `vi.mock` blocks (`@deck.gl/geo-layers`,
  `@loaders.gl/tiles`) to `MapEditorPage.test.tsx`, added `fireEvent` to the
  `@testing-library/react` import, and appended the two new tests
  ("edits terrain and camera, then saves both" /
  "the camera reset button zeroes pitch and bearing in the saved view")
  verbatim, with one fix (below).
- RED (Step 7): `npm run test -- src/pages/MapEditorPage.test.tsx` — 2 new
  tests failed (no "Activer le terrain 3D" / camera slider labels existed
  yet), 5 pre-existing tests passed, as expected.
- Step 8: replaced `MapEditorPage.tsx` with the brief's full-file content
  verbatim, then made one necessary fix (below) to satisfy `tsc --noEmit`.
- GREEN attempt (Step 9) surfaced a **second test-file bug in the brief**:
  `userEvent.type(..., "https://example.test/dem/{z}/{x}/{y}.png")` silently
  mistyped the URL. `@testing-library/user-event`'s `type()` parses `{`/`}` as
  special-key syntax (documented in
  `node_modules/@testing-library/user-event/dist/cjs/keyboard/parseKeyDef.js`:
  "Brackets `{` and `[` can be escaped by doubling — e.g. `foo[[bar` translates
  to `foo[bar`"). Typed verbatim, it produced
  `https://example.test/dem/z/x/y.png` (braces silently dropped, no thrown
  error) instead of the literal template URL, so the saved-terrain assertion
  failed on a value that was never a `CameraControls`/`TerrainPanel`/
  `MapEditorPage` defect. Task 6's own `TerrainPanel.test.tsx` independently
  avoids this exact trap (it never types `{z}`-style URLs via `userEvent.type`,
  only asserts pre-set/short literal values), which corroborates this reading.
  **Deviation applied**: escaped each opening brace by doubling
  (`{{z}` / `{{x}` / `{{y}` — doubling `{` is sufficient per user-event's own
  escape rule; `}` needs no escaping outside a special-key span), landing on
  `"https://example.test/dem/{{z}/{{x}/{{y}.png"`, which types the literal
  string `https://example.test/dem/{z}/{x}/{y}.png` as intended.
- `tsc --noEmit` (Step 10) then surfaced a **third, this time real
  production-code** issue in the brief's verbatim `MapEditorPage.tsx`: inside
  the nested `function setCamera(...)` declaration, `draft.view.center` /
  `draft.view.zoom` were flagged `TS18047: 'draft' is possibly 'null'`.
  TypeScript's control-flow narrowing of the early-return null guard
  (`if (query.isError || !draft) return (...)`) does not propagate into the
  body of a nested function declaration that outlives the render pass — this
  is standard, intentional TS behavior (narrowing of outer bindings is not
  carried into closures/nested function bodies unless the binding's *declared
  type itself* is already non-nullable). The sibling helpers
  (`setPrintLayout`, `setTerrain`) sidestep this by only referencing the
  `setDraft` updater's own callback parameter `d`, never the outer `draft`
  directly — `setCamera` is the only one that also needs `draft.view.center`/
  `zoom` for the `flyTo` call outside the updater. **Deviation applied**:
  added one line, `const currentDraft = draft;`, immediately after the earlier
  narrowing point (so its inferred type is already `MapConfig`, not
  `MapConfig | null`), and referenced `currentDraft.view.center` /
  `currentDraft.view.zoom` inside `setCamera` instead of `draft.view.*`. No
  behavioral change — same value, just referenced through a binding whose
  static type doesn't require re-narrowing inside the closure.
- GREEN (Step 9 re-run + Step 10): `npm run test -- src/pages/MapEditorPage.test.tsx`
  → 7/7 pass (5 pre-existing + 2 new); `npx tsc --noEmit` → clean, no output.
- Full-suite sanity check: `npm run test` → 139 test files, 1132 tests, all
  green (includes the pre-existing, currently-uncommitted
  `VisualQueryWizardPage` tests from concurrent work — untouched, just
  confirmed not broken by this change).
- Step 11: committed `shell/src/pages/MapEditorPage.tsx` +
  `shell/src/pages/MapEditorPage.test.tsx` only. Commit `ec95f11`.

## Deviations from the brief (all test-file or narrow type-only, no behavior change)

1. `CameraControls.test.tsx`: `toHaveValue(30)`/`toHaveValue(120)` →
   `toHaveValue("30")`/`toHaveValue("120")` (jest-dom 6.9.1 range-input
   behavior).
2. `MapEditorPage.test.tsx`: DEM template URL typed via `userEvent.type` needed
   brace-escaping (`{{z}` etc.) to survive user-event's special-key parser
   intact.
3. `MapEditorPage.tsx`: added `const currentDraft = draft;` and used it inside
   `setCamera` instead of the outer `draft`, to satisfy `tsc --noEmit`'s
   closure-narrowing limitation. Purely a type-level fix; runtime behavior is
   identical (same object, read at the same point in time).

None of these touch the public component interfaces
(`CameraControls({ pitch, bearing, onChange })`, `MapConfig.terrain`/
`view.pitch`/`view.bearing` shape) specified in the brief.

## Verification commands run

```
cd shell && npm run test -- src/map/CameraControls.test.tsx        # 4/4 pass
cd shell && npm run test -- src/pages/MapEditorPage.test.tsx       # 7/7 pass
cd shell && npx tsc --noEmit                                       # clean
cd shell && npm run test                                           # 139 files / 1132 tests pass
```

## Commits

- `7429760` — `feat(shell): CameraControls, sliders pitch/bearing avec réinitialisation 2D`
- `ec95f11` — `feat(shell): MapEditorPage câble le terrain et la caméra 3D`
