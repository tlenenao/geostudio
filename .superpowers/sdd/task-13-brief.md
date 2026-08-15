### Task 13: widen `AppExportMode` on the shell

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `AppExportMode = "static" | "connected" | "standalone"`.

- [ ] **Step 1: Widen the type**

In `shell/src/api/types.ts`, change:

```ts
export type AppExportMode = "static" | "connected";
```

to:

```ts
export type AppExportMode = "static" | "connected" | "standalone";
```

- [ ] **Step 2: Run the type checker**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): AppExportMode gains \"standalone\" (SP-18c)"
```

---

