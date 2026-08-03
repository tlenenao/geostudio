# Task 5 report — E2E coverage for SQL Lab (SP-14i)

## What was implemented

Created `shell/e2e/sql-lab.spec.ts` exactly as specified in the task brief (verbatim, no
code changes) — 3 Playwright scenarios:

1. **Happy path**: an analyst (`isAnalyst: true`) navigates to `/analytics/sql`, sees the
   "SQL Lab" nav link, fills the SQL editor, executes, sees the results table (columns +
   rows), verifies the POST body sent to `https://core.test/analytics/sql`, clears the
   editor, reloads a query from history via its labelled button, and confirms the editor
   value is restored.
2. **SQL error**: the mocked `/analytics/sql` route returns HTTP 400 with a structured
   error body; the test verifies the `role="alert"` message shows the server's error text
   and that the editor still holds the offending SQL (not cleared on failure).
3. **Access denial**: a non-analyst user (using `mockCore`'s default `/me` route, which
   omits `isAnalyst` entirely) navigates to `/analytics/sql`, sees the access-denied alert
   ("Accès réservé aux analystes."), confirms the "SQL Lab" nav link is absent, and that
   the `/analytics/sql` endpoint was never called.

No application source code was touched — only the new spec file.

## What was tested and results

1. **New spec only**: `npm run e2e -- e2e/sql-lab.spec.ts` → **3/3 passed** (49.7s), first
   try, no adjustments needed to the brief's literal selectors/timing.
2. **Full E2E suite**: `npm run e2e` → **79/79 passed** (~2.0m), confirming 76 pre-existing
   specs + 3 new ones, no regressions.
3. **Final whole-suite check** (per brief's "Final check" section):
   - `npm test` → **807 tests passed across 106 files** (unit/Vitest), including the
     pre-existing `src/lib/sqlLabHistory.test.ts` (4 tests, from Task 2).
   - `npx tsc --noEmit` → clean, no errors.
   - `npm run e2e` (re-run) → **79/79 passed** again, pristine.

## Files changed

- Created: `/home/lenen/projets/geostudio/shell/e2e/sql-lab.spec.ts` (77 lines, 3 tests)
- Commit: `f7f7b6d` — `test(e2e): couvre SQL Lab — exécution, erreur, historique, garde analyste (SP-14i)`
  (only this one file staged and committed; other working-tree changes under
  `.superpowers/sdd/*` from prior tasks were left untouched, out of scope for this task)

## Self-review

- **Completeness**: all 3 scenarios from the brief present, matching intent (execute +
  history reload; SQL error message + editor text preserved; non-analyst denial + no nav
  link + no API call).
- **Quality**: selectors use `getByRole`/`getByLabel` (accessible, robust — no CSS/test-id
  hacks); no arbitrary `sleep`/timeouts; `expect.poll` used correctly to await the async
  POST body rather than racing it.
- **Discipline**: no application source code modified; only the single new spec file
  created and committed, exactly per the brief.
- **Testing**: full 79-spec E2E suite green twice (once right after adding the spec, once
  again as part of the final whole-branch check), plus unit tests (807/807) and `tsc
  --noEmit` clean.

## Deviations from the brief's literal code

**None.** The spec file is byte-for-byte the code given in the brief. It passed against
the real running app on the first attempt with no selector or timing adjustments required.

## Issues or concerns

None. Task 5 is the final task of the SP-14i plan; all prior tasks (1-4) were already
in place on `dev` HEAD and this task's E2E coverage confirms they integrate correctly
end-to-end.

## Fix: SPDX header

**Finding:** `shell/e2e/sql-lab.spec.ts` was missing the SPDX license identifier header required by the SP-14i plan's Global Constraints.

**Fix applied:** Added `// SPDX-License-Identifier: Apache-2.0` as the first line, followed by a blank line, before the existing `import` statement.

**Test result:** `npm run e2e -- e2e/sql-lab.spec.ts` → **3/3 passed** (46.7s), all SQL Lab scenarios remain green.

**Commit:** `27428d4` — `fix(shell): ajoute l'en-tête SPDX manquant à sql-lab.spec.ts (SP-14i)`
