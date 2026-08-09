# SP-17a Task 11 — ExportPanel (bouton + dialogue + poll) + intégration — Report

## What was implemented

- `shell/src/builder/print/ExportPanel.tsx` (new): `ExportPanel({ itemId })`.
  - Button "Exporter" opens a `Dialog` (reused `../../ui/dialog` component,
    role="dialog", ESC/backdrop close — consistent with `ImportFileButton`
    style rather than the brief's raw `<div role="dialog">`) offering PNG/PDF.
  - On format click: calls `client.createExport(itemId, format)`, then polls
    `client.getExportJob(jobId)` via a **manual recursive async/setTimeout
    loop** (not `useQuery`/`refetchInterval`), matching the pattern in
    `PipelineRunPanel.tsx` / `ImportFileButton.tsx`.
  - Poll interval: 1500ms, same as the two reference implementations.
  - On `status === "done"`: renders a download `<a href={resultUrl} download>`.
  - On `status === "error"`: renders `job.error` via `role="alert"`.
  - On `createExport` rejection or any exception surfacing out of the poll
    loop itself (e.g. a `getExportJob` network failure): caught in the same
    `try/catch` in `onExport`, shown as `role="alert"` with a fixed French
    message "Échec de l'export." (deliberately not raw `e.message` — see
    TDD evidence below, the brief's own suggested implementation would have
    failed its own test 3).
  - **Extra safety beyond the brief's literal snippet**: a `mountedRef` +
    `timerRef` guard. `PipelineRunPanel`/`ImportFileButton` (the cited
    reference patterns) do not actually have unmount cleanup in this
    codebase today — I added it here because this task's brief and
    self-review checklist explicitly require "no setState after unmount, no
    leaked timer", and `ExportPanel` is more likely than those two to be
    unmounted mid-poll (dialog panel next to page navigation). Every
    `setState` after an `await` is gated on `mountedRef.current`; the
    pending `setTimeout` is cleared on unmount via a `useEffect` cleanup.

- `shell/src/builder/print/ExportPanel.test.tsx` (new): 5 tests (brief asked
  for 3; I added 2 more to nail down cases the self-review checklist calls
  out explicitly):
  1. creates export job on click, polls until `done`, shows download link.
  2. surfaces a job-level `error` status via `role="alert"`.
  3. surfaces a `createExport` rejection via `role="alert"` (message must
     match `/échec/i`).
  4. *(added)* surfaces a network failure **during polling itself** (a
     `getExportJob` rejection), not just a job status of `"error"` — this is
     the exact distinction the task prompt calls out ("errors from the poll
     itself... not just job-status error").
  5. *(added)* does not call `setState` / trigger a React warning after the
     panel is unmounted mid-poll (unmounts while a `getExportJob` mock keeps
     returning `"running"`, waits past one more poll interval, asserts
     `console.error` was never called).

- `shell/src/pages/MapEditorPage.tsx`: added `useInstanceInfo` +
  `exportEnabled` (same pattern as `etlEnabled` in `NewItemButton.tsx`),
  rendered `{exportEnabled && <ExportPanel itemId={pk} />}` in the aside,
  after `PrintLayoutPanel`. This is naturally outside the `isExportRender`
  branch — that branch returns early above this code, so no extra guard
  was needed (the brief's suggested `pk !== null` check doesn't apply here:
  `pk` is typed `string`, never null, in this component).

- `shell/src/pages/AppRuntimePage.tsx`: added the same `useInstanceInfo` +
  `exportEnabled`, rendered `{exportEnabled && <ExportPanel itemId={pk} />}`
  inside the existing `{!isExportRender && query.data.interactions ===
  "auto" && (...)}` top bar, next to "Enregistrer la vue".

## TDD evidence

RED (module missing):
```
FAIL  src/builder/print/ExportPanel.test.tsx
Error: Failed to resolve import "./ExportPanel" ...
```

GREEN (after implementation, before adding the 2 extra tests):
```
✓ src/builder/print/ExportPanel.test.tsx (4 tests) 3757ms
```

Final GREEN (5 tests, after adding poll-failure + unmount-safety tests):
```
✓ src/builder/print/ExportPanel.test.tsx (5 tests) 3796ms
```

One deliberate deviation from the brief's Step 3 sample code, found via
TDD: the brief's snippet used `e instanceof Error ? e.message :
"Échec de l'export."` in the catch block, but its own test 3 rejects
`createExport` with `new Error("Request failed: 403 POST /export")` and
asserts the alert matches `/échec/i` — the raw message doesn't contain
"échec", so the brief's own sample code would have failed its own test.
Fixed by using a fixed French message regardless of the underlying error
text (matches the project convention already used in `ImportFileButton.tsx`,
which also discards the raw error and shows a fixed "Échec de l'import.").

## Files changed

- `shell/src/builder/print/ExportPanel.tsx` (new)
- `shell/src/builder/print/ExportPanel.test.tsx` (new)
- `shell/src/pages/MapEditorPage.tsx`
- `shell/src/pages/AppRuntimePage.tsx`

Commit: `bc0f406` — "feat(shell): SP-17a — ExportPanel (bouton, dialogue, poll) intégré carte/app"

Note: `.superpowers/sdd/progress.md` was already modified in the working
tree at task start (not by this task, not in my "touches only" scope) — left
unstaged/uncommitted.

## Self-review findings

- **Poll loop stops on unmount / terminal state**: confirmed. `mountedRef`
  checked before every `setState` and before recursing; `timerRef` cleared
  in the `useEffect` cleanup. Dedicated test unmounts mid-poll (job stuck on
  `"running"`), waits 2000ms (> one poll interval), asserts `console.error`
  was never invoked (would catch both React's "state update on unmounted
  component" warning, if the runtime still emitted it, and any unhandled
  rejection logging).
- **No setState after unmount**: same guard as above; also `finally` block
  in `onExport` (`setRunning(false)`) is gated.
- **Fetch errors during poll show `role="alert"`, not silently swallowed**:
  confirmed — both a job-level `status: "error"` and a `getExportJob`
  promise rejection reach `role="alert"`, tests 2 and 4 respectively.
- **`createExport` failure (not just poll failure) is also caught**:
  confirmed, test 3.
- **`exportEnabled` gating works**: `ExportPanel` only renders when
  `useInstanceInfo().data?.exportEnabled === true`, same fail-closed pattern
  as `etlEnabled`/`readOnly` elsewhere (MSW/test defaults resolve
  `exportEnabled: false`, so existing `MapEditorPage.test.tsx` /
  `AppRuntimePage.test.tsx` suites pass unchanged without ever exercising
  `ExportPanel` — confirms no accidental render when the capability is off).
- **Panel absent/inert during actual export-render capture**: in
  `MapEditorPage`, the `isExportRender` branch returns a completely
  different nude JSX tree above the aside that hosts `ExportPanel` — the
  export capture never reaches the code path that renders it. In
  `AppRuntimePage`, `ExportPanel` sits inside `{!isExportRender && ...}`,
  so it's excluded by the same guard Task 10 already put in place for the
  "Enregistrer la vue" button. Neither page can render `ExportPanel` while
  `isExportRender` is true, so it can't poll or fetch during a headless
  capture.

## Full suite + build results

- `npm run test`: **128 test files passed, 1030 tests passed** (was 1029
  before this task; +1 net test file `ExportPanel.test.tsx` with 5 tests,
  no regressions elsewhere — `MapEditorPage.test.tsx` (5 tests) and
  `AppRuntimePage.test.tsx` (11 tests) both re-verified green in isolation
  too).
- `npx tsc --noEmit`: clean, no errors.
- `npx vite build`: clean build (pre-existing chunk-size warnings only,
  unrelated to this change).

## Concerns

None blocking. Two minor notes:
- `.superpowers/sdd/progress.md` has uncommitted changes in the working tree
  that predate/are outside this task — left untouched per the "touches
  only" scope.
- `ExportPanel`'s outer wrapper is `flex flex-col gap-2`, which reads fine
  stacked in `MapEditorPage`'s aside but is slightly tall inside
  `AppRuntimePage`'s horizontal top bar (button + dialog + potential
  link/alert all in one flex column next to "Enregistrer la vue"). Purely
  cosmetic, no functional or accessibility issue — not addressed since it's
  outside the brief's specified integration code and no test covers layout.
