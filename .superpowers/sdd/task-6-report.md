# Task 6 report — `modal` widget (SP-14j)

## Status: DONE_WITH_CONCERNS

## Summary

Implemented `shell/src/builder/widgets/modal.tsx` (new widget kind `"modal"`)
and registered it in `shell/src/builder/widgets/index.tsx`, following TDD:
wrote `shell/src/builder/widgets/modal.test.tsx` first (verbatim from the
brief plus one timing fix — see below), confirmed all 5 tests failed with
`getWidget("modal")` undefined, implemented the widget, then confirmed all 5
pass, then ran the full unit suite (109 files / 827 tests, all green, no
regressions).

## Verified against real repo signatures

Read `LayoutEditor.tsx`, `dialog.tsx`, `ActionBusContext.tsx`, `registry.ts`,
`GridCanvas.tsx`, `WidgetHost.tsx`, `tabs.tsx` (Task 5 sibling), and
`index.tsx` before implementing. The brief's code matched all real
signatures (`Dialog({ open, onClose, title, wide, children })`,
`useBusAction(bus, widgetId, action, handler)`, `LayoutEditor({ items,
onChange, dataSources, breakpoint })`, `GridCanvas` props, `WidgetHost`
props). `LayoutEditor.tsx`'s `NESTED_EXCLUDE` array already contains
`"modal"` (and `"drawer"`) — Task 4 anticipated this widget, no change
needed there.

## Fix 1 (per pre-flagged instruction): missing `breakpoint` on nested `WidgetHost`

Same omission as Task 5's `tabs` widget: the brief's `Component` code for
`modal.tsx` called the nested `WidgetHost` inside `GridCanvas`'s
`renderItem` without `breakpoint={ctx.breakpoint}`:

```tsx
renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />}
```

Applied the same fix as the reviewer-approved Task 5 fix, mirroring
`tabs.tsx`'s own `Component` and `AppRenderer.tsx`'s top-level convention:

```tsx
renderItem={(item) => (
  <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} breakpoint={ctx.breakpoint} />
)}
```

Without it, any widget nested inside a modal would silently get
`ctx.breakpoint === undefined`.

## Fix 2 (new, found during this task): flaky test assertion in the brief's own test

The brief's test "closes on the close action too" calls `bus.emit("closer",
"clicked")` then immediately asserts
`screen.queryByRole("dialog")).not.toBeInTheDocument()` with no
`await`/`waitFor`. `ActionBus.emit` invokes the registered handler
synchronously (`setOpen(false)`), but that's not a React-tracked DOM event,
so the resulting re-render doesn't flush before the very next assertion —
the test failed deterministically (100% repro over 3 runs) with the dialog
still present in the DOM.

This is the exact same class of issue already handled correctly elsewhere
in this codebase: `shell/src/builder/widgets/form.test.tsx`'s "the reset bus
action clears the form" test (~line 353) wraps the post-`bus.emit`
assertion in `await waitFor(...)` for the identical reason (a comment there
even explains `ActionBus.emit` only routes through configured wiring, not a
direct call).

Fix applied in `modal.test.tsx`:
- imported `waitFor` from `@testing-library/react`.
- changed the closing assertion from
  `expect(screen.queryByRole("dialog")).not.toBeInTheDocument();` to
  `await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());`

After the fix, all 5 tests pass deterministically. There's a benign
`act(...)` warning on stderr for that same test (state update from
`bus.emit` not wrapped in `act`), which matches the existing precedent in
`form.test.tsx` for the same pattern (confirmed by running that pre-existing
test and seeing the identical warning) — not a regression, not something
introduced by this task.

## Files touched

- Created: `shell/src/builder/widgets/modal.tsx`
- Created: `shell/src/builder/widgets/modal.test.tsx` (brief's test plus the
  `waitFor` fix described above)
- Modified: `shell/src/builder/widgets/index.tsx` (import +
  `registerModalWidget()` call after `registerTabsWidget()`)

## Test results

- `cd shell && npx vitest run src/builder/widgets/modal.test.tsx` → 5/5 pass
- `cd shell && npx vitest run` → 109 files, 827 tests, all pass, no
  regressions

## Commit

`15f921f` — `feat(shell): modal container widget, opened/closed via the
action bus (SP-14j)`

Only `shell/src/builder/widgets/{modal.tsx,modal.test.tsx,index.tsx}` were
staged/committed. Note: `git status` showed several `.superpowers/sdd/*.md`
files (task briefs/reports/progress.md) as modified in the working tree at
the start of this task — these were pre-existing uncommitted changes from
other sessions, not touched by this task, and were deliberately left
unstaged.

## Concerns

- The two fixes above (nested `breakpoint` prop, and the test's `waitFor`)
  are both deviations from the brief's literal code. Both are justified by
  direct precedent already reviewed/approved in this same plan (Task 5) or
  already present elsewhere in the codebase (`form.test.tsx`), so confidence
  is high, but flagging per the "ask before proceeding, or fix the obvious
  ones and report" instruction.
