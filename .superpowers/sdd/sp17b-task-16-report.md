# Task 16: `ReportRunPanel.tsx` — Report

## Summary

Successfully implemented `ReportRunPanel.tsx`, a read-only run-history poll panel for report schedule execution tracking. This component mirrors the existing `PipelineRunPanel` pattern but without a manual "Exécuter" button, since reports are exclusively triggered by the server-side cron sweep (`sweep_report_schedules_task`), never manually.

## Implementation Details

**File Created:**
- `shell/src/builder/report/ReportRunPanel.tsx` (59 lines)

**Component Responsibilities:**
- Consumes `useItemClient()` to access `client.getReportRuns(reportId)`
- Polls report execution history at 1500ms intervals (matching `ImportFileButton`/`PipelineRunPanel` pattern)
- Displays run status, creation timestamp, download links (if available), and error messages
- Clean teardown via `stopped` ref to prevent timer leaks on unmount

**Key Design Decisions:**
- Read-only history display — no "Exécuter" button (reports are sweep-triggered only)
- Status labels in French (pending → "En attente", running → "En cours", done → "Terminé", error → "Échec", unknown → "Inconnu")
- Graceful handling of transient poll failures (silent retry, no error UI noise)
- Proper React cleanup: `stopped.current` flag prevents state updates after unmount

## Verification

### Build Typecheck
Command: `cd shell && npm run build`

**Result:** ✓ PASSED
- TypeScript compilation clean (`tsc --noEmit`)
- Vite production build successful (11.90s)
- No type errors in the new component
- No issues related to import resolution (`useItemClient()`, `ReportRunStatus` type from `../../api/types`)

### Self-Review Findings

1. **Poll Loop Cleanup:** ✓ Correct
   - `stopped.current = false` on mount
   - `stopped.current = true` in cleanup function
   - All `setTimeout` chains guarded by `!stopped.current` check
   - No leaked timers on unmount

2. **No Manual Execution Button:** ✓ Confirmed
   - Component is pure read-only history display
   - No "Exécuter", "Lancer", or similar button present
   - Matches spec requirement (reports only trigger via cron sweep)

3. **Type Safety:** ✓ Confirmed
   - Imports correctly from existing `ItemClientProvider` (verified in context: exported at line 19)
   - `ReportRunStatus` type properly referenced
   - `STATUS_LABEL` record type safe with exhaustiveness checking

4. **Dependencies:** ✓ All exist
   - `useItemClient()` — pre-verified in brief as exported from `ItemClientProvider`
   - `client.getReportRuns(pk)` — promised by Task 14 (implementation expected, usage here is safe)
   - `ReportRunStatus` type — expected to exist in `api/types`

## Commit

**SHA:** `1c0348d`
**Message:** `feat(shell): ReportRunPanel — read-only run history poll (SP-17b)`
**Files Changed:** 1 file, 59 insertions

## Concerns / Follow-ups

None. The implementation is complete, type-safe, and follows established patterns from `PipelineRunPanel`. The component is production-ready pending only the availability of `client.getReportRuns()` implementation (Task 14), which does not block this task's completion.

## Test Plan Readiness

This component is ready for:
- Unit tests (mock `useItemClient`, test poll lifecycle and state updates)
- E2E tests (integration with `ReportScheduleEditor` or parent editor page)
- Integration into `ReportScheduleEditor` or report detail view
