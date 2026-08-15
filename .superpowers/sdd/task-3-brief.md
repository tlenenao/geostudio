### Task 3: wire into `AppBuilderPage`

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `useUndoableDraft` (Task 2, `../builder/useUndoableDraft`).
- Produces: two new toolbar buttons with visible text "Annuler" and
  "Rétablir" (accessible name = visible text, no separate aria-label
  needed), disabled per `canUndo`/`canRedo`. Global `Ctrl+Z`/`Cmd+Z` (undo)
  and `Ctrl+Shift+Z`/`Cmd+Shift+Z` (redo) keyboard shortcuts, ignored when
  `document.activeElement` is a text-editing element.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (all existing tests stay
as-is above this):

```tsx


test("a GridCanvas move can be undone with Ctrl+Z", async () => {
  const withItem: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0);
});

test("Ctrl+Shift+Z redoes an undone GridCanvas move", async () => {
  const withItem: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeEnabled();

  await userEvent.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(1);
});

test("a burst of keystrokes in visibleWhen collapses into one undo step once blurred", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x == 'a'");
  // Move focus to a non-text element — tabbing would only land in the "text"
  // widget's own textarea just below visibleWhen in the same panel, still a
  // text field, so it wouldn't actually exercise the "focus left every text
  // field" path the keyboard shortcut check depends on.
  await userEvent.click(screen.getByRole("button", { name: "Édition" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(area).toHaveValue("");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
});

test("Ctrl+Z while focus is in a text field does not trigger the builder's undo", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x");
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.type(area, "{Control>}z{/Control}"); // focus stays in `area`
  expect(area).toHaveValue("vars.x");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled();
});

test("Annuler and Rétablir start disabled and stay disabled with no edits", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — no element with role `button` and name `Annuler`/`Rétablir`
exists yet.

- [ ] **Step 3: Update `AppBuilderPage.tsx`**

Change the import block — replace:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
```

with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useUndoableDraft } from "../builder/useUndoableDraft";
```

Replace the `draft`/`selectedId` state declarations:

```tsx
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
```

with:

```tsx
  const { draft, setDraft, seedDraft, undo, redo, canUndo, canRedo } = useUndoableDraft();
  const [selectedId, setSelectedId] = useState<string | null>(null);
```

Replace the seeding effect:

```tsx
  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    if (query.data) setDraft((d) => d ?? query.data);
  }, [query.data]);
```

with:

```tsx
  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    // seedDraft (not setDraft) — this is the session's starting point, not
    // an edit, and must not create an undo step (SP-19).
    if (query.data) seedDraft(query.data);
  }, [query.data, seedDraft]);
```

Add the keyboard shortcut effect right after it (still before the
`query.isLoading` early return, alongside the other hooks):

```tsx
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField = target instanceof HTMLInputElement
        || target instanceof HTMLTextAreaElement
        || (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);
```

Add the toolbar buttons — replace:

```tsx
          <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
          <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
          <div className="ml-2 flex items-center gap-1">
```

with:

```tsx
          <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
          <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
          <div className="ml-2 flex items-center gap-1">
            <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>Annuler</Button>
            <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>Rétablir</Button>
          </div>
          <div className="ml-2 flex items-center gap-1">
```

(This introduces a second `ml-2` group right after the first — matching the
existing breakpoint-buttons group's own styling, just placed before it.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS (all tests, existing + 5 new)

- [ ] **Step 5: Run the full shell unit suite to confirm nothing broke**

Run: `cd shell && npm run test`
Expected: PASS (no regressions elsewhere — `AppRenderer`'s own `onChange`
prop type is unchanged, still `(config: AppConfig) => void`, satisfied by
the hook's `setDraft`).

- [ ] **Step 6: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): AppBuilderPage gains undo/redo — Ctrl+Z/Ctrl+Shift+Z + toolbar buttons (SP-19)"
```

---

