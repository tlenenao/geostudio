### Task 4: E2E proof

**Files:**
- Modify: `shell/e2e/app-builder.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`./mocks`, unchanged).

- [ ] **Step 1: Append the E2E test**

Append to `shell/e2e/app-builder.spec.ts` (existing test stays as-is above
this):

```ts

test("undo/redo: adding a widget can be undone and redone", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte" }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();

  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await page.keyboard.press("Control+Shift+z");
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();
});
```

- [ ] **Step 2: Run it**

Run: `cd shell && npx playwright test e2e/app-builder.spec.ts`
Expected: PASS (2 tests — the pre-existing one and this new one).

- [ ] **Step 3: Commit**

```bash
git add shell/e2e/app-builder.spec.ts
git commit -m "test(e2e): undo/redo an added widget in the app builder (SP-19)"
```

---

## Self-review notes

- **Spec coverage:** §3 architecture (single stack behind the one existing
  commit point) → Tasks 2–3. §3 granularity (corrected 2026-08-15, centralized
  debounce) → Task 2's `COALESCE_WINDOW_MS` mechanism, verified in Task 3's
  "collapses into one undo step" and "flushes immediately on undo" tests. §5
  risk (single-commit-point audit) → resolved by construction: every panel
  reads from the same `AppBuilderPage.tsx` `setDraft` (confirmed by reading
  `PropsPanel`/`ActionsPanel`/`DataSourcePanel`/`ThemePanel`/
  `VariablesPanel`/`NavigationPanel`/`GridCanvas`/every widget's `PropsPanel`
  before writing this plan — none of them hold a second, parallel path to
  the config), so no per-panel fix task is needed. §6 acceptance criteria:
  (1) any panel's committed mutation undoable → Task 3 GridCanvas test +
  Task 4 E2E; (2) one step per gesture, not per intermediate event → Task 2
  burst test + Task 3 visibleWhen burst test; (3) 50-step cap → Task 1; (4)
  `Ctrl+Z` ignored while typing → Task 3's dedicated test.
- **Placeholder scan:** none — every step has complete, real code.
- **Type consistency:** `UndoStack<T>`/`pushUndo`/`applyUndo`/`applyRedo`
  used identically in Task 1 (definition) and Task 2 (`useUndoableDraft`'s
  only consumer). `UndoableDraft`'s five fields (`draft`, `setDraft`,
  `seedDraft`, `undo`, `redo`, `canUndo`, `canRedo`) used identically in Task
  2 (definition) and Task 3 (destructured in `AppBuilderPage.tsx`, same
  names, no renaming).
