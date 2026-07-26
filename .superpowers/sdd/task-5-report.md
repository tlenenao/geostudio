# Task 5 Report: Wire `ExplorerProvider`/`ExplorerDrawer` into `AppRenderer` (SP-14d)

Note: this report file previously held an unrelated report from an earlier plan's differently-numbered
"Task 5" (SP-14c, `AnalyticsContextIndicator` + `AppRenderer` wiring, commit `5833a33`). It has been
overwritten below with the current SP-14d Task 5 report, per this task's brief file path.

## What was implemented

Matches the brief exactly; no deviations of substance. The brief's line numbers had drifted slightly
(actual file was 202 lines, JSX block started at line 174 not 172) but the surrounding code (the
existing `AnalyticsContextIndicator` import, the `ActionBusProvider`/`VariablesProvider`/
`AnalyticsContextProvider`/`DataProvider`/`GridCanvas` JSX tree) matched the brief's assumed structure
exactly, so the insertion was a straightforward textual match against that context.

### `shell/src/builder/AppRenderer.tsx`
- Added two imports right after the existing `AnalyticsContextIndicator` import:
  ```tsx
  import { ExplorerProvider } from "./ExplorerContext";
  import { ExplorerDrawer } from "./ExplorerDrawer";
  ```
- Wrapped the existing subtree (`AnalyticsContextProvider` and everything inside it) in:
  ```tsx
  <ExplorerProvider enabled={mode !== "edit" && config.interactions === "auto"}>
    ...
  </ExplorerProvider>
  ```
  placed between `VariablesProvider` and `AnalyticsContextProvider`.
- Added `<ExplorerDrawer />` as a sibling right after the existing
  `{mode !== "edit" && config.interactions === "auto" && <AnalyticsContextIndicator />}` line, before
  `<ActionConditionBridge bus={bus} />`.
- The gating expression used for `ExplorerProvider`'s `enabled` prop is textually identical to the
  expression already gating `AnalyticsContextIndicator` — no new boolean, no risk of drift between
  the two.

### `shell/src/builder/AppRenderer.test.tsx`
- Extended the shared `stubClient` fixture (as specified in the brief) with `getDatasetConfig` and
  `getCollectionSchema` mocks, needed because with a `dataSources` entry carrying a `datasetId`, the
  `DataContext`/`ExplorerDrawer` machinery resolves dataset config; without these mocks the client
  interface would be missing methods the drill-down path expects.
- Appended the new test exactly as given in the brief:
  `"shows the explorer menu on an eligible widget only when interactions is auto and not edit mode"`,
  verifying the `Explorer`-labelled button (rendered by `ExplorerMenu` inside the `indicator` widget)
  appears in `runtime` + `interactions: "auto"`, and is absent in `edit` mode and in
  `interactions: "manual"` mode.

## Testing

### TDD Evidence

**RED** — before implementation:
```
cd shell && npx vitest run src/builder/AppRenderer.test.tsx
```
Result: 1 failed / 27 passed. Failure:
```
❯ src/builder/AppRenderer.test.tsx:508:23
expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();
Unable to find a label with the text of: Explorer
```
This matches the brief's predicted failure exactly — `ExplorerProvider` not yet mounted, so
`useExplorerEnabled()` defaults to `false` and `ExplorerMenu` renders nothing.

**GREEN** — after implementation:
```
cd shell && npx vitest run src/builder/AppRenderer.test.tsx
```
Result: `Test Files 1 passed (1)`, `Tests 28 passed (28)`.

**Full suite** — regression check:
```
cd shell && npm run test
```
Result: `Test Files 99 passed (99)`, `Tests 706 passed (706)`. Zero regressions. (Some pre-existing
stderr noise from unrelated CEL-expression tests intentionally exercising error paths — not
failures, present before this change.)

## Files changed

- `/home/lenen/projets/geostudio/shell/src/builder/AppRenderer.tsx` (imports + JSX wiring)
- `/home/lenen/projets/geostudio/shell/src/builder/AppRenderer.test.tsx` (fixture update + new test)

## Commit

`88d5b14` — `feat(shell): mount ExplorerProvider/ExplorerDrawer in AppRenderer, gated like the
context indicator (SP-14d)`.

`git status --short` before commit showed only these two files staged
(`M  shell/src/builder/AppRenderer.test.tsx`, `M  shell/src/builder/AppRenderer.tsx`); unrelated
pre-existing worktree changes (`.superpowers/sdd/*` docs, an unrelated new plan doc) were left
untouched and unstaged.

## Self-review

- **Completeness**: menu never shows in edit mode (asserted by the test's rerender to
  `mode="edit"`); never shows when `interactions !== "auto"` (asserted by the test's rerender to
  `interactions: "manual"`); confirmed by reading the final JSX that `ExplorerProvider`'s `enabled`
  prop and `AnalyticsContextIndicator`'s render condition use the byte-identical expression
  `mode !== "edit" && config.interactions === "auto"` — no duplicated/divergent gating logic exists
  anywhere in the file.
- **Quality**: no unrelated changes to `AppRenderer.tsx` — the diff is exactly the two-line import
  addition and the wrap/insert in the JSX tree. `ExplorerDrawer` is unconditionally rendered once
  inside `ExplorerProvider` (correct: it self-gates via `useExplorerTarget()` returning `null` until
  `open()` is called, and `open()` itself is a no-op when `enabled` is false per
  `ExplorerContext.tsx`'s own `open` callback — so no separate gate is needed around
  `<ExplorerDrawer />` itself).
- **Testing**: the new test's 3 assertions all pass (auto+runtime shows the "Explorer" label; edit
  mode hides it; manual interactions hides it). Full suite: 99 files / 706 tests, zero regressions,
  pristine output.

## Issues or concerns

None. The wiring is a direct, minimal application of the existing `AnalyticsContextIndicator` gating
pattern, extended to a second consumer of the identical boolean — by construction the two can never
disagree.

---

## Follow-up: Code review finding fix (2026-07-26)

### Finding

Post-review code quality pass identified that the gating expression
`mode !== "edit" && config.interactions === "auto"` was duplicated as two independent literals:
- Line 177: `<ExplorerProvider enabled={mode !== "edit" && config.interactions === "auto"}>`
- Line 183: `{mode !== "edit" && config.interactions === "auto" && <AnalyticsContextIndicator />}`

This created a maintenance risk: editing one without the other could cause unintended divergence.

### Fix applied

Hoisted the expression into a single local variable `const analyticsUiEnabled = mode !== "edit" && config.interactions === "auto";`
placed near line 97 alongside the existing `const editable = mode === "edit";` pattern, then replaced both
literal occurrences with references to `analyticsUiEnabled`.

### Tests run

- **`AppRenderer.test.tsx` unit tests**: `npx vitest run src/builder/AppRenderer.test.tsx` → 28 passed ✓
- **Full suite regression check**: `npm run test` → 706 tests passed (99 files) ✓
- **TypeScript check**: `npx tsc --noEmit` → clean ✓

### Commit

`df409f7` — `refactor(shell): hoist shared analytics-UI gating expression in AppRenderer (SP-14d)`

### Files changed

- `/home/lenen/projets/geostudio/shell/src/builder/AppRenderer.tsx` (line 98: added const; lines 177, 183: replaced with variable reference)
