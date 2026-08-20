# Task 12 report — CopilotPanel.tsx + AppBuilderPage.tsx wiring

## What was implemented

- Created `shell/src/builder/copilot/CopilotPanel.tsx`: a chat panel component
  (message history, textarea, "Envoyer" button) taking props
  `{ itemId, config, activePageId, setDraft }`. On send, it calls
  `client.copilotTurn(itemId, { message, history, mcpToken, currentConfig, clientTools })`
  (via `useItemClient()`), appends the reply to local history, and — if the
  response includes `clientOps` — reduces them through `applyClientOp` and
  commits the result via a **single** `setDraft` call (so a whole copilot
  turn lands as one entry in SP-19's undo stack). Errors are caught and shown
  via a `role="alert"` paragraph; no crash. No dedicated undo button — reuses
  the AppBuilderPage toolbar's existing Annuler/Rétablir (single global undo
  stack), per the corrected design note in the spec (commit 8f45d95).
- Created `shell/src/builder/copilot/CopilotPanel.test.tsx` (3 tests, exactly
  as specified in the brief).
- Wired `CopilotPanel` into `shell/src/pages/AppBuilderPage.tsx`:
  - Import added right after the `AppExportPanel` import.
  - `const copilotEnabled = instanceQuery.data?.copilotEnabled === true;`
    added right after the `appExportEnabled` derivation.
  - JSX block `{copilotEnabled && (<>…<CopilotPanel .../></>)}` added right
    after the `appExportEnabled && (...)` block, inside the same `<aside>`.

Both files match the brief's code verbatim; no deviations were needed — all
brief anchors (`AppExportPanel` import line, `appExportEnabled` derivation,
the `appExportEnabled && (...)` JSX block) matched the current
`AppBuilderPage.tsx` exactly, and all consumed interfaces
(`applyClientOp`/`RawClientOp` from Task 9, `buildClientToolSchemas` from
Task 8, `useMcpToken` from Task 10, `ItemClient.copilotTurn`/`CopilotMessage`/
`CopilotTurnResult` from Task 11, `InstanceInfo.copilotEnabled` from Task 11,
`useUndoableDraft`'s `setDraft` signature from SP-19) matched what the brief
assumed, verified by reading each file before writing.

## TDD evidence

**RED** — `cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx`
before creating `CopilotPanel.tsx`:
```
FAIL  src/builder/copilot/CopilotPanel.test.tsx [ src/builder/copilot/CopilotPanel.test.tsx ]
Error: Failed to resolve import "./CopilotPanel" from "src/builder/copilot/CopilotPanel.test.tsx". Does the file exist?
Test Files  1 failed (1)
```
Fails for the expected reason (module not found).

**GREEN** — same command after implementing `CopilotPanel.tsx`:
```
✓ src/builder/copilot/CopilotPanel.test.tsx (3 tests) 407ms
Test Files  1 passed (1)
     Tests  3 passed (3)
```

**Full build**: `cd shell && npm run build` → `tsc --noEmit && vite build`
succeeded, no type errors, bundle built (2 chunk-size warnings, pre-existing,
unrelated to this change).

**Full test suite**: `cd shell && npm run test` →
```
Test Files  152 passed (152)
     Tests  1231 passed (1231)
```
(One test file prints an expected CEL parse error to stderr as part of an
assertion that the parser throws — not a failure.)

## Files changed

- `shell/src/builder/copilot/CopilotPanel.tsx` (new)
- `shell/src/builder/copilot/CopilotPanel.test.tsx` (new)
- `shell/src/pages/AppBuilderPage.tsx` (modified: import, `copilotEnabled`
  derivation, JSX block)

## Self-review findings

- Confirmed `activePage` (the `AppBuilderPage` local var, passed as
  `activePageId` prop) is always a non-null string by the time this JSX
  renders — the page has an earlier early-return
  (`if (query.isError || !draft || !activeLayout || !activePage) return …`)
  guarding the whole builder body, so passing it directly to
  `CopilotPanel`'s `activePageId: string` prop is sound (also confirmed by
  `tsc --noEmit` passing with no cast needed).
- Confirmed `setDraft`'s actual type
  (`(update: AppConfig | null | ((prev) => AppConfig | null)) => void` in
  `useUndoableDraft.ts`) is compatible with `CopilotPanel`'s narrower prop
  type (`(update: (prev) => AppConfig | null) => void`) — passing the
  broader setter where the narrower type is expected typechecks fine
  (contravariance in the right direction).
- Verified only the 3 intended files were staged/committed (`git add` with
  explicit paths, `git status --short` checked before commit) — the working
  tree had several unrelated pre-existing modifications/untracked files
  (other task briefs/reports, `deploy/postgis/Dockerfile`, a vision doc) that
  were correctly left out of this commit.
- No dedicated undo button added to `CopilotPanel`, and it does not consume
  `undo`/`redo`/`canUndo`/`canRedo` — matches the corrected design note.

## Issues or concerns

None. All anchors matched exactly as expected, no signature mismatches with
Task 8/9/10/11 outputs, all tests pass, build is clean.
