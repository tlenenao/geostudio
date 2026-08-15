# Task 3 report: wire `useUndoableDraft` into `AppBuilderPage.tsx`

## Status: DONE_WITH_CONCERNS

One of the 5 new tests, as given verbatim in the brief, is self-contradictory
and cannot pass under any timing. I diagnosed the exact mechanism, then
rewrote that single test (only) to remove the confound, using a pattern
already established elsewhere in the same file. All other brief content
(the four `AppBuilderPage.tsx` edits, the other 4 new tests) was applied
verbatim, unmodified.

## What was implemented

1. **Step 1 (RED)**: appended the 5 new tests verbatim from the brief to
   `shell/src/pages/AppBuilderPage.test.tsx`.
2. **Step 2**: ran `npx vitest run src/pages/AppBuilderPage.test.tsx` — all 5
   new tests failed as expected (no "Annuler"/"Rétablir" buttons exist yet),
   13 pre-existing tests still passed. Confirmed RED.
3. **Step 3**: applied all four search/replace edits to
   `shell/src/pages/AppBuilderPage.tsx` exactly as specified in the brief
   (import, `draft`/`setDraft` → `useUndoableDraft()` destructure, seeding
   effect → `seedDraft` + new keyboard-shortcut effect, toolbar buttons).
   All four snippets matched the file verbatim before editing.
4. **Step 4 (first run)**: 4 of the 5 new tests passed; 1 failed
   deterministically (reproduced 3× in a row, not flaky):
   `"a burst of keystrokes in visibleWhen collapses into one undo step once
   blurred"` — `expect(area).toHaveValue("")` received `"vars.x == 'a'"`.

## Root cause investigation (found and fixed within this task's scope)

The failing test, as literally given in the brief, does back-to-back with no
gap:
```
await userEvent.click(screen.getByRole("button", { name: "Texte" }));  // addWidget → 1st setDraft call
const area = screen.getByLabelText(...);
await userEvent.type(area, "vars.x == 'a'");                            // 13 more setDraft calls
```

`useUndoableDraft`'s coalescing rule (by design — see its own doc comment
and its own test `"a rapid burst of setDraft calls within the window
collapses into one undo step"` in `useUndoableDraft.test.tsx`, Task 2,
already committed as `fa614ad`) is: the first `setDraft` call after the last
flush captures the pre-burst baseline; every subsequent `setDraft` call
within 400ms of the *previous* call extends the same burst without
re-capturing. It doesn't distinguish "a discrete click action" from "a
typing burst" — only the wall-clock gap between consecutive `setDraft`
calls matters.

I instrumented `flush`/`setDraft` with temporary `console.log` calls
(reverted immediately after diagnosis — `git diff --stat
shell/src/builder/useUndoableDraft.ts` is empty, confirmed both before and
after this investigation) and reran just this test: the "Texte" click and
all 13 keystrokes produced exactly 1 baseline capture followed by 13
extend-only calls, then exactly one flush. With real timers and no
artificial delay between the click and the typing, the widget-add and the
entire typed string merge into a single undo step. `Ctrl+Z` then undoes
*both* — removing the widget entirely (confirmed via
`document.body.textContent` showing `"...Aucun widget sélectionné."` post-
undo), not just the typed text. The `area` textarea reference is left
pointing at a now-detached DOM node, which is why it still reports its last
live value (`"vars.x == 'a'"`) instead of `""`.

**This is not a timing artifact fixable by adding a delay — the test's two
assertions are mutually exclusive under the current whole-config-snapshot
undo model, regardless of timing:**

- If the widget-add and typing merge into one step (what actually happens
  with real timers and near-zero gap): one `Ctrl+Z` removes the widget
  outright → `Annuler` correctly disables, but `area` is a detached node,
  not `""` — `toHaveValue("")` can never pass.
- If forced apart into two separate steps (e.g. waiting for the widget-add
  to flush before typing starts): one `Ctrl+Z` pops just the typing step,
  correctly leaving the widget in place with `visibleWhen` cleared → `area`
  correctly reads `""`, but the widget-add step is still on the stack, so
  `Annuler` stays enabled — `toBeDisabled()` can never pass.

Neither timing works. The two assertions together only make sense if
**adding the widget isn't itself an undo-tracked edit at all** — i.e. if
the widget already exists (seeded) before the burst under test starts, and
the entire test is really about *only* the visibleWhen keystrokes.

## Resolution

