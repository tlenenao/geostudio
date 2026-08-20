# Task 13 report — E2E: copilot panel presence + explain/add-widget flows

## What was implemented

Created `shell/e2e/copilot.spec.ts` with the exact code from the task brief,
verbatim (no deviations needed — the brief's assumptions about the
app-creation flow, dialog labels, and URL pattern all matched the current
codebase exactly, confirmed against `shell/e2e/app-builder.spec.ts` before
writing).

Two tests:

1. **`copilot panel is absent without copilotEnabled`** — creates an app via
   the standard "Nouveau" dialog flow (mocked core, default `/instance` route
   from `mockCore` which returns `{readOnly:false}` with no `copilotEnabled`
   key), lands on `/apps/9/edit`, asserts `getByLabel("Message au copilote")`
   has count 0.

2. **`copilot: explain prompt makes no changes, add-widget prompt adds and is
   undoable`** — overrides `https://core.test/instance` to
   `{readOnly:false, copilotEnabled:true}` and mocks
   `https://core.test/copilot/turn` to branch on whether the message contains
   "indicateur": an "explain" prompt returns `clientOps: []` (no canvas
   change asserted via absence of `Sélectionner widget-` buttons), an
   "add indicator" prompt returns `clientOps: [{op: "addWidget", args:
   {type: "indicator"}}]` (canvas change asserted, then undone via the
   toolbar's existing "Annuler" button — not a dedicated copilot undo
   control, matching Task 12's deliberate design).

## Verification against real code (before running anything)

- `shell/src/builder/copilot/CopilotPanel.tsx`: confirmed `aria-label`
  `"Message au copilote"` on the textarea (line 85) and button text
  `"Envoyer"` (line 92), matching the spec's selectors exactly.
- `shell/src/pages/AppBuilderPage.tsx`: confirmed
  `copilotEnabled = instanceQuery.data?.copilotEnabled === true` (line 42)
  gates `<CopilotPanel>` rendering (line 320) — matches test 1's premise.
- `shell/e2e/mocks.ts`: confirmed the default `https://core.test/instance`
  route returns `{readOnly: false}` with no `copilotEnabled` field (so test 1
  needs no override), and that `page.route` calls registered after
  `mockCore(page)` but before `page.goto("/")` correctly override mockCore's
  handlers (Playwright matches last-registered-first) — used for test 2's
  `/instance` and `/copilot/turn` overrides.
- `shell/e2e/app-builder.spec.ts`: confirmed the app-creation flow (dialog
  labels `"Nouveau"`/`"Nouvel élément"`/`"Type"`/`"Titre"`/`"Créer"`, URL
  pattern `/\/apps\/9\/edit$/`) and the "Annuler" toolbar button
  (SP-19, already shipped) match the brief's assumptions verbatim.

No corrections were needed — brief matched the real code exactly.

## Test run evidence

### Step 2 — isolated run

```
cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/copilot.spec.ts
```

```
Running 2 tests using 1 worker

  ✓  1 e2e/copilot.spec.ts:5:1 › copilot panel is absent without copilotEnabled (1.2s)
  ✓  2 e2e/copilot.spec.ts:19:1 › copilot: explain prompt makes no changes, add-widget prompt adds and is undoable (1.9s)

  2 passed (35.6s)
```

### Step 3 — full E2E suite

```
cd shell && npm run e2e
```

```
Running 107 tests using 8 workers
...
  ✓   17 e2e/copilot.spec.ts:5:1 › copilot panel is absent without copilotEnabled (958ms)
  ✓   22 e2e/copilot.spec.ts:19:1 › copilot: explain prompt makes no changes, add-widget prompt adds and is undoable (2.2s)
...
  107 passed (1.7m)
```

All 107 tests across every spec file passed — no regressions. (Note: the
brief's Step 3 text says "19 specs total"; the actual current suite has grown
to many more spec *files* — e.g. `analytics-context.spec.ts` alone contributes
dozens of tests — by 107 individual test cases across ~50+ spec files at this
point in the branch's history. This is a pre-existing drift in the brief's
count, not a discrepancy caused by this task; all tests pass regardless.)

## Files changed

- Created: `/home/lenen/projets/geostudio/shell/e2e/copilot.spec.ts` (61
  lines, matches brief verbatim).

No other files were touched. The working tree had a number of pre-existing
unrelated modified/untracked files (various `.superpowers/sdd/*.md` task
briefs/reports, `deploy/postgis/Dockerfile`, `deploy/postgis/pg_hba.conf`,
`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`) — these were left
untouched and unstaged; only `shell/e2e/copilot.spec.ts` was staged and
committed.

## Self-review findings

None. The spec is a verbatim copy of the brief's Step 1 code (diffed
mentally against the brief while writing — no typos, no selector drift).
Confirmed via source inspection (not just brief-trust) that every selector
used (`"Message au copilote"`, `"Envoyer"`, `"Sélectionner widget-"` pattern,
`"Annuler"`) exists in the real component code before running anything.

## Issues or concerns

None. Both isolated and full-suite runs are green, commit is clean (single
file, exact message from the brief), and this was the last implementation
task — the branch is now ready for the final whole-branch review per the
plan.
