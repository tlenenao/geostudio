### Task 6: widen `AppExportMode` on the shell

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `AppExportMode = "static" | "connected"` (was `"static"` only).

- [ ] **Step 1: Widen the type**

In `shell/src/api/types.ts`, change:

```ts
export type AppExportMode = "static";
```

to:

```ts
export type AppExportMode = "static" | "connected";
```

- [ ] **Step 2: Run the type checker**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS (widening a union type is never a breaking change for
existing callers that only ever passed `"static"`).

- [ ] **Step 3: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): AppExportMode gains \"connected\" (SP-18b)"
```

---