Rewrote **only this one test** to seed a pre-existing widget via
`getAppConfig` (the exact same `withItem` pattern the brief's own two other
new tests — the GridCanvas move/undo tests just above it in the same
file — already use), then select it via the GridCanvas "Sélectionner
widget-w1" button (which only touches `selectedId`, a separate `useState`,
never `setDraft`) instead of adding it via the palette click immediately
before typing. This isolates the burst under test to exactly the 13
typed keystrokes, with the widget itself outside the undo stack (seeded,
not edited) — matching what the test's assertions actually require. Added
a code comment explaining why, so a future reader isn't left to
re-derive this.

No other test, and no non-test file, was touched to make this pass.
`shell/src/builder/useUndoableDraft.ts` (Task 2's file) was not modified —
this stayed within Task 3's declared scope throughout.

## Testing

- **RED**: `npx vitest run src/pages/AppBuilderPage.test.tsx` → 5 new tests
  failed (no Annuler/Rétablir buttons), 13 pre-existing passed.
- **GREEN** (after Step 3 edits + the one test rewrite): `npx vitest run
  src/pages/AppBuilderPage.test.tsx` → **18/18 passed**, all 5 new tests
  included. Re-ran 3× in a row to rule out flakiness from the timing
  investigation — stable every time.
- **Full shell suite**: `npm run test` → **146 test files passed, 1208
  tests passed** (0 failed). The `CelParseError` line visible in the raw
  output is expected stderr from `exprBindings.test.ts` exercising invalid-
  expression handling — that file's 7 tests all pass; not a regression.
- **Typecheck**: `npx tsc --noEmit` → initially reported `'AppConfig' is
  declared but never used` (`AppConfig` import in `AppBuilderPage.tsx`
  became unused once `useState<AppConfig | null>` was replaced by the
  hook's inferred type — a direct, in-scope consequence of the Step 3 edit,
  not present in the brief's snippets since they don't touch that import
  line). Fixed by removing `AppConfig` from the type-only import. Reran →
  clean, no errors.

## Files changed

- `shell/src/pages/AppBuilderPage.tsx` — the four edits from Step 3,
  applied verbatim, plus removal of the now-unused `AppConfig` type import
  (necessary for `tsc --noEmit` to pass; not itself in the brief but a
  direct consequence of applying it).
- `shell/src/pages/AppBuilderPage.test.tsx` — 5 new tests appended; 4 are
  verbatim from the brief, 1 (`"a burst of keystrokes in visibleWhen
  collapses into one undo step once blurred"`) was rewritten to seed the
  widget instead of adding it via click, for the reason above.
- `shell/src/builder/useUndoableDraft.ts` — untouched (confirmed via `git
  diff --stat`, empty).

## Commit

`ad67989` — `feat(shell): AppBuilderPage gains undo/redo — Ctrl+Z/Ctrl+Shift+Z + toolbar buttons (SP-19)`

## Self-review

- **Completeness**: all four `AppBuilderPage.tsx` edits from the brief are
  present; toolbar buttons render with exact French labels "Annuler"/
  "Rétablir"; keyboard shortcuts wired (`Ctrl+Z`/`Cmd+Z` undo,
  `Ctrl+Shift+Z`/`Cmd+Shift+Z` redo), ignored while focus is in an
  `<input>`/`<textarea>`/`contentEditable` element.
- **Discipline**: no panel/widget file touched (verified: `git status`
  shows only the two declared files changed by me, plus pre-existing
  unrelated changes to `.superpowers/sdd/*` from the surrounding session
  that I did not make). `useUndoableDraft.ts` untouched.
- **Quality**: the one test rewrite is minimal, mirrors an existing pattern
  in the same file (not a novel approach), and is commented to explain the
  "why" for future readers — this isn't a weakened assertion, it's a
  corrected test setup that still fully exercises burst-coalescing +
  blur-triggered flush, which is the test's actual stated purpose.
- **Testing**: targeted file green (18/18, stable across repeated runs),
  full suite green (1208/1208), typecheck clean.

## Concerns

- **One new test deviates from the brief's literal text.** I'm confident in
  the diagnosis (reproduced the contradiction from both angles — merged and
  separated timing — and confirmed via DOM inspection, not just assertion
  failure), but flagging clearly since "use the exact code in the brief"
  was an explicit instruction. If the plan's author had a different
  resolution in mind (e.g. changing the undo model to keep widgets across
  an undo of a value edited right after creation), that's a design
  decision that would need to go through `useUndoableDraft.ts` (Task 2,
  already committed) — out of my scope, and not what I did here.
- Worth noting for whoever reviews Task 2's design later: the coalescing
  window treats *any* two `setDraft` calls less than 400ms apart as one
  burst regardless of what UI action triggered them. In real human usage
  this is very unlikely to bite (add-widget-then-immediately-type-into-a-
  not-yet-focused-field in under 400ms isn't realistic finger speed), but
  it's a real edge case worth being aware of, not just a test artifact.
