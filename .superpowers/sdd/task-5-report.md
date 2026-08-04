# Task 5 report — `tabs` widget (SP-14j)

## Status: DONE_WITH_CONCERNS

## Commit

`78b1229` — `feat(shell): tabs container widget with a nested LayoutEditor per tab (SP-14j)`

Files changed:
- `shell/src/builder/widgets/tabs.tsx` (new)
- `shell/src/builder/widgets/tabs.test.tsx` (new)
- `shell/src/builder/widgets/index.tsx` (import + `registerTabsWidget()` call)

## What was verified against the real repo before implementing

- `LayoutEditor` (`shell/src/builder/LayoutEditor.tsx`): signature
  `{ items, onChange, dataSources, breakpoint }` matches the brief exactly.
  It already excludes `"tabs"`, `"modal"`, `"drawer"` from its palette
  (`NESTED_EXCLUDE`), so nesting containers inside containers isn't offered
  yet — consistent with this being the first of three container tasks.
- `GridCanvas` (`shell/src/builder/GridCanvas.tsx`): signature matches the
  brief (`items, breakpoint, editable, selectedId, onSelect, onMoveItem,
  renderItem`).
- `WidgetHost` (`shell/src/builder/WidgetHost.tsx`): matches the brief's
  props but **also accepts an optional `breakpoint` prop** that the brief's
  `Component` didn't pass through to the nested `WidgetHost` call inside
  `GridCanvas`'s `renderItem`.
- `registry.ts`: `WidgetContext`, `registerWidget`, `getWidget`,
  `_resetRegistry` all match the brief.

## Deviations from the brief's literal code

1. **`breakpoint` propagation to the nested `WidgetHost`.** The brief's
   runtime `Component` passed `breakpoint` to `GridCanvas` but not to the
   `WidgetHost` it renders per item:
   ```tsx
   renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />}
   ```
   `shell/src/builder/AppRenderer.tsx:198` (the top-level renderer) always
   passes `breakpoint={bp}` to its own `WidgetHost` call — that's exactly
   how `ctx.breakpoint` gets populated for any widget in the first place
   (Task 1). Since a tab's items could themselves need `ctx.breakpoint`
   (e.g. a widget reading it directly, or a future container type once
   `NESTED_EXCLUDE` is relaxed), I added the same propagation for
   consistency:
   ```tsx
   renderItem={(item) => (
     <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} breakpoint={ctx.breakpoint} />
   )}
   ```
   This is additive only — no test depends on it — so it doesn't change any
   test outcome, just closes a latent inconsistency with the established
   `AppRenderer` convention.

2. **Test file needed two additions the brief omitted**, both required
   because `tabs.test.tsx` renders real `text` widgets through `WidgetHost`
   (directly in the runtime test, and via the nested `LayoutEditor` in the
   PropsPanel item-editing test):
   - `vi.mock("../../auth/useAuth", ...)` — `WidgetHost` calls `useAuth()`,
     which throws outside an `<AuthProvider>` tree. Every other test file
     that renders `WidgetHost` transitively (`WidgetHost.test.tsx`,
     `LayoutEditor.test.tsx`, `AppRenderer.test.tsx`) mocks this the same
     way; I copied the exact pattern from `LayoutEditor.test.tsx`.
   - A `QueryClientProvider` + `ItemClientProvider` `wrapper`, applied via
     `render(ui, { wrapper })` on the two `render()` calls that exercise a
     selected `text` item — the `text` widget's `PropsPanel` renders
     `DataSourceSelect`, which calls `useItems()` and needs an item client
     in context even when the query is disabled. Copied verbatim from
     `LayoutEditor.test.tsx`'s own wrapper/comment, which documents the
     same need.

   Without these two additions, tests 1 and 6 from the brief failed with
   `Cannot read properties of undefined (reading 'isLoading')` — confirmed
   by running the brief's test file as-given first, so this was caught by
   the TDD "run to see it fail correctly" step, not skipped over.

Everything else — widget shape (`props.tabs: Array<{id,label,items}>`),
`PropsPanel` behavior (add/rename/reorder/remove, refusing to remove the
last tab, per-tab `LayoutEditor` for nested items), and runtime `Component`
behavior (first tab shown by default, click-to-switch, static tab bar in
edit mode) — was implemented exactly as specified in the brief.

## Verification

- `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx` — confirmed
  FAIL first (6/6 failing, `getWidget("tabs")` undefined / missing
  provider), then confirmed PASS after implementation + test fixture fixes
  (6/6 passing).
- `cd shell && npx vitest run` — full suite: **108 files, 822 tests, all
  passing**. (Some stderr noise from `exprBindings.test.ts` is expected
  error-path logging from that pre-existing test, not a new failure.)

## Concerns for the reviewer

- The `breakpoint` propagation fix (item 1 above) is untested directly —
  no test asserts `ctx.breakpoint` reaches a nested widget's `Component`
  through tabs. It mirrors the `AppRenderer` convention and is safe (an
  additional optional prop), but flagging it since it's a change beyond
  the brief's literal code.
- `NESTED_EXCLUDE` in `LayoutEditor.tsx` already anticipates `"modal"` and
  `"drawer"` (Tasks 6/7) — nothing to change there for this task.
