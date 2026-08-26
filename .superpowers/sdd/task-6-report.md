# Task 6 Report: `ErrorBoundary` applicatif (3.5c)

**Date:** 2026-08-26  
**Status:** DONE  
**Commit:** `3598ce2` — `feat(shell): error boundary applicatif à la racine`

## Summary

Implemented a root-level React error boundary (`AppErrorBoundary`) to catch render crashes anywhere in the application outside of the per-widget error boundary that already existed in `WidgetHost.tsx`. This closes I12 from the project review (2026-08-20), which identified that the only error boundary was scoped per-widget, causing crashes in builder chrome, pages, or panels to produce a white screen.

## Implementation Details

### Files Created

1. **`shell/src/AppErrorBoundary.tsx`** (50 lines)
   - Class component error boundary extending `React.Component<Props, State>`
   - Implements `getDerivedStateFromError()` to set `failed: true` on any child render error
   - Implements `componentDidCatch()` to log errors via `console.error()`
   - Renders a user-friendly fallback UI in French when an error occurs:
     - Message: "Une erreur est survenue."
     - Instructions to reload the page or contact admin
     - "Recharger" button that calls `window.location.reload()`
   - Styled with Tailwind CSS (flexbox centering, slate color palette)
   - Explicitly documented as distinct from `WidgetErrorBoundary` (builder/WidgetHost.tsx)

2. **`shell/src/AppErrorBoundary.test.tsx`** (50 lines)
   - Test 1: Verifies children render normally when nothing throws
   - Test 2: Verifies fallback UI renders when a child throws, with mocked `console.error`
   - Tests imported directly from the brief, no modifications needed

### Files Modified

**`shell/src/App.tsx`**
- Added import: `import { AppErrorBoundary } from "./AppErrorBoundary";`
- Wrapped root return: `<AppErrorBoundary>` now wraps `<AuthProvider>`, ensuring it catches not just router/page crashes but also provider initialization errors
- Position: Outside `AuthProvider` and `QueryClientProvider` to maximize crash detection scope

## TDD Evidence

**RED (Step 2):**
```
Error: Failed to resolve import "./AppErrorBoundary" from "src/AppErrorBoundary.test.tsx"
```

**GREEN (after Step 3 implementation):**
```
✓ src/AppErrorBoundary.test.tsx (2 tests) 47ms
Test Files  1 passed (1)
Tests  2 passed (2)
```

## Full Suite Results

### Tests
- **Command:** `npx vitest run`
- **Result:** 162 files, 1463 tests, all passing
- **Delta:** +1 test file (AppErrorBoundary.test.tsx), +2 tests
- **Pre-existing baseline:** 161 files, 1461 tests

### Linting
- **Command:** `npm run lint`
- **Result:** ✓ PASS (no eslint errors)

### Format Check
- **Command:** `npm run format:check`
- **Result:** ✓ PASS (prettier check passed)

### Build
- **Command:** `npm run build`
- **Result:** ✓ PASS (build succeeded in 15.16s)
- **Note:** Pre-existing warnings about chunk size > 500 kB unrelated to this change

## Self-Review

### Completeness
- ✓ Test file created (Step 1)
- ✓ Test confirmed failing (Step 2)
- ✓ Component implemented exactly per brief (Step 3)
- ✓ Wired into App.tsx correctly (Step 4)
- ✓ Both test files pass individually (Step 5)
- ✓ Full suite + lint + format + build all green (Step 6)
- ✓ Committed with appropriate message (Step 7)

### Quality Checks
- ✓ Fallback UI is accessible and reasonable (flex layout, clear French messaging, reload button)
- ✓ `componentDidCatch` logs via `console.error` as specified
- ✓ No scope creep: `WidgetErrorBoundary` in builder/WidgetHost.tsx untouched
- ✓ Placement rationale followed: outside providers to catch provider crashes
- ✓ State management is simple and correct: only tracks `failed` boolean
- ✓ Error boundary recovery: fallback stays until page reload
- ✓ Test mocks console.error to avoid noise in test output

### Notes
- The commitlint hook enforced lowercase subject line (`error boundary` vs `ErrorBoundary`), which is fine — the component name is still clear in the body
- `App.test.tsx` required no changes; its partial provider setup doesn't affected by the new wrapper
- All pre-commit hooks (eslint, prettier, commitlint) passed

## Files Changed

```
shell/src/AppErrorBoundary.tsx       (new, +50 lines)
shell/src/AppErrorBoundary.test.tsx  (new, +50 lines)
shell/src/App.tsx                    (modified, +2 lines)
```

## Commit

- **SHA:** 3598ce2
- **Subject:** feat(shell): error boundary applicatif à la racine
- **Body:** Explains the rationale (I12 fix) and distinction from widget-scoped boundary
- **Co-Author:** Claude Sonnet 5 <noreply@anthropic.com>

## No Issues or Concerns

All requirements met. Ready for merge.
