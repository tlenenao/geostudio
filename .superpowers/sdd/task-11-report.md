## Task 11 Report: Shell — `itemClient.ts` (`copilotTurn` + `copilotEnabled`)

### What Was Implemented

Added copilot support to the client-side `ItemClient` interface and implementations:

1. **New types in `shell/src/api/types.ts`:**
   - Added `copilotEnabled: boolean` field to `InstanceInfo` type
   - Added `CopilotMessage` type: `{ role: "user" | "assistant"; content: string }`
   - Added `CopilotClientOp` type: `{ op: string; args: Record<string, unknown> }`
   - Added `CopilotTurnResult` type: `{ reply: string; clientOps: CopilotClientOp[] }`
   - Added `CopilotToolSchema` type: `{ name: string; description: string; inputSchema: Record<string, unknown> }`

2. **Interface extension in `shell/src/api/types.ts`:**
   - Added `copilotTurn()` method signature to `ItemClient` interface, placed right after `getInstanceInfo()`:
     ```typescript
     copilotTurn(itemId: string, payload: {
       message: string;
       history: CopilotMessage[];
       mcpToken: string;
       currentConfig: AppConfig;
       clientTools: CopilotToolSchema[];
     }): Promise<CopilotTurnResult>;
     ```

3. **Implementation in `shell/src/api/itemClient.ts`:**
   - Added `CopilotTurnResult` to the imports from `./types`
   - Implemented `copilotTurn()` method in `createItemClient()`, right after `getAppExportJob()`:
     ```typescript
     async copilotTurn(itemId, payload): Promise<CopilotTurnResult> {
       return request<CopilotTurnResult>("POST", "/copilot/turn", { itemId, ...payload });
     }
     ```

4. **StaticItemClient implementation in `shell/src/staticExport/StaticItemClient.ts`:**
   - Added `copilotTurn()` method that rejects with `unsupported()` (consistent with other backend-dependent methods)
   - Placed after `getAppExportJob()` to maintain method ordering

### Build Verification

Run: `cd shell && npm run build`

**Output (key sections):**
```
> geostudio-shell@0.1.0 build
> tsc --noEmit && vite build

vite v6.4.3 building for production...
...
✓ 4190 modules transformed.
...
✓ built in 16.98s
```

**Result: PASS** — TypeScript compilation (`tsc --noEmit`) succeeded without errors. All test doubles and `ItemClient` implementations now properly satisfy the widened interface.

### Files Changed

- `shell/src/api/types.ts` — Added 4 new types and extended `InstanceInfo` and `ItemClient` interface
- `shell/src/api/itemClient.ts` — Added `copilotTurn()` implementation and updated imports
- `shell/src/staticExport/StaticItemClient.ts` — Added `copilotTurn()` rejection method

**Commit:** `82c64bc` — `feat(shell): ItemClient.copilotTurn + InstanceInfo.copilotEnabled (SP-20)`

### Self-Review Findings

**Strengths:**
- All changes follow existing patterns in the codebase
- `copilotTurn()` mirrors the structure of `createAppExport()` as specified in the brief
- StaticItemClient correctly rejects copilot turns (no backend available in static mode)
- All three `ItemClient` implementations (regular, static, and any test mocks using `Partial<ItemClient>`) compile without type errors

**Type Safety:**
- New types (`CopilotMessage`, `CopilotClientOp`, `CopilotTurnResult`, `CopilotToolSchema`) are simple, well-defined, and follow the project's conventions
- The `copilotTurn()` method signature clearly documents the expected payload structure (message, history, mcpToken, currentConfig, clientTools)
- `Promise<CopilotTurnResult>` return type matches the reply/clientOps structure expected by consumers (Task 12 `CopilotPanel`)

### Issues and Concerns

**None detected.** The implementation is mechanical, well-specified by the brief, and all type-checking passes. The method is ready for consumption by Task 12 (`CopilotPanel.tsx` wiring).

### Scope Confirmation

Task complete as specified:
- ✅ Step 1: Types added to `types.ts`
- ✅ Step 2: Implementation in `createItemClient()`
- ✅ Step 3: `npm run build` passes (verifies TypeScript compilation and interface satisfaction)
- ✅ Step 4: Commit created with exact message
- ✅ StaticItemClient updated (no other implementations were overlooked)
