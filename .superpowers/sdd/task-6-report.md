# Task 6 Report: Widen `AppExportMode` on the shell

**Date:** 2026-08-15  
**Status:** DONE  
**Commit:** `b6b59b3`

## Summary

Successfully widened the `AppExportMode` type in the shell from a literal `"static"` to a union type `"static" | "connected"`, matching the core's API which already accepts both values. Typecheck passes with no errors. This is the first shell-side task in SP-18b (export d'apps — mode Connecté).

## Implementation

### Step 1: Widen the Type
Modified `shell/src/api/types.ts` line 607:

**Before:**
```typescript
export type AppExportMode = "static";
```

**After:**
```typescript
export type AppExportMode = "static" | "connected";
```

### Step 2: Type Checker Verification
Ran: `cd shell && npx tsc --noEmit`

**Result:**
```
✓ PASS (no output, no errors)
```

No type errors, no warnings. Widening a union is a safe, backward-compatible change.

### Step 3: Commit
```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): AppExportMode gains \"connected\" (SP-18b)"
```

**Commit hash:** `b6b59b3`  
**Files changed:** 1  
**Lines changed:** 1 insertion, 1 deletion

## Files Changed

- **`shell/src/api/types.ts`** (line 607)
  - Type widening only, no other modifications

## Technical Details

**Rationale:**
- The core's `POST /app-exports` route (implemented in Tasks 1-5, already merged) already validates and accepts both `"static"` and `"connected"` export modes
- The shell type was artificially narrowed to `"static"` only, creating a type mismatch with the actual API contract
- This task widens the shell type to match reality, unblocking downstream SP-18b work

**Backward Compatibility:**
- All existing code passing `"static"` to `createAppExport()` and related functions remains valid
- No callers needed to change
- New code can now pass `"connected"` as well

## Self-Review

✓ **Type correctness:** Union type `"static" | "connected"` is valid TypeScript  
✓ **API alignment:** Shell type now matches core's actual `AppExportMode` parameter  
✓ **Backward compatibility:** Union widening never breaks existing valid callers  
✓ **Naming consistency:** Matches project convention for export mode literals  
✓ **No cascading changes:** Type widening is purely additive; no other files need modification  
✓ **Typecheck passes:** TypeScript compilation clean, no regressions  

## Concerns

None. This is a straightforward type widening with no architectural or functional implications. All callers continue to work unchanged.
