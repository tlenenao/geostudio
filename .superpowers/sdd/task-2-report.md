# Task 2 Report: `useUndoableDraft` React Hook

## Summary

Successfully implemented `useUndoableDraft`, a React hook that wraps the pure `UndoStack` module (Task 1) to provide debounced undo/redo state management for the AppBuilder's AppConfig draft. The hook collapses rapid bursts of changes into single undo steps via a 400ms coalesce window, while supporting the same call signature as the plain `useState` setter it replaces (both value and updater function forms).

## What Was Implemented

### Files Created

1. **`shell/src/builder/useUndoableDraft.test.tsx`** — 8 comprehensive tests:
   - `seedDraft` sets initial draft without creating undo step
   - `seedDraft` never overwrites already-seeded draft
   - `canUndo` flips true once coalesce window elapses
   - `undo` restores pre-edit config and flushes pending burst immediately
   - Rapid burst of `setDraft` calls collapses into one undo step
   - `redo` restores what undo reverted
   - New edit after undo purges redo branch
   - `setDraft` supports functional-updater form

2. **`shell/src/builder/useUndoableDraft.ts`** — Hook implementation with:
   - `UndoableDraft` type defining public API
   - `useUndoableDraft()` hook function
   - Debounced pending baseline capture (400ms idle flush)
   - Proper cleanup of timers on flush/undo/redo
   - Support for both value and functional updater forms in `setDraft`
   - `seedDraft` that sets initial config without affecting history
   - Full undo/redo state management via `canUndo`/`canRedo` flags

### Key Implementation Details

- **Coalesce window**: First `setDraft` within a burst captures the pre-burst config as pending baseline; subsequent calls within 400ms extend the burst without re-capturing
- **Immediate flush on undo/redo**: Both operations call `flush()` synchronously first, so Ctrl+Z works mid-burst without waiting for the timer
- **Seed bypass**: `seedDraft` uses `prev ?? value` to set initial config without creating history, preserving the original AppBuilderPage behavior
- **Exact signature compatibility**: `setDraft` accepts both direct values and updater functions, identical to `useState` signature for seamless replacement
- **Timer cleanup**: Properly clears pending timeout when flushing or taking any action

## Test Results

### TDD Verification

**RED (failing tests before implementation):**
```
Exit code 1
FAIL  src/builder/useUndoableDraft.test.tsx
Error: Failed to resolve import "./useUndoableDraft" from "src/builder/useUndoableDraft.test.tsx".
Does the file exist?
```

**GREEN (all tests passing):**
```
 ✓ src/builder/useUndoableDraft.test.tsx (8 tests) 46ms

 Test Files  1 passed (1)
      Tests  8 passed (8)
```

All 8 tests verify:
- Initial state and seeding behavior
- Debounce coalescing across multiple rapid edits
- State restoration on undo/redo
- History truncation on new edits after undo
- Functional updater syntax support

## Files Changed

- **Created**: `shell/src/builder/useUndoableDraft.ts` (105 lines)
- **Created**: `shell/src/builder/useUndoableDraft.test.tsx` (135 lines)

## Commit Created

```
fa614ad feat(shell): useUndoableDraft — debounced undo/redo for the builder config (SP-19)
```

## Self-Review Findings

### Completeness ✓
- All 8 tests from brief implemented verbatim
- Full implementation from brief transcribed exactly
- All imports correct (AppConfig type, undoStack exports)
- Commit message matches brief specification

### Code Quality ✓
- Follows React hooks best practices (useCallback, useRef, useState)
- Proper dependency arrays on all useCallback hooks
- Timer cleanup implemented in flush() to prevent memory leaks
- No direct state mutations; all state updates via proper React patterns
- TypeScript types correctly applied throughout

### Testing ✓
- Tests use vitest fake timers correctly
- beforeEach/afterEach restore real timers after each test
- act() wraps all state changes
- Tests verify both synchronous and asynchronous behavior
- Burst coalescing verified with multiple sequential advanceTimersByTime calls
- Edge cases covered: empty undo, redo after undo, new edit clearing redo

### Architecture Alignment ✓
- Hook maintains exact `useState` call signature for `setDraft` — seamless Task 3 replacement
- `seedDraft` preserves original session start semantics (never overwrites)
- Debouncing hides keystroke bursts from undo stack as designed
- Immediate flush on undo/redo ensures Ctrl+Z responsiveness
- No changes needed to caller code (AppBuilderPage)

### No Concerns

- Implementation follows brief specification precisely
- All tests pass without modification
- No linting issues (SPDX header present, code style matches project)
- Ready for Task 3 integration with AppBuilderPage

## Verification Steps

1. ✓ Created test file (Step 1)
2. ✓ Verified tests fail without implementation (Step 2)
3. ✓ Created implementation file from brief (Step 3)
4. ✓ Verified all 8 tests pass (Step 4)
5. ✓ Committed with exact message (Step 5)
6. ✓ Self-reviewed completeness, quality, discipline

Ready for Task 3: Integration with AppBuilderPage.
