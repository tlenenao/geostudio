## Task 11: Shell — `itemClient.ts` (`copilotTurn` + `copilotEnabled`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`

**Interfaces:**
- Produces: `InstanceInfo.copilotEnabled: boolean`; `CopilotMessage`, `CopilotClientOp`, `CopilotTurnResult` types; `ItemClient.copilotTurn(itemId, payload): Promise<CopilotTurnResult>`. Consumed by Task 13 (`CopilotPanel.tsx`) and `AppBuilderPage.tsx` wiring.

- [ ] **Step 1: Add types**

In `shell/src/api/types.ts`, change:
```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; appExportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean };
```
to:
```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; appExportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean; copilotEnabled: boolean };

export type CopilotMessage = { role: "user" | "assistant"; content: string };
export type CopilotClientOp = { op: string; args: Record<string, unknown> };
export type CopilotTurnResult = { reply: string; clientOps: CopilotClientOp[] };
export type CopilotToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };
```

Add the method to the `ItemClient` interface, right after `getInstanceInfo(): Promise<InstanceInfo>;`:
```ts
  getInstanceInfo(): Promise<InstanceInfo>;
  copilotTurn(itemId: string, payload: {
    message: string;
    history: CopilotMessage[];
    mcpToken: string;
    currentConfig: AppConfig;
    clientTools: CopilotToolSchema[];
  }): Promise<CopilotTurnResult>;
```

- [ ] **Step 2: Implement in `createItemClient`**

In `shell/src/api/itemClient.ts`, add right after `getAppExportJob`:

```ts
    async getAppExportJob(_itemId: string, jobId: string): Promise<AppExportJobStatus> {
      return request<AppExportJobStatus>("GET", `/app-exports/jobs/${jobId}`);
    },

    async copilotTurn(itemId, payload): Promise<CopilotTurnResult> {
      return request<CopilotTurnResult>("POST", "/copilot/turn", { itemId, ...payload });
    },
```

(Add `CopilotTurnResult` to the existing `import type { ... } from "./types"` at the top of the file.)

- [ ] **Step 3: Type-check**

Run: `cd shell && npm run build`
Expected: PASS — `tsc --noEmit` succeeds (confirms `createItemClient`'s returned object structurally satisfies the updated `ItemClient` interface, and any test-double `ItemClient` implementations using `Partial<ItemClient>` still compile).

- [ ] **Step 4: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts
git commit -m "$(cat <<'EOF'
feat(shell): ItemClient.copilotTurn + InstanceInfo.copilotEnabled (SP-20)

Types CopilotMessage/CopilotClientOp/CopilotTurnResult/CopilotToolSchema
et méthode copilotTurn() côté client, miroir de createAppExport.
EOF
)"
```

---

