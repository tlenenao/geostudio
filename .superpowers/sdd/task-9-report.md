# Task 9 Report: Shell — `applyClientOp.ts` (SP-20)

## Summary

Implemented `shell/src/builder/copilot/applyClientOp.ts` — a pure function that executes client operations proposed by the copilot (SP-20) by reusing existing pure helpers from the palette/PropsPanel. All 7 tests pass.

## Implementation Details

### Files Created

1. **`shell/src/builder/copilot/applyClientOp.test.ts`** (103 lines)
   - 7 test cases covering all 5 operations plus error cases
   - Uses `vitest` with beforeEach setup to reset/register widgets
   - Tests all code paths: success, unknown type, duplicate ID, unknown operation

2. **`shell/src/builder/copilot/applyClientOp.ts`** (78 lines)
   - Pure function `applyClientOp(raw: RawClientOp, config: AppConfig, activePageId: string): AppConfig`
   - Exported type `RawClientOp` (opaque op name + args)
   - Helper `coerceProp()` for type coercion (string/number/boolean/dataSource)
   - Five switch cases:
     - `addWidget`: creates item with default props/size via `getWidget()`
     - `updateWidgetProps`: merges only keys in `configSchema`, coerces by type
     - `removeWidget`: filters item by id
     - `addDataSource`: appends new source, ignores duplicate id
     - `setFilter`: updates source's query
   - Default: no-op, never throws

### Design Decisions

- **Pure, no mutations**: all operations return a new `AppConfig`, never mutate input
- **Reuses existing helpers**: `nextFreePosition`, `getPageLayout`, `setPageLayout`, `getWidget` — same code path as manual UI
- **Type safety**: `coerceProp()` enforces type coercion; `updateWidgetProps` checks `configSchema` before merging
- **Unknown op safety**: unknown operation names are no-ops; unknown widget types are no-ops

### Imports Verified

All imports exist and have correct signatures:
- `getWidget` from `../registry` ✓
- `nextFreePosition` from `../grid` ✓
- `getPageLayout`/`setPageLayout` from `../pages` ✓
- Types `AppConfig`/`DataSource`/`WidgetItem` from `../../api/types` ✓

## TDD Evidence

### RED (Before Implementation)

```
cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts

Failed Suites 1
FAIL  src/builder/copilot/applyClientOp.test.ts
Error: Failed to resolve import "./applyClientOp" from "src/builder/copilot/applyClientOp.test.ts"

Test Files  1 failed (1)
```

### GREEN (After Implementation)

```
cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts

✓ src/builder/copilot/applyClientOp.test.ts (7 tests) 16ms

Test Files  1 passed (1)
Tests       7 passed (7)
```

## Test Coverage

All 7 tests pass:

1. ✓ `addWidget adds an item with the widget's default props/size`
2. ✓ `addWidget with an unknown type is a no-op`
3. ✓ `updateWidgetProps merges only keys present in configSchema, coerced by type`
4. ✓ `removeWidget removes the item by id`
5. ✓ `addDataSource appends a new source, ignoring a duplicate id`
6. ✓ `setFilter updates an existing source's query`
7. ✓ `an unknown op name is a no-op, never throws`

## Commit

```
e87f01a feat(shell): applyClientOp.ts — exécute les opérations du copilote (SP-20)
```

Commit message follows the exact format from the brief.

## Self-Review Findings

✓ No issues found. Implementation is clean, pure, and follows project patterns.

### Code Quality

- Follows SPDX license header convention
- French documentation comments reflect copilot context
- Type safety enforced via TypeScript strict mode
- No magic numbers; uses existing constants
- Error handling: all unknown inputs are safe (return original config or no-op)

### Integration Points

- Ready for Task 13 (`CopilotPanel.tsx`) which will call this via `setDraft`
- Every copilot edit lands in SP-19's undo stack for free (no changes needed)
- Consistent with shell's pure-function architecture patterns

## Concerns

None. Implementation is complete, tested, and ready for use.
